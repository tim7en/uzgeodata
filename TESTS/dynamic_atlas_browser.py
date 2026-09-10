"""Exercise saved values, crosswalk filters, downloads, mobile layout and fetch errors."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get('ATLAS_TEST_URL', 'http://localhost:5173')
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(BASE + '/dynamic-atlas.html', wait_until='networkidle')
    page.get_by_role('heading', name='Inspect the results for every pilot basin.').wait_for()
    assert page.locator('.families > details').count() == 56
    assert page.locator('#results tbody tr').count() == 20
    page.get_by_label('Search sources or attributes').fill('snw')
    assert page.locator('.families > details').count() == 1
    page.locator('.families summary').click()
    assert '2003-01-01 ≤ date < 2023-01-01' in page.locator('.family-content').inner_text()
    page.get_by_label('Attribute', exact=True).select_option('gla_pc_sse')
    assert page.locator('#results tbody tr').count() == 20
    assert page.locator('#results tbody td').nth(0).inner_text() == '0'
    page.get_by_label('Search sources or attributes').fill('')
    page.get_by_label('Evidence', exact=True).select_option('gaps')
    assert 0 < page.locator('.families > details').count() < 56
    page.get_by_label('Evidence', exact=True).select_option('all')
    for link in page.locator('.downloads a').all():
        assert page.request.get(BASE + link.get_attribute('href')).ok
    out = ROOT / 'WORKSPACE/derived/ui-review'
    out.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out / 'dynamic-atlas-desktop.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    page.screenshot(path=str(out / 'dynamic-atlas-mobile.png'), full_page=True)
    page.route('**/dynamic-atlas.json', lambda route: route.fulfill(status=503, body='Unavailable'))
    page.reload(wait_until='networkidle')
    page.get_by_role('button', name='Try again').wait_for()
    page.unroute('**/dynamic-atlas.json')
    page.get_by_role('button', name='Try again').click()
    page.locator('.families > details').first.wait_for()
    assert not errors, errors
    browser.close()
print('Dynamic atlas: filters, 20-basin values, downloads, mobile and error recovery passed.')
