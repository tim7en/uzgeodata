import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../worker.js';
import { json } from '../INTERFACE/catchmentData.js';

test('report manifests revalidate even a previously cached response with a long lifetime', async t => {
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, '/data/atlas/catchments/index.json');
    assert.equal(options.cache, 'no-cache');
    return Response.json({ through: '2025-12' });
  });
  assert.deepEqual(await json('/data/atlas/catchments/index.json'), { through: '2025-12' });
});

test('mutable data revalidate while compressed matrices stay cacheable', async () => {
  const env = { DATA: { get: async () => ({
    body: '{}', httpEtag: '"current-release"',
    writeHttpMetadata: headers => headers.set('content-type', 'application/json'),
  }) } };
  for (const name of ['atlas/catchments/index.json', 'atlas/climate-continuation/basins/4121262730.json']) {
    const response = await worker.fetch(new Request(`https://uzgeodata.uz/data/${name}`), env);
    assert.equal(response.headers.get('cache-control'), 'public, no-cache');
    assert.equal(response.headers.get('etag'), '"current-release"');
  }
  const response = await worker.fetch(new Request('https://uzgeodata.uz/data/atlas/catchments/pre-820afd66f08f.bin.gz'), env);
  assert.equal(response.headers.get('cache-control'), 'public, max-age=3600');
});
