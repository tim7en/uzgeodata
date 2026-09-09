const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM || undefined});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:5186';
    await page.goto(`${base}/roadmap.html`, {waitUntil: 'domcontentloaded'});
    await page.getByText('Earlier single-attribute pilot runs', {exact: true}).click();
    const panel = page.getByRole('region', {name: 'Pilot attribute processing'});
    await panel.getByText('15/20 units within 1 m.', {exact: true}).waitFor();
    assert.match(await panel.textContent(), /independent scientific reproduction remains pending/);
    assert.equal(await panel.locator('tbody tr').count(), 8);
    await panel.locator('.attempts summary').click();
    assert.match(await panel.locator('.attempts').textContent(), /failed/);
    const download = await page.request.get(base + await panel.getByRole('link', {name: 'All pilot values and differences'}).getAttribute('href'));
    assert.equal(download.status(), 200);
    assert.equal((await download.text()).trim().split('\n').length, 21);
    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await panel.screenshot({path: 'tmp/atlas-processing-mobile.png'});
    // Simulate a later running attempt and verify polling preserves the earlier report.
    const real = await (await page.request.get(`${base}/data/atlas/processing-status.json`)).json();
    await page.route('**/data/atlas/processing-status.json', route => route.fulfill({json: {
      ...real, run_id: 'browser-poll-test', status: 'running', wall_seconds: 12.345,
      active_stage: {name: 'calculate_ele_mt_sav'}, stages: [],
    }}));
    await panel.locator('.processing-summary').getByText('12.345 s', {exact: true}).waitFor({timeout: 10000});
    await panel.getByRole('heading', {name: 'Latest completed comparison (earlier run)'}).waitFor();
    assert.deepEqual(errors, []);
    console.log('Atlas processing: timings, failure history, CSV, mobile layout and live polling passed');
  } finally {
    await browser.close();
  }
})().catch(error => {console.error(error); process.exit(1);});
