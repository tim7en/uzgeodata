// Publish the reviewed release's data tree to R2, the production data plane.
//
// GitHub carries the source, the pipelines and the reviewed public files; it is
// not the transport that gets data to readers. worker.js answers /data/* from the
// uzgeodata-public bucket, so a dataset only reaches the live site once it is in
// R2. Pushing to GitHub deploys the frontend and nothing else.
//
// What is published is dist/data, not PUBLISHED/data: build_launch.mjs validates
// every basin record, applies the git-tracked release allowlist, drops raw
// partitions and unpublished source geometry, and compacts the JSON. Syncing
// PUBLISHED/data directly would publish files the release deliberately withholds.
//
// Usage:
//   npm run publish:r2                   build the release, then sync it
//   npm run publish:r2 -- --dry-run      report the difference, upload nothing
//   npm run publish:r2 -- --skip-build   reuse an existing dist/data
//   npm run publish:r2 -- --prune        also delete objects the release dropped
//   npm run publish:r2 -- --prune --force   prune even a large share of the bucket
//   npm run publish:r2 -- --only=atlas/catchments/   restrict to one prefix
//
// Credentials come from .env (see .env.example). They are R2 S3-API tokens, not
// the wrangler OAuth login: the S3 API is the only one that can list a bucket,
// and listing is what makes this a sync rather than a blind re-upload of 1 GB.
import 'dotenv/config';
import { createHash, createHmac } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const source = path.join(root, 'dist/data');
const args = process.argv.slice(2);
const flag = name => args.includes(`--${name}`);
const option = name => args.find(arg => arg.startsWith(`--${name}=`))?.slice(name.length + 3);
const dryRun = flag('dry-run');
const prune = flag('prune');
const only = option('only') || '';
const concurrency = Number(option('concurrency') || 12);

function bucketFromWrangler() {
  try {
    // wrangler.jsonc permits comments; JSON.parse does not. No string in that file
    // contains // or /*, so stripping them line-wise is enough to read the name.
    const text = readFileSync(path.join(root, 'wrangler.jsonc'), 'utf8')
      .replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
    return JSON.parse(text).r2_buckets?.[0]?.bucket_name;
  } catch { return undefined; }
}

const account = process.env.R2_ACCOUNT_ID || process.env.CLOUDFLARE_ACCOUNT_ID;
const accessKeyId = process.env.R2_ACCESS_KEY_ID;
const secretAccessKey = process.env.R2_SECRET_ACCESS_KEY;
const bucket = process.env.R2_BUCKET || bucketFromWrangler() || 'uzgeodata-public';
if (!account || !accessKeyId || !secretAccessKey) {
  throw Error('Missing R2 credentials. Set R2_ACCOUNT_ID, R2_ACCESS_KEY_ID and '
    + 'R2_SECRET_ACCESS_KEY in .env. Create the token in the Cloudflare dashboard '
    + `under R2 → API → Manage API tokens, with Object Read & Write on ${bucket}. `
    + 'See docs/LAUNCH.md.');
}

const TYPES = {
  '.json': 'application/json',
  '.geojson': 'application/geo+json',
  '.csv': 'text/csv; charset=utf-8',
  '.tsv': 'text/tab-separated-values; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.pdf': 'application/pdf',
  '.zip': 'application/zip',
  '.parquet': 'application/vnd.apache.parquet',
};
// Content type is not cosmetic here: the catchment tab rejects a JSON response
// whose type does not say json. The .bin.gz matrices are decompressed by the page
// itself, so they are stored as application/gzip and never with
// content-encoding: gzip - the browser would then decompress them first and
// DecompressionStream would fail on plain bytes.
function contentType(key) {
  if (key.endsWith('.gz')) return 'application/gzip';
  return TYPES[path.extname(key).toLowerCase()] || 'application/octet-stream';
}

