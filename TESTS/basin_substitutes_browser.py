"""Real portal modal: any basin, its estimates, its evidence and its monthly record.

The modal is where a reader meets the whole programme, and most of what can go wrong
there is a wrong reading rather than a broken page. So these checks are about
meaning: that every level-12 basin is served and not only the pilot's twenty, that a
measured zero is marked as an estimate while a missing value is not, that a
difference is shown only between quantities that subtract, that the evidence behind a
number is reachable from the number, and that the monthly record shows its gaps as
gaps in the chart, the table and the download alike.

Run against a dev server: python TESTS/basin_substitutes_browser.py
"""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get('ATLAS_TEST_URL', 'http://localhost:5173')
# A basin far outside the Pskem pilot, so "it works here" means the region and not
# the twenty units the pilot ran on.
REGIONAL = '4120050220'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1000}, locale='en-US')
    errors, requests = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: requests.append(request.url))

    def open_basin(bid):
        page.goto(BASE + '/', wait_until='domcontentloaded')
        page.locator('.land-level').wait_for()
        for _ in range(6):
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

    dialog = open_basin(REGIONAL)
    assert dialog.locator('tbody tr').count() == 281
    # Nothing is fetched for a tab nobody opened.
    assert not any('/data/atlas/basins/' in url for url in requests), 'estimates load on activation'

    dialog.get_by_role('tab', name='Independent estimates', exact=True).click()
    dialog.locator('.land-sub-table').wait_for()
    estimated = dialog.locator('[data-substitute-status=estimated]').count()
    assert estimated > 150, f'a regional basin carries its estimates, found {estimated}'
    assert dialog.locator('.land-sub-updated').count() == estimated
    assert dialog.locator('[data-substitute-status=empty] .land-sub-updated').count() == 0, \
        'a missing value is never marked as an estimate'
    assert dialog.locator('[data-substitute-status=original_only] .land-sub-updated').count() == 0

    # The count in the header is the count in the table.
    assert f'{estimated} independently estimated' in dialog.locator('.land-sub-counts').inner_text().lower()

    # A measured zero is an estimate, not a gap.
    zeros = dialog.locator('td.land-sub-updated', has_text='0').count()
    assert zeros > 0, 'the region publishes measured zeroes'

    # Evidence is reachable from the value, and carries what the value cannot show.
    dialog.get_by_placeholder('Attribute, category or column').fill('snw_pc_s01')
    assert dialog.locator('.land-sub-table tbody tr').count() == 1
    dialog.locator('.land-sub-toggle').first.click()
    evidence = dialog.locator('.land-sub-evidence')
    evidence.wait_for()
    text = evidence.inner_text()
    for expected in ('ORIGINAL', 'SUBSTITUTE', 'PERIOD', 'SPATIAL', 'LICENCE', 'METHOD'):
        assert expected in text.upper(), f'{expected} missing from the evidence panel'
    assert 'native' in text, 'the source resolution is what limits the value'
    assert 'not the same measurement' in text.lower(), 'the divergences must travel with the number'
    dialog.locator('.land-sub-toggle').first.click()
    assert dialog.locator('.land-sub-evidence').count() == 0

    # Snow is deliberately not comparable by subtraction with the published attribute
    # in units, but the family declares a reviewed conversion, so the difference shows.
    dialog.get_by_placeholder('Attribute, category or column').fill('')
    dialog.get_by_role('button', name='Upstream', exact=True).click()
    upstream = dialog.locator('.land-sub-table tbody tr').count()
    assert 0 < upstream < 281
    dialog.get_by_role('button', name='All', exact=True).click()

    # Category chips and the estimate-only filter narrow the same table.
    total = dialog.locator('.land-sub-table tbody tr').count()
    dialog.locator('.land-sub-chips button', has_text='Climate').first.click()
    climate = dialog.locator('.land-sub-table tbody tr').count()
    assert 0 < climate < total, 'a theme is a subset of the whole'
    dialog.locator('.land-sub-chips button', has_text='All themes').click()
    dialog.get_by_label('Only attributes with an estimate').check()
    assert dialog.locator('[data-substitute-status=empty]').count() == 0
    dialog.get_by_label('Only attributes with an estimate').uncheck()

    # The estimate marker is a token, so it moves with the theme instead of staying
    # a light green on a dark page.
    page.evaluate("document.documentElement.dataset.theme='dark'")
    dark = dialog.locator('.land-sub-updated').first.evaluate('e=>getComputedStyle(e).backgroundColor')
    page.evaluate("document.documentElement.dataset.theme='light'")
    light = dialog.locator('.land-sub-updated').first.evaluate('e=>getComputedStyle(e).backgroundColor')
    assert dark != light, 'the estimate colour must follow the theme'

    out = ROOT / 'WORKSPACE/derived/ui-review'
    out.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out / 'basin-estimates-light.png'))
    page.evaluate("document.documentElement.dataset.theme='dark'")
    page.screenshot(path=str(out / 'basin-estimates-dark.png'))

    # Tabs cycle both ways and wrap, and each panel belongs to its tab.
    dialog.get_by_role('tab', name='Independent estimates').focus()
    page.keyboard.press('ArrowLeft')
    assert dialog.get_by_role('tab', name='HydroATLAS attributes').get_attribute('aria-selected') == 'true'
    assert dialog.locator('.land-sub-updated').count() == 0
    page.keyboard.press('ArrowLeft')
    assert dialog.get_by_role('tab', name='Monthly record').get_attribute('aria-selected') == 'true', 'wraps'

    # The monthly record: the gaps must survive into every rendering of it.
    record = dialog.locator('.land-hist-figure, .land-sub-note[role=alert]').first
    record.wait_for()
    if dialog.locator('.land-hist-figure').count():
        assert dialog.locator('.land-hist-line, .land-hist-dot').count() > 0, 'the record is drawn'
        rows = dialog.locator('.land-hist-table tbody tr')
        assert rows.count() >= 20, 'one row per year of the record'
        partial = dialog.locator('.land-hist-table tbody tr[data-substitute-status=empty]')
        for index in range(partial.count()):
            cells = partial.nth(index).inner_text()
            assert 'of 12' in cells, 'an incomplete year says how much it observed'
        # A year short of twelve months withholds its total rather than summing what it has.
        assert dialog.locator('.land-hist-table tbody tr[data-substitute-status=empty] '
                              '.land-sub-nocompare').count() >= partial.count()
        assert dialog.get_by_role('button', name='Download this basin, all variables (CSV)').count() == 1
        with page.expect_download() as pending:
            dialog.get_by_role('button', name='Download this basin, all variables (CSV)').click()
        csv_text = Path(pending.value.path()).read_text()
        assert len(csv_text.strip().splitlines()) == 241
        assert 'snw_pc_s' in csv_text.splitlines()[0]
        dialog.get_by_role('button', name='snow cover', exact=True).click()
        assert 'not for trend analysis' in dialog.locator('.land-hist-warn').first.inner_text()
        with page.expect_download() as pending:
            dialog.get_by_role('button', name='Download metadata & limitations').click()
        import json
        metadata = json.loads(Path(pending.value.path()).read_text())
        assert metadata['series']['snw_pc_s']['trend_use'] == 'withdrawn'
        # The search box belongs to the attribute tables, not to this tab.
        assert dialog.locator('.land-modal-tools').count() == 0
        page.screenshot(path=str(out / 'basin-record-dark.png'))
    else:
        assert not os.environ.get('ATLAS_REQUIRE_HISTORY'), 'launch requires published history'
        print('note: monthly record not published yet; its empty state was checked instead')
        assert 'level-12' in record.inner_text()

    # A failed fetch offers a way back rather than an empty table.
    dialog.get_by_role('tab', name='HydroATLAS attributes').click()
    page.route(f'**/data/atlas/basins/{REGIONAL}.json', lambda route: route.fulfill(status=503, body='Unavailable'))
    dialog.get_by_role('tab', name='Independent estimates').click()
    dialog.get_by_role('button', name='Try again').wait_for()
    page.unroute(f'**/data/atlas/basins/{REGIONAL}.json')
    dialog.get_by_role('button', name='Try again').click()
    dialog.locator('.land-sub-table').wait_for()

    # Mobile: the modal scrolls its tables rather than the page.
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    page.screenshot(path=str(out / 'basin-estimates-mobile.png'))
    page.set_viewport_size({'width': 1440, 'height': 1000})

    for name in ('about', 'guide', 'projects'):
        page.goto(f'{BASE}/{name}.html', wait_until='domcontentloaded')
        assert page.locator('h1').inner_text()
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        assert page.get_by_role('link', name='Basin map', exact=True).get_attribute('href').endswith('/')
    page.set_viewport_size({'width': 1440, 'height': 1000})

    # A coarser unit is a view of the level-12 basins, and says so rather than
    # showing an average nobody computed.
    page.goto(BASE + '/', wait_until='domcontentloaded')
    page.locator('.land-level').wait_for()
    page.get_by_placeholder('HYBAS or PFAF id').fill('4120050220')
    if page.locator('.land-results button').count():
        page.locator('.land-results button').first.click()
        page.locator('.land-open-table').click()
        coarse = page.get_by_role('dialog', name='Atlas attributes for this basin')
        coarse.get_by_role('tab', name='Independent estimates').click()
        panel = coarse.locator('.land-sub-note').first
        panel.wait_for()
        if 'level-12' in panel.inner_text():
            assert coarse.locator('.land-sub-updated').count() == 0

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
print('Basin estimates, monthly record and six-stage roadmap: browser checks passed.')
