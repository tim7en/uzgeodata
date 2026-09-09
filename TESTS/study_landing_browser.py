"""Production navigation, deferred data, mobile layout and failure recovery."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
BASE=os.environ.get('STUDY_TEST_URL','http://localhost:5173')
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[]; requests=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:requests.append(r.url))
    page.goto(BASE+'/case-studies.html',wait_until='networkidle')
    page.locator('.cs-study-card').first.wait_for()
    assert page.locator('.cs-study-card').count()==2
    assert not any('regional-station-study.json' in r or r.endswith('chirchik.json') for r in requests)
    assert page.locator('.cs-card-image img').evaluate_all('(images)=>images.every(i=>i.complete && i.naturalWidth>0)')
    out=ROOT/'WORKSPACE/derived/ui-review';out.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(out/'study-directory-desktop.png'),full_page=True)
    page.get_by_role('link',name='From mountain snow',exact=False).click()
    page.get_by_role('heading',name='Flow timing has skill. Seasonal volume remains uncertain.').wait_for()
    assert page.locator('#model-review .cs-chart svg').count()==2
    assert not page.locator('#supporting-evidence').get_attribute('open')
    page.locator('#reference-model > summary').click()
    page.get_by_role('heading',name='Snow storage, soil water and river flow.').wait_for()
    page.get_by_label('Current model chart').select_option('seasonal')
    assert 'million m³' in page.locator('#current-model').inner_text()
    page.get_by_label('Evaluation split').select_option('calibration')
    page.go_back(wait_until='networkidle')
    page.locator('.cs-study-card').first.wait_for()
    page.get_by_role('link',name='Read the landscape',exact=False).click()
    page.get_by_role('heading',name='How does location shape the satellite signal?').wait_for()
    page.get_by_role('link',name='All case studies',exact=True).click()
    page.locator('.cs-study-card').first.wait_for()
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    page.screenshot(path=str(out/'study-directory-mobile.png'),full_page=True)
    page.route('**/study-directory.json',lambda route:route.fulfill(status=503,body='Unavailable'))
    page.reload(wait_until='networkidle')
    page.get_by_role('button',name='Try again').wait_for()
    page.unroute('**/study-directory.json')
    page.get_by_role('button',name='Try again').click()
    page.locator('.cs-study-card').first.wait_for()
    page.goto(BASE+'/',wait_until='domcontentloaded')
    page.locator('.land-deeper').wait_for()
    assert page.locator('.land-deeper a').count()==1
    assert page.locator('.land-deeper a').get_attribute('href')=='/case-studies.html'

    # A study must be citable: its own path has to render the study on a cold
    # load, not fall through to the front page with a 200, and it must survive
    # back and forward. The fragment the directory used before still resolves.
    page.set_viewport_size({'width':1440,'height':1000})
    page.goto(BASE+'/case-studies/chirchik',wait_until='networkidle')
    page.locator('#reproducibility').wait_for()
    assert page.title().startswith('Chirchik'),page.title()
    page.goto(BASE+'/case-studies.html#chirchik-study',wait_until='networkidle')
    assert page.title().startswith('Chirchik'),page.title()
    page.goto(BASE+'/case-studies.html',wait_until='networkidle')
    page.locator('.cs-study-card').first.wait_for()
    assert page.locator('.cs-study-card').first.get_attribute('href')=='/case-studies/chirchik'
    page.get_by_role('link',name='From mountain snow',exact=False).click()
    page.locator('#reproducibility').wait_for()
    assert page.url.endswith('/case-studies/chirchik'),page.url
    page.go_back(wait_until='networkidle')
    page.locator('.cs-study-card').first.wait_for()

    # The reproducibility package answers four questions; each tab must render
    # substance, and the verification tab must show a real rebuild verdict.
    page.goto(BASE+'/case-studies/chirchik',wait_until='networkidle')
    package=page.locator('#reproducibility')
    package.wait_for()
    package.scroll_into_view_if_needed()
    for label in ('Data','Method','Results','Verification','Tests','Transfer'):
        package.get_by_role('tab',name=label,exact=True).click()
        assert package.locator('table tbody tr, li').count()>0,label
    package.get_by_role('tab',name='Verification',exact=True).click()
    assert package.locator('.cs-package-verdict').count()==1
    package.get_by_role('tab',name='Transfer',exact=True).click()
    assert 'not attempted' in package.inner_text(),'untested domains must stay visible'


    # Both themes must be readable, not merely available. Contrast is measured
    # rather than eyeballed: a light palette derived from a dark one fails in
    # exactly the places a screenshot flatters.
    contrast=(ROOT/'TESTS'/'contrast_probe.js').read_text(encoding='utf-8')
    for theme in ('dark','light'):
        page.goto(BASE+'/case-studies/chirchik',wait_until='networkidle')
        page.evaluate("theme => localStorage.setItem('uzgeodata-theme', theme)",theme)
        page.reload(wait_until='networkidle')
        page.locator('#reproducibility').wait_for()
        assert page.evaluate('document.documentElement.dataset.theme')==theme
        failures=[r for r in page.evaluate(contrast) if r['ratio']<r['need']]
        assert not failures,f'{theme}: '+'; '.join(
            f"{r['ratio']} {r['text'][:40]}" for r in failures[:5])
    # The switch itself: start from a known theme, then toggle both ways and
    # confirm the choice survives a reload rather than resetting to the default.
    page.evaluate("localStorage.setItem('uzgeodata-theme','dark')")
    page.reload(wait_until='networkidle')
    page.locator('#reproducibility').wait_for()
    page.get_by_role('button',name='Switch to light mode').click()
    assert page.evaluate('document.documentElement.dataset.theme')=='light'
    page.reload(wait_until='networkidle')
    assert page.evaluate('document.documentElement.dataset.theme')=='light','choice must persist'
    page.get_by_role('button',name='Switch to dark mode').click()
    assert page.evaluate('document.documentElement.dataset.theme')=='dark'
    page.evaluate("localStorage.removeItem('uzgeodata-theme')")

    assert not errors,errors
    browser.close()
print('Study directory, image cards, lazy data, history navigation, current charts, mobile layout, retry, citable study paths, the reproducibility package and both themes passed.')
