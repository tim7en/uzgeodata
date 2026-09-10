"""Real portal modal: exact basin joins, colours, filters, tab keys and fetch recovery."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get('ATLAS_TEST_URL', 'http://localhost:5173')
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1000}, locale='en-US')
    errors, requests = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: requests.append(request.url))

    def open_basin(bid):
        page.goto(BASE + '/', wait_until='domcontentloaded')
        page.locator('.land-level').wait_for()
        for _ in range(5):
            if 'Level 12' in page.locator('.land-level').inner_text():
                break
            page.get_by_role('button', name='Zoom in', exact=True).click()
            page.wait_for_timeout(450)
        page.locator('.land-level').filter(has_text='Level 12').wait_for()
        page.get_by_placeholder('HYBAS or PFAF id').fill(bid)
        page.locator('.land-results button').filter(has_text=bid).click()
        page.locator('.land-open-table').click()
        dialog = page.get_by_role('dialog', name='Atlas attributes for this basin')
        dialog.locator('tbody tr').first.wait_for()
        return dialog

    dialog = open_basin('4121289400')
    assert not any('/substitutes-index.json' in url for url in requests), 'Substitutes should load on tab activation'
    assert dialog.locator('tbody tr').count() == 281
    dialog.get_by_role('tab', name='Updated substitutes', exact=True).click()
    dialog.locator('.land-sub-table').wait_for()
    assert dialog.locator('[data-substitute-status=available]').count() == 196
    assert dialog.locator('.land-sub-updated').count() == 196
    assert dialog.locator('[data-substitute-status=pending] .land-sub-updated').count() == 0
    assert dialog.locator('.land-opportunity').count() > 0
    assert dialog.locator('.land-sub-updated').first.evaluate('(e)=>getComputedStyle(e).backgroundColor') == 'rgb(223, 243, 217)'
    dialog.get_by_placeholder('Attribute, category or column').fill('snw_pc_s01')
    assert dialog.locator('tbody tr').count() == 1
    assert '2003-01-01' in dialog.locator('tbody').inner_text()
    dialog.get_by_placeholder('Attribute, category or column').fill('')
    dialog.get_by_role('button', name='Upstream', exact=True).click()
    assert 0 < dialog.locator('tbody tr').count() < 281
    dialog.get_by_role('button', name='All', exact=True).click()
    dialog.get_by_role('tab', name='Updated substitutes').focus()
    page.keyboard.press('ArrowLeft')
    assert dialog.get_by_role('tab', name='HydroATLAS attributes').get_attribute('aria-selected') == 'true'
    assert dialog.locator('.land-sub-updated').count() == 0
    page.keyboard.press('ArrowRight')
    dialog.locator('.land-sub-table').wait_for()
    out = ROOT / 'WORKSPACE/derived/ui-review'
    out.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out / 'basin-substitutes-dark.png'))
    page.evaluate("document.documentElement.dataset.theme='light'")
    assert dialog.locator('.land-sub-updated').first.evaluate('(e)=>getComputedStyle(e).color') == 'rgb(34, 71, 43)'
    page.screenshot(path=str(out / 'basin-substitutes-light.png'))
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    page.screenshot(path=str(out / 'basin-substitutes-mobile.png'))
    page.set_viewport_size({'width': 1440, 'height': 1000})

    dialog.get_by_role('tab', name='HydroATLAS attributes').click()
    page.route('**/substitutes/*/4121289400.json', lambda route: route.fulfill(status=503, body='Unavailable'))
    dialog.get_by_role('tab', name='Updated substitutes').click()
    dialog.get_by_role('button', name='Retry substitutes').wait_for()
    page.unroute('**/substitutes/*/4121289400.json')
    dialog.get_by_role('button', name='Retry substitutes').click()
    dialog.locator('.land-sub-table').wait_for()

    dialog = open_basin('4120050220')
    dialog.get_by_role('tab', name='Updated substitutes').click()
    dialog.get_by_role('heading', name='No substitutes published for this basin yet.').wait_for()
    assert dialog.locator('.land-sub-updated').count() == 0

    page.goto(BASE + '/roadmap.html#implementation-plan', wait_until='domcontentloaded')
    page.locator('.plan-stages article').first.wait_for()
    assert page.locator('.plan-stages article').count() == 6
    assert 'Awaiting benchmark' in page.locator('.plan-calculators').inner_text()
    page.get_by_label('Monthly indicators').fill('10')
    page.get_by_label('Years', exact=True).fill('1')
    assert '893,400 rows' in page.locator('.plan-calculators').inner_text()
    page.get_by_label('Measured minutes per batch').fill('10')
    assert '~6.3 hours' in page.locator('.plan-calculators').inner_text()
    page.screenshot(path=str(out / 'implementation-plan-desktop.png'))
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    page.screenshot(path=str(out / 'implementation-plan-mobile.png'))
    assert not errors, errors
    browser.close()
print('Basin substitutes and six-stage roadmap: browser checks passed.')
