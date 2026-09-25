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
    await page.locator('.land-level').waitFor({ state: 'attached' });
    const headerToggle = page.getByRole('button', { name: 'Toggle map header' });
    const panelToggle = page.getByRole('button', { name: 'Toggle basins panel' });
    assert.equal(await headerToggle.getAttribute('aria-expanded'), 'false');
    assert.equal(await panelToggle.getAttribute('aria-expanded'), 'false');
    await headerToggle.click();
    await page.mouse.move(1000, 500);
    assert.equal(await headerToggle.getAttribute('aria-expanded'), 'true');
    await headerToggle.click();
    await page.mouse.move(1000, 500);
    assert.equal(await headerToggle.getAttribute('aria-expanded'), 'false');
    await panelToggle.click();
    await page.mouse.move(1000, 500);
    await page.waitForTimeout(700);
    assert.equal(await panelToggle.getAttribute('aria-expanded'), 'true');
    await panelToggle.click();
    await page.mouse.move(1000, 500);
    await page.waitForTimeout(700);
    assert.equal(await panelToggle.getAttribute('aria-expanded'), 'false');
    const glaciers = page.getByRole('checkbox', { name: /Glacier catalogues/ });
    const markers = page.locator('.land-glacier-mark');
    await glaciers.check();
    await markers.first().waitFor();
    async function openGlacier() {
      for (let i = 0; i < await markers.count(); i++) {
        const marker = markers.nth(i), box = await marker.boundingBox();
        if (box && box.x > 300 && box.x < 1300 && box.y > 200 && box.y < 700) {
          await marker.click();
          await page.getByRole('dialog').waitFor();
          return;
        }
      }
      throw Error('No glacier marker available to click');
    }
    await openGlacier();
    const dialog = page.getByRole('dialog');
    await dialog.getByRole('heading', { name: 'Source', exact: true }).waitFor();
    assert.ok(await dialog.getByText('Perimeter (m)', { exact: true }).count());
    const recordPicker = dialog.getByLabel('Glacier record');
    if (await recordPicker.count()) {
      await recordPicker.selectOption('1');
      assert.equal(await recordPicker.inputValue(), '1');
    }
    await page.keyboard.press('Escape');
    await dialog.waitFor({ state: 'detached' });
    await openGlacier();
    await dialog.getByRole('button', { name: 'Close', exact: true }).click();
    await dialog.waitFor({ state: 'detached' });
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
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.locator('#map-header').isVisible(), true);
    assert.equal(await page.locator('.land-finder').isVisible(), true);
    const size = await page.evaluate(() => [innerWidth, document.documentElement.scrollWidth]);
    assert.ok(size[1] <= size[0], 'No mobile horizontal overflow');
    // Deterministic records cover both catalogue schemas and grouped/single marks.
    const fs = require('node:fs');
    const path = require('node:path');
    const fixture = name => JSON.parse(fs.readFileSync(path.join(__dirname,
      `../PUBLISHED/data/hydroclimate/${name}-glaciers.geojson`), 'utf8'));
    const regional = fixture('regional'), pskem = fixture('pskem');
    regional.features = regional.features.slice(0, 1);
    regional.features[0].geometry.coordinates = [73, 40.2];
    pskem.features = pskem.features.slice(0, 2);
    pskem.features.forEach(feature => { feature.geometry.coordinates = [70.5, 40.2]; });
    for (const [name, data] of [['regional', regional], ['pskem', pskem]]) {
      await page.route(`**/${name}-glaciers.geojson`, route => route.fulfill({ json: data }));
    }
    await page.evaluate(() => localStorage.removeItem('uzgeodata.mapView'));
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.reload();
    await glaciers.check();
    await page.locator('.land-glacier-mark[title="2 glaciers"]').click();
    await dialog.getByText('This catalogue does not report area.', { exact: false }).waitFor();
    await dialog.getByLabel('Glacier record').selectOption('1');
    const second = pskem.features[1].properties;
    await dialog.getByRole('heading', { name: second.name_en || second.name || `Glacier ${second.glacier_key}`, exact: true }).waitFor();
    assert.ok((await dialog.getByRole('link', { name: /Download source/ }).getAttribute('href')).includes('pskem'));
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await dialog.isVisible());
    const modalSize = await dialog.locator('.dam-modal-card').evaluate(el => [el.clientWidth, el.scrollWidth]);
    assert.ok(modalSize[1] <= modalSize[0], 'Glacier modal fits mobile width');
    await dialog.getByRole('button', { name: 'Close', exact: true }).click();
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.locator('.land-glacier-mark[title="1"]').click();
    assert.equal(await dialog.getByLabel('Glacier record').count(), 0);
    await dialog.getByText('0.1758', { exact: true }).waitFor();
    assert.ok((await dialog.getByRole('link', { name: /Download source/ }).getAttribute('href')).includes('regional'));
    await dialog.click({ position: { x: 5, y: 5 } });
    await dialog.waitFor({ state: 'detached' });
    assert.deepEqual(errors.filter(error => !error.includes('net::ERR_FAILED')), []);
    console.log('Map symbols, glacier details, collapsible navigation and mobile layout passed.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