const EMPTY = createHash('sha256').update('').digest('hex');
const escape = text => encodeURIComponent(text)
  .replace(/[!'()*]/g, character => `%${character.charCodeAt(0).toString(16).toUpperCase()}`);

const endpoint = new URL(process.env.R2_ENDPOINT || `https://${account}.r2.cloudflarestorage.com`);

// Minimal SigV4 for the R2 S3 endpoint, checked request for request against
// botocore's signer. An SDK would be a large dependency for three request
// shapes: list, put, delete.
function signed({ method, key = '', query = {}, body = null, type = null }) {
  const host = endpoint.host;
  const stamp = new Date().toISOString().replace(/[:-]|\.\d{3}/g, '');
  const day = stamp.slice(0, 8);
  const payloadHash = body ? createHash('sha256').update(body).digest('hex') : EMPTY;
  const headers = { host, 'x-amz-content-sha256': payloadHash, 'x-amz-date': stamp };
  if (type) headers['content-type'] = type;
  const names = Object.keys(headers).sort();
  const canonicalHeaders = names.map(name => `${name}:${String(headers[name]).trim()}\n`).join('');
  const uri = `/${[bucket, ...(key ? key.split('/') : [])].map(escape).join('/')}`;
  const canonicalQuery = Object.keys(query).sort()
    .map(name => `${escape(name)}=${escape(query[name])}`).join('&');
  const canonicalRequest = `${method}\n${uri}\n${canonicalQuery}\n${canonicalHeaders}\n`
    + `${names.join(';')}\n${payloadHash}`;
  const scope = `${day}/auto/s3/aws4_request`;
  const toSign = `AWS4-HMAC-SHA256\n${stamp}\n${scope}\n`
    + createHash('sha256').update(canonicalRequest).digest('hex');
  let signing = Buffer.from(`AWS4${secretAccessKey}`, 'utf8');
  for (const part of [day, 'auto', 's3', 'aws4_request']) {
    signing = createHmac('sha256', signing).update(part).digest();
  }
  const signature = createHmac('sha256', signing).update(toSign).digest('hex');
  const sent = {
    ...headers,
    authorization: `AWS4-HMAC-SHA256 Credential=${accessKeyId}/${scope}, `
      + `SignedHeaders=${names.join(';')}, Signature=${signature}`,
  };
  delete sent.host; // fetch sets it itself and refuses the override.
  return {
    url: `${endpoint.origin}${uri}${canonicalQuery ? `?${canonicalQuery}` : ''}`,
    headers: sent,
  };
}

async function send(request, attempt = 0) {
  const { url, headers } = signed(request);
  let response;
  try {
    response = await fetch(url, { method: request.method, headers, body: request.body });
  } catch (error) {
    if (attempt >= 4) throw error;
    await new Promise(resolve => setTimeout(resolve, 500 * 2 ** attempt));
    return send(request, attempt + 1);
  }
  if ((response.status === 429 || response.status >= 500) && attempt < 4) {
    await response.arrayBuffer();
    await new Promise(resolve => setTimeout(resolve, 500 * 2 ** attempt));
    return send(request, attempt + 1);
  }
  if (!response.ok) {
    throw Error(`R2 ${request.method} ${request.key || '(list)'} failed: ${response.status} `
      + (await response.text()).slice(0, 400));
  }
  return response;
}

async function each(items, limit, visit) {
  const iterator = items[Symbol.iterator]();
  await Promise.all(Array.from({ length: limit }, async () => {
    for (let next = iterator.next(); !next.done; next = iterator.next()) await visit(next.value);
  }));
}

// Release keys are the site's own /data/ paths: dist/data/atlas/catalogue.json is
// published as atlas/catalogue.json, which worker.js serves at /data/atlas/catalogue.json.
async function local(directory = source, prefix = '') {
  const files = new Map();
  for (const item of await readdir(directory, { withFileTypes: true })) {
    const key = prefix ? `${prefix}/${item.name}` : item.name;
    if (item.isDirectory()) {
      if (!key.startsWith(only) && !only.startsWith(key)) continue;
      for (const [name, file] of await local(path.join(directory, item.name), key)) {
        files.set(name, file);
      }
    } else if (key.startsWith(only)) {
      files.set(key, path.join(directory, item.name));
    }
  }
  return files;
}

const unescapeXml = text => text.replace(/&quot;/g, '"').replace(/&apos;/g, "'")
  .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');

async function remote() {
  const objects = new Map();
  let token;
  do {
    const query = { 'list-type': '2', 'max-keys': '1000' };
    if (only) query.prefix = only;
    if (token) query['continuation-token'] = token;
    const xml = await (await send({ method: 'GET', query })).text();
    for (const [, block] of xml.matchAll(/<Contents>([\s\S]*?)<\/Contents>/g)) {
      objects.set(unescapeXml(block.match(/<Key>([\s\S]*?)<\/Key>/)[1]), {
        etag: unescapeXml(block.match(/<ETag>([\s\S]*?)<\/ETag>/)[1]).replaceAll('"', ''),
        bytes: Number(block.match(/<Size>(\d+)<\/Size>/)[1]),
      });
    }
    token = /<IsTruncated>true<\/IsTruncated>/.test(xml)
      ? unescapeXml(xml.match(/<NextContinuationToken>([\s\S]*?)<\/NextContinuationToken>/)[1])
      : undefined;
  } while (token);
  return objects;
}

if (!flag('skip-build')) {
  // The launch build is invoked as a script rather than through npm: Node refuses
  // to execFile a .cmd shim on Windows, which is where this command is run.
  execFileSync(process.execPath, [path.join(root, 'PIPELINES/build_launch.mjs')], {
    cwd: root,
    stdio: 'inherit',
    env: { ...process.env, SITE_BASE: process.env.SITE_BASE || '/' },
  });
}

const files = await local().catch(error => {
  if (error.code !== 'ENOENT') throw error;
  throw Error('dist/data is missing. Run without --skip-build, or run npm run build:launch '
    + 'first. build:cloudflare deletes dist/data by design: the Worker asset bundle must '
    + 'not carry the data a second time.');
});
if (!files.size) throw Error(`No files to publish under dist/data/${only}`);
const published = await remote();

const upload = [];
let unchanged = 0;
// Bodies are read twice - once to hash, once to send - rather than held. A full
// backfill is a gigabyte, and keeping it resident to save a second read of a
// warm file is the wrong trade.
for (const [key, file] of files) {
  const body = await readFile(file);
  const known = published.get(key);
  // A multipart ETag (hash-partcount) is not the object's MD5, so it cannot be
  // compared. Those objects - anything loaded through the dashboard - are
  // rewritten once, after which every ETag in the bucket is one this wrote.
  if (known && !known.etag.includes('-') && known.bytes === body.length
      && known.etag === createHash('md5').update(body).digest('hex')) {
    unchanged += 1;
    continue;
  }
  upload.push({ key, file, bytes: body.length, existed: Boolean(known) });
}
const stale = [...published.keys()].filter(key => !files.has(key));
// R2 keeps no object versions, so a deletion here is final. Pruning a quarter of
// the bucket at once is more likely a mistyped prefix or a half-built release than
// a real withdrawal, and that is worth having to say twice.
if (prune && !dryRun && !flag('force') && stale.length > published.size / 4) {
  throw Error(`--prune would delete ${stale.length} of ${published.size} objects. Check the `
    + 'release tree and the --only prefix, then re-run with --force if that is intended.');
}

const report = {
  bucket,
  source: 'dist/data',
  prefix: only || null,
  dry_run: dryRun,
  local_files: files.size,
  remote_objects: published.size,
  unchanged,
  upload: upload.length,
  upload_bytes: upload.reduce((total, item) => total + item.bytes, 0),
  added: upload.filter(item => !item.existed).length,
  replaced: upload.filter(item => item.existed).length,
  stale_remote: stale.length,
  pruned: 0,
  examples: { upload: upload.slice(0, 10).map(item => item.key), stale: stale.slice(0, 10) },
};

if (!dryRun) {
  let done = 0;
  await each(upload, concurrency, async item => {
    const body = await readFile(item.file);
    await send({ method: 'PUT', key: item.key, body, type: contentType(item.key) });
    done += 1;
    if (done % 250 === 0 || done === upload.length) {
      console.log(`Uploaded ${done}/${upload.length} objects.`);
    }
  });
  if (prune) {
    await each(stale, concurrency, async key => { await send({ method: 'DELETE', key }); });
    report.pruned = stale.length;
  }
}
if (stale.length && !prune) {
  console.log(`${stale.length} object(s) in R2 are no longer part of the release. They still `
    + 'answer requests. Re-run with --prune to delete them.');
}

// Kept out of dist/: that tree is the deployed Worker asset bundle, and an
// internal publication log is not part of the public site.
await mkdir(path.join(root, 'tmp'), { recursive: true });
await writeFile(path.join(root, 'tmp/r2-publish.json'), JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
