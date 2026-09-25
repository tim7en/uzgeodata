const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { gzipSync } = require('node:zlib');
const { createHash } = require('node:crypto');
const { unzipSync, strFromU8 } = require('fflate');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM || undefined });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    const polygon = (id, x) => ({ type: 'Feature', properties: { hybas_id: id, basin_level: 12, area_km2: id, next_down: id === 1 ? 0 : 1 },
      geometry: { type: 'Polygon', coordinates: [[[x, 40], [x + 1, 40], [x + 1, 41], [x, 41], [x, 40]]] } });
    const geometry = { type: 'FeatureCollection', features: [polygon(1, 70), polygon(2, 71), polygon(3, 72)] };
    const bytes = Buffer.alloc(3 * 12 * 4);
    for (let basin = 0; basin < 3; basin++) for (let plane = 0; plane < 4; plane++) bytes[plane * 36 + basin * 12] = ((basin + 1) * 100 >>> (plane * 8)) & 255;
    const compressed = gzipSync(bytes);
    const index = { ids: [1, 2, 3], next_down: [0, 1, 1], areas_km2: [1, 2, 3], months: 12, years: [2020, 2020], scale: 10,
      null_sentinel: -2147483648, encoding: 'gzip-byte-shuffled-delta-int32-le-basin-major', morphology_url: '/poi-morphology.json',
      series: { pre_mm_s: { url: '/poi-matrix.bin.gz', sha256: createHash('sha256').update(compressed).digest('hex'),
        meta: { label: 'Precipitation', unit: 'millimetres per month', source_release: 'Test source' }, provenance_ids: [0, 0, 0], provenance: [{ source: 'Test source' }] } } };
    const ladder = JSON.parse(fs.readFileSync(path.join(__dirname, '../PUBLISHED/data/hydroclimate/reference-basin-levels.json')));
    const level12 = ladder.levels.find(entry => entry.level === 12).url;
    await page.route('https://**/*', route => route.abort());
    await page.route(`**${level12}`, route => route.fulfill({ json: geometry }));
    await page.route('**/data/atlas/catchments/index.json', route => route.fulfill({ json: index }));
    await page.route('**/poi-matrix.bin.gz', route => route.fulfill({ body: compressed, contentType: 'application/octet-stream' }));
    await page.route('**/poi-morphology.json', route => route.fulfill({ json: { basins: { 1: { traced_area_km2: 6, reported_upstream_area_km2: 6 } }, notes: ['Test method'] } }));
    await page.route('**/data/atlas/catalogue.json', route => route.fulfill({ json: { attributes: ['pre_mm_syr'], meta: { pre_mm_syr: { label: 'Annual precipitation', unit: 'mm', support: 's', original: {}, substitute: {} } } } }));
    await page.route(/\/data\/atlas\/basins\/[123]\.json$/, route => {
      const id = route.request().url().match(/(\d+)\.json$/)[1];
      return route.fulfill({ json: { basin_id: id, area_km2: Number(id), original: [123], substitute: [120] } });
    });
    await page.goto(process.env.TEST_BASE_URL || 'http://127.0.0.1:5175');
    await page.getByRole('button', { name: /Upload points or polygons/ }).click();
    const dialog = page.getByRole('dialog', { name: 'Upload & basin reports' });
    const upload = dialog.getByLabel('Upload locations');
    await upload.setInputFiles({ name: 'locations.csv', mimeType: 'text/csv', buffer: Buffer.from('name,longitude,latitude\nТочка,70.5,40.5\nOutside,0,0\nNear,69.999,40.5') });
    const report = dialog.getByRole('article', { name: 'Location basin report' });
    await report.waitFor();
    assert.match(await report.textContent(), /23.33/);
    async function download(button, extension) {
      const pending = page.waitForEvent('download');
      await dialog.getByRole('button', { name: button, exact: true }).click();
      const result = await pending;
      assert.ok(result.suggestedFilename().endsWith(extension));
      const filename = await result.path();
      return fs.readFileSync(filename);
    }
    const pdf = await download('Download PDF', '.pdf');
    assert.equal(pdf.subarray(0, 5).toString(), '%PDF-');
    assert.ok(pdf.length > 10000);
    const zip = unzipSync(await download('Report & data (ZIP)', '.zip'));
    for (const file of ['report.pdf', 'report.json', 'input.geojson', 'matched-basins.geojson', 'upstream-basins.geojson', 'monthly-statistics.csv', 'basin-attributes.csv', 'attribute-dictionary.csv']) assert.ok(zip[file], file);
    const data = JSON.parse(strFromU8(zip['report.json']));
    assert.deepEqual(data.local.ids, ['1']); assert.deepEqual(data.upstream.ids, ['1', '2', '3']);
    assert.equal(data.name, 'Точка'); assert.equal(data.upstream.rows[0].mean_observed_area, 140 / 6);
    await dialog.getByLabel('Location report').selectOption('1');
    await dialog.getByText(/No basin matches this location/).waitFor();
    assert.equal(await report.count(), 0);
    await dialog.getByLabel('Location report').selectOption('2'); await report.waitFor();
    await dialog.getByText('snapped', { exact: true }).waitFor();
    await dialog.getByLabel('Maximum point snap distance').selectOption('0');
    await dialog.getByText(/No basin matches this location/).waitFor();
    await upload.setInputFiles({ name: 'invalid.csv', mimeType: 'text/csv', buffer: Buffer.from('longitude,latitude\n,40') });
    await dialog.getByRole('alert').filter({ hasText: 'missing fields' }).waitFor();
    const inputPolygon = polygon(100, 70.5); inputPolygon.properties = { name: 'Polygon report' };
    await upload.setInputFiles({ name: 'area.geojson', mimeType: 'application/geo+json', buffer: Buffer.from(JSON.stringify(inputPolygon)) });
    await report.waitFor();
    const polygonReport = JSON.parse((await download('Download JSON', '.json')).toString());
    assert.deepEqual(polygonReport.local.ids, ['1', '2']);
    assert.deepEqual(polygonReport.upstream.ids, ['1', '2', '3']);
    assert.equal(polygonReport.morphology, null);
    await page.setViewportSize({ width: 390, height: 844 });
    const width = await dialog.locator('.dam-modal-card').evaluate(el => [el.clientWidth, el.scrollWidth]);
    assert.ok(width[1] <= width[0], 'Mobile modal has no horizontal overflow');
    fs.mkdirSync('tmp', { recursive: true });
    await page.screenshot({ path: 'tmp/poi-report-mobile.png' });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.screenshot({ path: 'tmp/poi-report-desktop.png' });
    await page.keyboard.press('Escape'); await dialog.waitFor({ state: 'detached' });
    await page.route('**/poi-matrix.bin.gz', route => route.fulfill({ body: Buffer.from('corrupt'), contentType: 'application/octet-stream' }));
    await page.reload();
    await page.getByRole('button', { name: /Upload points or polygons/ }).click();
    await upload.setInputFiles({ name: 'retry.csv', mimeType: 'text/csv', buffer: Buffer.from('longitude,latitude\n70.5,40.5') });
    await dialog.getByRole('alert').filter({ hasText: 'integrity check' }).waitFor();
    assert.equal(await report.count(), 0);
    await page.route('**/poi-matrix.bin.gz', route => route.fulfill({ body: compressed, contentType: 'application/octet-stream' }));
    await dialog.getByRole('button', { name: 'Retry report', exact: true }).click();
    await report.waitFor();
    await dialog.getByText('Matched basin attributes', { exact: true }).click();
    await dialog.getByLabel('Attribute basin').waitFor();
    await dialog.getByRole('button', { name: 'Close', exact: true }).click();
    await dialog.waitFor({ state: 'detached' });
    assert.deepEqual(errors, []);
    console.log('POI browser: CSV/polygon uploads, per-location reports, snap limits, invalid input, PDF/ZIP/JSON, mobile and closing passed.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
