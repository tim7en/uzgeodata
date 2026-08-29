import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import dotenv from 'dotenv';
import express from 'express';
import multer from 'multer';

dotenv.config();

const root = path.dirname(fileURLToPath(import.meta.url));
const storageRoot = path.join(root, 'WORKSPACE');
const uploadRoot = path.join(storageRoot, 'uploads');
const metadataFile = path.join(storageRoot, 'datasets.json');
const requestsFile = path.join(storageRoot, 'requests.json');
await fs.mkdir(uploadRoot, { recursive: true });

async function readDatasets() {
  try { return JSON.parse(await fs.readFile(metadataFile, 'utf8')); }
  catch (error) {
    if (error.code === 'ENOENT') return [];
    throw error;
  }
}

async function writeDatasets(data) {
  const temporary = `${metadataFile}.tmp`;
  await fs.writeFile(temporary, JSON.stringify(data, null, 2));
  await fs.rename(temporary, metadataFile);
}

async function readRequests() {
  try { return JSON.parse(await fs.readFile(requestsFile, 'utf8')); }
  catch (error) { if (error.code === 'ENOENT') return []; throw error; }
}

async function writeRequests(data) {
  const temporary = `${requestsFile}.tmp`;
  await fs.writeFile(temporary, JSON.stringify(data, null, 2));
  await fs.rename(temporary, requestsFile);
}

const safeCompare = (a, b) => {
  const left = Buffer.from(String(a));
  const right = Buffer.from(String(b));
  return left.length === right.length && crypto.timingSafeEqual(left, right);
};

const sessions = new Map();
const cookieName = 'uzg_admin';
const sessionDuration = 12 * 60 * 60 * 1000;

function cookies(req) {
  return Object.fromEntries((req.headers.cookie || '').split(';').filter(Boolean).map(item => {
    const [key, ...value] = item.trim().split('=');
    return [key, decodeURIComponent(value.join('='))];
  }));
}

function authenticated(req, res, next) {
  const token = cookies(req)[cookieName];
  const session = token && sessions.get(token);
  if (!session || session.expiresAt < Date.now()) {
    if (token) sessions.delete(token);
    return res.status(401).json({ error: 'Authentication required' });
  }
  session.expiresAt = Date.now() + sessionDuration;
  next();
}

const allowedExtensions = new Set(['.zip', '.lpkx', '.shp', '.shx', '.dbf', '.prj', '.cpg', '.tif', '.tiff', '.img', '.gpkg', '.geojson', '.json', '.csv', '.kml', '.kmz', '.pdf']);
const storage = multer.diskStorage({
  destination: uploadRoot,
  filename: (_req, file, callback) => {
    const extension = path.extname(file.originalname).toLowerCase();
    callback(null, `${crypto.randomUUID()}${extension}`);
  }
});
const upload = multer({
  storage,
  limits: { fileSize: 5 * 1024 * 1024 * 1024, files: 20 },
  fileFilter: (_req, file, callback) => {
    const extension = path.extname(file.originalname).toLowerCase();
    callback(allowedExtensions.has(extension) ? null : new Error(`Unsupported file type: ${extension || 'unknown'}`), allowedExtensions.has(extension));
  }
});

const app = express();
app.disable('x-powered-by');
app.use(express.json({ limit: '1mb' }));

const requestWindows = new Map();
app.post('/api/requests', async (req, res, next) => {
  try {
    const now = Date.now();
    const recent = (requestWindows.get(req.ip) || []).filter(time => now - time < 60 * 60 * 1000);
    if (recent.length >= 5) return res.status(429).json({ error: 'Too many requests. Please try again later.' });
    const clean = (value, limit = 500) => String(value || '').trim().slice(0, limit);
    const request = {
      id: crypto.randomUUID(), name: clean(req.body?.name, 120), email: clean(req.body?.email, 180),
      organization: clean(req.body?.organization, 180), topic: clean(req.body?.topic, 250),
      intendedUse: clean(req.body?.intendedUse, 1500), status: 'new', createdAt: new Date().toISOString(),
    };
    if (!request.name || !request.topic || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(request.email)) {
      return res.status(400).json({ error: 'Name, valid email and dataset topic are required.' });
    }
    const requests = await readRequests(); requests.unshift(request); await writeRequests(requests);
    requestWindows.set(req.ip, [...recent, now]); res.status(201).json({ id: request.id, ok: true });
  } catch (error) { next(error); }
});

