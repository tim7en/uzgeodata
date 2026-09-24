// Build the reviewed public release, then remove the data payload from the
// Worker static-assets bundle. Production /data/* requests are served from R2
// by worker.js, so shipping the same ~1 GB twice is both wasteful and over the
// static-hosting limits.
//
// This intentionally delegates validation and release metadata generation to
// build_launch.mjs so GitHub Pages and Cloudflare package the same reviewed
// scientific release.
import { execFileSync } from 'node:child_process';
import { readFile, writeFile, rm, readdir, stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const output = path.join(root, 'dist');
const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';

execFileSync(npm, ['run', 'build:launch'], {
  cwd: root,
  stdio: 'inherit',
  env: { ...process.env, SITE_BASE: process.env.SITE_BASE || '/' },
});

// R2 is the production data plane. Keep only the UI/static shell in the
// Workers Static Assets deployment.
await rm(path.join(output, 'data'), { recursive: true, force: true });

let files = 0;
let bytes = 0;
let largest = { path: '', bytes: 0 };

async function measure(directory) {
  for (const item of await readdir(directory, { withFileTypes: true })) {
    const file = path.join(directory, item.name);
    if (item.isDirectory()) {
      await measure(file);
      continue;
    }
    const info = await stat(file);
    const relative = path.relative(output, file).replaceAll('\\', '/');
    files += 1;
    bytes += info.size;
    if (info.size > largest.bytes) largest = { path: relative, bytes: info.size };
  }
}

await measure(output);

// Guard the Cloudflare free-plan static-asset constraints before deployment.
// R2-held data are deliberately excluded from these counts.
if (files > 20_000) {
  throw new Error(`Cloudflare frontend exceeds 20,000 static assets: ${files}`);
}
if (largest.bytes > 25 * 1024 * 1024) {
  throw new Error(
    `Cloudflare frontend asset exceeds 25 MiB: ${largest.path} (${largest.bytes} bytes)`,
  );
}

const releaseFile = path.join(output, 'release.json');
const release = JSON.parse(await readFile(releaseFile, 'utf8'));
release.hosting = {
  frontend: 'cloudflare_workers_static_assets',
  data: 'cloudflare_r2',
  r2_bucket: 'uzgeodata-public',
  frontend_files: files,
  frontend_bytes: bytes,
};
await writeFile(releaseFile, JSON.stringify(release, null, 2));

console.log(JSON.stringify({
  cloudflare_frontend_files: files,
  cloudflare_frontend_bytes: bytes,
  largest_frontend_asset: largest,
  data_served_from: 'R2/uzgeodata-public',
}, null, 2));
