const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM || undefined});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:5186';
    await page.goto(`${base}/roadmap.html`, {waitUntil: 'domcontentloaded'});
    const panel = page.getByRole('region', {name: 'Pskem 281 attribute processing'});
    await panel.getByText('281 of 281 attributes', {exact: false}).waitFor();
    assert.equal(await panel.locator('.attributes > details').count(), 281);
    const batch = await (await page.request.get(`${base}/data/atlas/batch-latest.json`)).json();
    await panel.getByLabel('Readiness', {exact: true}).selectOption('computed');
    assert.equal(await panel.locator('.attributes > details').count(), batch.candidate_attributes);
    await panel.getByLabel('Readiness', {exact: true}).selectOption('surrogate');
    assert.equal(await panel.locator('.attributes > details').count(), batch.surrogate_attributes);
    await panel.getByLabel('Readiness', {exact: true}).selectOption('none');
    assert.equal(await panel.locator('.attributes > details').count(), batch.attributes_without_any_estimate);
    await panel.getByLabel('Readiness', {exact: true}).selectOption('all');
    await panel.getByLabel('Search', {exact: true}).fill('tmp_dc_syr');
    assert.equal(await panel.locator('.attributes > details').count(), 1);
    await panel.locator('.attributes summary').click();
    assert.match(await panel.textContent(), /WorldClim V1 mirror needs exact v1.4 vintage review/);
    await panel.getByLabel('Search', {exact: true}).fill('slp_dg_sav');
    await panel.locator('.attributes summary').click();
    const slope = await panel.locator('.surrogate').textContent();
    assert.match(slope, /Open surrogate \(original source family\)/);
    assert.match(slope, /processing grid 15 arc-seconds/);
    assert.match(slope, /not a test/);
    const registry = await page.request.get(base + await panel.getByRole('link', {name: 'Surrogate sources and resolutions'}).getAttribute('href'));
    assert.equal(registry.status(), 200);
    assert.equal((await registry.text()).trim().split('\n').length, 282);
    await panel.getByLabel('Search', {exact: true}).fill('');
    const csv = await page.request.get(base + await panel.getByRole('link', {name: 'All basin observations'}).getAttribute('href'));
    assert.equal(csv.status(), 200);
    assert.equal((await csv.text()).trim().split('\n').length, 5621);
    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.screenshot({path: 'tmp/pskem-all281-mobile.png', fullPage: true});
    const status = await (await page.request.get(`${base}/data/atlas/batch-status.json`)).json();
    await page.route('**/data/atlas/batch-status.json', route => route.fulfill({json: {
      ...status, status: 'running', wall_seconds: 12.34, active_stage: {name: 'next_attribute'},
    }}));
    await panel.getByRole('status').filter({hasText: 'next attribute'}).waitFor({timeout: 10000});
    assert.deepEqual(errors, []);
    console.log('Pskem batch: 281 rows, filters, source caveats, full CSV, mobile and live progress passed');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
