"""Explicit browser smoke: python TESTS/regional_case_study_smoke.py."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto('http://localhost:5173/case-studies.html', wait_until='networkidle')
    page.get_by_role('link', name='From mountain snow', exact=False).click()
    page.get_by_role('heading', name='One methodology, distinct evidence layers').wait_for()
    page.get_by_role('link', name='Regional station study', exact=False).click()
    page.get_by_role('heading', name='How does location shape the satellite signal?').wait_for()
    page.get_by_label('Regional station', exact=True).select_option('uz:station/meteo-419704')
    page.get_by_label('Station measurement', exact=True).select_option('air')
    page.get_by_label('Temporal comparison', exact=True).select_option('raw')
    assert page.locator('.cs-chart svg').count() >= 7
    assert page.get_by_role('link', name='Monthly values and QA counts').count() == 1
    page.get_by_label('Temporal comparison', exact=True).select_option('anomaly')
    path = ROOT/'WORKSPACE/derived/ui-review'
    path.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path/'regional-study-desktop.png'))
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(path/'regional-study-mobile.png'))
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
    page.get_by_role('link', name='Chirchik / Pskem', exact=False).click()
    page.get_by_role('heading', name='One methodology, distinct evidence layers').wait_for()
    assert not errors, errors
    browser.close()
print('Desktop/mobile, study switch, station/variable selectors, charts and downloads passed; no page errors.')