app.post('/api/admin/login', (req, res) => {
  const expectedUser = process.env.ADMIN_USERNAME;
  const expectedPassword = process.env.ADMIN_PASSWORD;
  if (!expectedUser || !expectedPassword) return res.status(503).json({ error: 'Admin credentials are not configured' });
  if (!safeCompare(req.body?.username, expectedUser) || !safeCompare(req.body?.password, expectedPassword)) {
    return res.status(401).json({ error: 'Invalid username or password' });
  }
  const token = crypto.randomBytes(32).toString('hex');
  sessions.set(token, { expiresAt: Date.now() + sessionDuration });
  res.setHeader('Set-Cookie', `${cookieName}=${token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=${sessionDuration / 1000}${process.env.COOKIE_SECURE === 'true' ? '; Secure' : ''}`);
  res.json({ ok: true });
});

app.post('/api/admin/logout', authenticated, (req, res) => {
  const token = cookies(req)[cookieName];
  sessions.delete(token);
  res.setHeader('Set-Cookie', `${cookieName}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0`);
  res.json({ ok: true });
});

app.get('/api/admin/session', (req, res) => {
  const token = cookies(req)[cookieName];
  const session = token && sessions.get(token);
  res.json({ authenticated: Boolean(session && session.expiresAt >= Date.now()) });
});

app.get('/api/admin/datasets', authenticated, async (_req, res, next) => {
  try { res.json(await readDatasets()); } catch (error) { next(error); }
});

app.get('/api/admin/requests', authenticated, async (_req, res, next) => {
  try { res.json(await readRequests()); } catch (error) { next(error); }
});

app.post('/api/admin/datasets', authenticated, (req, res, next) => {
  upload.array('files', 20)(req, res, async error => {
    if (error) return next(error);
    try {
      if (!req.files?.length) return res.status(400).json({ error: 'Select at least one data file' });
      const clean = value => String(value || '').trim().slice(0, 500);
      const entry = {
        id: crypto.randomUUID(),
        title: clean(req.body.title),
        category: clean(req.body.category),
        access: clean(req.body.access),
        description: clean(req.body.description),
        createdAt: new Date().toISOString(),
        files: req.files.map(file => ({ storedName: file.filename, originalName: file.originalname, size: file.size }))
      };
      if (!entry.title || !entry.category) {
        await Promise.all(req.files.map(file => fs.unlink(file.path).catch(() => {})));
        return res.status(400).json({ error: 'Title and category are required' });
      }
      const data = await readDatasets();
      data.unshift(entry);
      await writeDatasets(data);
      res.status(201).json(entry);
    } catch (uploadError) { next(uploadError); }
  });
});

app.delete('/api/admin/datasets/:id', authenticated, async (req, res, next) => {
  try {
    const data = await readDatasets();
    const entry = data.find(item => item.id === req.params.id);
    if (!entry) return res.status(404).json({ error: 'Dataset not found' });
    await Promise.all(entry.files.map(file => fs.unlink(path.join(uploadRoot, path.basename(file.storedName))).catch(() => {})));
    await writeDatasets(data.filter(item => item.id !== req.params.id));
    res.json({ ok: true });
  } catch (error) { next(error); }
});

app.get('/api/admin/datasets/:id/files/:file', authenticated, async (req, res) => {
  const data = await readDatasets();
  const entry = data.find(item => item.id === req.params.id);
  const file = entry?.files.find(item => item.storedName === req.params.file);
  if (!file) return res.status(404).json({ error: 'File not found' });
  res.download(path.join(uploadRoot, path.basename(file.storedName)), file.originalName);
});

app.use((error, _req, res, _next) => {
  console.error(error);
  res.status(error instanceof multer.MulterError ? 400 : 500).json({ error: error.message || 'Server error' });
});

if (process.env.NODE_ENV === 'production') {
  app.use(express.static(path.join(root, 'dist')));
  app.use((req, res, next) => req.method === 'GET' && req.accepts('html')
    ? res.sendFile(path.join(root, 'dist', 'index.html'))
    : next());
} else {
  const { createServer } = await import('vite');
  const vite = await createServer({
    root: path.join(root, 'INTERFACE'),
    server: { middlewareMode: true },
    appType: 'spa',
  });
  app.use(vite.middlewares);
}

const port = Number(process.env.PORT) || 5173;
app.listen(port, '127.0.0.1', () => console.log(`UzGeoData running at http://localhost:${port}`));
