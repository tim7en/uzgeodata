const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const browser = await chromium.launch({
    headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM || undefined,
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    // Basemap tiles are unrelated to symbol rendering and require external access.
    await page.route('https://**/*', route => route.abort());
    await page.goto(process.env.TEST_BASE_URL || 'http://127.0.0.1:5175');
    await page.locator('.land-level').waitFor();
    const glaciers = page.getByRole('checkbox', { name: /Glacier catalogues/ });
    const markers = page.locator('.land-glacier-mark');
    await glaciers.check();
    await markers.first().waitFor();
    await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
    await page.waitForTimeout(600);
    await markers.first().waitFor();
    await page.mouse.move(1000, 500);
    await page.mouse.down();
    await page.mouse.move(1100, 550, { steps: 10 });
    await page.mouse.up();
    await page.waitForTimeout(600);
    await markers.first().waitFor();
    await glaciers.uncheck();
    assert.equal(await markers.count(), 0);
    await glaciers.check();
    await markers.first().waitFor();
    for (const name of [/Lakes/, /Dams/, /Observations/]) {
      // The scrollable controls can sit beneath the fixed page header.
      await page.getByRole('checkbox', { name }).evaluate(input => input.click());
    }
    await page.locator('.land-lake-symbol').first().waitFor();
    await page.locator('.land-station-symbol').first().waitFor();
    assert.equal(await page.getByRole('heading', { name: 'This page stopped.' }).count(), 0);
    assert.deepEqual(errors.filter(error => !error.includes('net::ERR_FAILED')), []);
    console.log('Map symbols: enable, zoom, pan, re-enable and combined layers passed.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
