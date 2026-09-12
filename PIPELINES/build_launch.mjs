// Package saved public evidence only. Never run acquisition or publication here.
import { execFileSync } from 'node:child_process';
import { readFile, writeFile, mkdir, readdir, stat, copyFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'vite';

const root = fileURLToPath(new URL('../', import.meta.url));
process.chdir(root);
const base = process.env.SITE_BASE || '/';
if (!/^\/(?:[a-zA-Z0-9_-]+\/)*$/.test(base)) throw Error('SITE_BASE must be / or /path/');
process.env.LAUNCH_BUILD = '1';
const published = path.join(root, 'PUBLISHED');
const output = path.join(root, 'dist');
async function each(items, concurrency, visit) {
  const iterator = items[Symbol.iterator]();
  await Promise.all(Array.from({ length: concurrency }, async () => {
    for (let next = iterator.next(); !next.done; next = iterator.next()) await visit(next.value);
  }));
}
const index = JSON.parse(await readFile(path.join(published, 'data/atlas/basins/index.json')));
const history = JSON.parse(await readFile(path.join(published, 'data/atlas/history/index.json')));
const catalogue = JSON.parse(await readFile(path.join(published, 'data/atlas/catalogue.json')));
if (index.basins !== 7445 || Object.keys(index.by_basin).length !== 7445 || history.basins !== index.basins)
  throw Error('Launch requires all 7,445 basin records');
await each(Object.keys(index.by_basin), 8, async id => {
  const attributes = JSON.parse(await readFile(path.join(published, `data/atlas/basins/${id}.json`)));
  if (String(attributes.basin_id) !== id || attributes.original.length !== catalogue.attributes.length)
    throw Error(`Invalid attributes: ${id}`);
  const record = JSON.parse(await readFile(path.join(published, `data/atlas/history/${id}.json`)));
  if (String(record.basin_id) !== id || record.months !== 240) throw Error(`Invalid history: ${id}`);
  for (const name of Object.keys(history.series)) {
    const series = record.series[name];
    if (!series || series.values.length !== 240 || !series.method || !series.source_release)
      throw Error(`Incomplete history metadata: ${id}/${name}`);
    if (name === 'snw_pc_s' && series.trend_use !== 'withdrawn') throw Error('Snow trend restriction missing');
  }
});
console.log('Validated attributes and history for all 7,445 basins.');
await build();
await writeFile(path.join(output, 'portal.html'), `<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="0;url=${base}"><title>UzGeoData basin map</title>
</head><body><a href="${base}">Open the public basin map</a></body></html>`);

// Git's public-file list is the release allowlist. Raw partitions and untracked
// downloads cannot accidentally enter the artifact. History is checked above.
const files = new Set(execFileSync('git', ['ls-files', '-z', 'PUBLISHED'], { encoding: 'utf8', maxBuffer: 8e6 })
  .split('\0').filter(Boolean).map(file => file.slice('PUBLISHED/'.length)));
for (const name of await readdir(path.join(published, 'data/atlas/history'))) {
  if (/^(?:index|\d+)\.json$/.test(name)) files.add(`data/atlas/history/${name}`);
}
await each(files, 4, async relative => {
  if (relative.split('/').some(part => part.startsWith('time_kind=') || part.startsWith('.'))) return;
  const target = path.join(output, relative);
  await mkdir(path.dirname(target), { recursive: true });
  if (/\.(?:json|geojson)$/.test(relative)) {
    const data = JSON.parse(await readFile(path.join(published, relative), 'utf8'));
    await writeFile(target, JSON.stringify(data));
  } else await copyFile(path.join(published, relative), target);
});
console.log('Copied reviewed public files; checking deployment paths.');

// Saved catalogues as well as browser modules contain root-relative URLs.
// Rebase only known public namespaces/pages, never source URLs or identifiers.
const pages = (await readdir(output)).filter(name => name.endsWith('.html'));
const rewrite = text => base === '/' ? text : text
  .replace(/(["'`(=])\/(data|assets)\//g, `$1${base}$2/`)
  .replace(new RegExp(`(["'\x60(=])/(${pages.map(name => name.replace('.', '\\.')).join('|')})(?=[?#"'\x60)])`, 'g'), `$1${base}$2`)
  .replace(/(href[=:]\s*["'])\/(?=["'])/g, `$1${base}`);
let bytes = 0, count = 0;
async function finish(directory) {
  await each(await readdir(directory, { withFileTypes: true }), 4, async item => {
    const file = path.join(directory, item.name);
    if (item.isDirectory()) await finish(file);
    else {
      if (/\.(html|js|css|json|geojson)$/.test(item.name)) {
        const original = await readFile(file, 'utf8');
        const rebased = rewrite(original);
        if (rebased !== original) await writeFile(file, rebased);
      }
      const fileStat = await stat(file);
      bytes += fileStat.size;
      count++;
    }
  });
}
await finish(output);
if (bytes > 950e6) throw Error(`Release exceeds 950 MB budget: ${bytes}`);
const release = {
  status: 'public_preview', generated_at: new Date().toISOString(),
  commit: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
  base, basins: index.basins, history_years: history.years,
  history_generated_at: history.generated_at, variables: Object.keys(history.series),
  independently_reproduced: 0, snow_trend_use: 'withdrawn', files: count, bytes,
};
await writeFile(path.join(output, 'release.json'), JSON.stringify(release, null, 2));
await writeFile(path.join(output, '.nojekyll'), '');
console.log(JSON.stringify(release, null, 2));
