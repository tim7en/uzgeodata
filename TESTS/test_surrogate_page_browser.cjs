const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM || undefined});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:5186';
    await page.goto(`${base}/surrogates.html`, {waitUntil: 'domcontentloaded'});
    const record = await (await page.request.get(`${base}/data/atlas/surrogate-science.json`)).json();

    await page.getByRole('heading', {name: 'What we built beside the atlas.'}).waitFor();
    const text = await page.textContent('main');
    assert.match(text, /never a reproduction/i);
    assert.match(text, /No attribute has passed the independent scientific reproduction gate/);
    assert.match(text, new RegExp(`${record.domain.basins.toLocaleString('en-US')}`));

    // Every family is listed, and the filters partition them the way the record does.
    assert.equal(await page.locator('.attributes > details').count(), record.families.length);
    await page.getByLabel('Show', {exact: true}).selectOption('estimated');
    assert.equal(await page.locator('.attributes > details').count(),
      record.families.filter(f => f.estimated_attributes > 0).length);
    await page.getByLabel('Show', {exact: true}).selectOption('pending');
    assert.equal(await page.locator('.attributes > details').count(),
      record.families.filter(f => f.estimated_attributes < f.attributes).length);
    await page.getByLabel('Show', {exact: true}).selectOption('all');
    await page.getByLabel('Search', {exact: true}).fill('GLIMS');
    assert.equal(await page.locator('.attributes > details').count(), 1);
    await page.locator('.attributes summary').first().click();
    assert.match(await page.textContent('.attributes .recipe'), /processing grid 15 arc-seconds/);

    // The scale section must show the measurement and the extrapolation as different things.
    assert.match(text, /Measured at full extent on this machine/);
    assert.match(text, /Acquisition is the uncertain half/);

    const registry = await page.request.get(base + await page.getByRole('link', {name: /Per-attribute registry/}).getAttribute('href'));
    assert.equal(registry.status(), 200);
    assert.equal((await registry.text()).trim().split('\n').length, 282);

    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.screenshot({path: 'tmp/surrogate-science-mobile.png', fullPage: true});
    assert.deepEqual(errors, []);
    console.log(`Surrogate science page: ${record.families.length} families, filters, limits, downloads and mobile passed`);
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
