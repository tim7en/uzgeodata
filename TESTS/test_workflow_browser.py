"""Run against Vite: TEST_BASE_URL defaults to http://127.0.0.1:5175."""
import json
import os
from pathlib import Path

def run():
    # Browser tooling is optional for the ordinary pytest collection in CI.
    from playwright.sync_api import sync_playwright, expect

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, locale="en-US")
        context.add_init_script("localStorage.setItem('uzgeodata-lang', 'en')")
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        base = os.getenv("TEST_BASE_URL", "http://127.0.0.1:5175")
        page.goto(base)
        finder = page.get_by_role("textbox", name="Search basins by HYBAS or PFAF identifier")
        expect(finder).to_be_visible()

        # One entry, one result, one download: no zoom, panel or tab prerequisite.
        finder.fill("4120050220")
        page.locator(".land-finder-result > button").click()
        expect(page.locator(".land-hist-figure")).to_be_visible()
        expect(page.locator(".land-catchment-map canvas")).to_be_visible()
        expect(page.locator(".land-catchment-key")).to_contain_text("Selected basin")
        expect(page.locator(".land-catchment")).to_contain_text("upstream basins")
        with page.expect_download() as download:
            page.get_by_role("button", name="Download this basin, all variables (CSV)").click()
        csv = Path(download.value.path()).read_text(encoding="utf-8")
        assert download.value.suggested_filename == "basin-4120050220-monthly.csv"
        assert csv.startswith("year,month,") and len(csv.splitlines()) > 200
        page.keyboard.press("Escape")

        # A result can open attributes or estimates directly, without extra tabs.
        page.locator(".land-finder-views").get_by_role("button", name="Attributes", exact=True).click()
        expect(page.get_by_role("tab", name="HydroATLAS attributes")).to_have_attribute("aria-selected", "true")
        expect(page.locator(".land-catchment-map")).to_be_visible()
        expect(page.locator(".land-modal tbody tr")).to_have_count(281)
        with page.expect_download() as download:
            page.get_by_role("link", name="Attributes & estimates (JSON)").click()
        record = json.loads(Path(download.value.path()).read_text())
        assert str(record["basin_id"]) == "4120050220"
        page.keyboard.press("Escape")
        page.locator(".land-finder-views").get_by_role("button", name="Estimates", exact=True).click()
        expect(page.get_by_role("tab", name="Independent estimates")).to_have_attribute("aria-selected", "true")
        page.locator(".land-sub-toggle").first.click()
        expect(page.locator(".land-sub-evidence").first).to_be_visible()
        page.keyboard.press("Escape")

        # Select a different variable as the third action after search and result.
        page.locator(".land-finder-result > button").click()
        variable = page.get_by_role("group", name="Choose a variable").get_by_role("button").nth(1)
        label = variable.inner_text()
        variable.click()
        expect(page.locator(".land-hist-figure figcaption")).to_contain_text(label, ignore_case=True)
        page.keyboard.press("Escape")

        # Drawing is one drag, with no finish/confirm action. Download is third.
        page.get_by_role("button", name="Draw area", exact=True).click()
        page.mouse.move(690, 420)
        page.mouse.down()
        page.mouse.move(780, 510, steps=12)
        page.mouse.up()
        expect(page.locator(".land-aoi-summary")).to_be_visible()
        with page.expect_download() as download:
            page.get_by_role("button", name="Basin list ids, system, area CSV").click()
        assert len(Path(download.value.path()).read_text().splitlines()) > 1
        assert page.get_by_role("dialog").count() == 0

        # Search failure is local, recoverable, and does not replace the map.
        page.evaluate("localStorage.removeItem('uzgeodata.mapView')")
        page.reload()
        pattern = "**/reference-basins-level12.geojson"
        page.route(pattern, lambda route: route.fulfill(status=503, body="unavailable"))
        finder.fill("4120050220")
        expect(page.get_by_role("button", name="Retry search")).to_be_visible()
        expect(page.locator(".leaflet-container")).to_be_visible()
        page.unroute(pattern)
        page.get_by_role("button", name="Retry search").click()
        expect(page.locator(".land-finder-result")).to_have_count(1)
        finder.fill("99999999999999")
        expect(page.get_by_role("status").filter(has_text="No matching basin")).to_be_visible()

        # Small screens retain the same entry and download controls.
        page.set_viewport_size({"width": 390, "height": 844})
        page.evaluate("window.scrollTo(0, 0)")
        box = finder.bounding_box()
        assert box["y"] >= 0 and box["y"] + box["height"] < 844
        finder.fill("4120050220")
        page.locator(".land-finder-result > button").click()
        expect(page.locator(".land-hist-figure")).to_be_visible()
        expect(page.locator(".land-catchment-map canvas")).to_be_visible()
        with page.expect_download() as download:
            page.get_by_role("link", name="Monthly data & metadata (JSON)").click()
        record = json.loads(Path(download.value.path()).read_text())
        assert str(record["basin_id"]) == "4120050220" and record["series"]
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        Path("tmp").mkdir(exist_ok=True)
        page.screenshot(path="tmp/workflow-mobile.png")
        # Touch drag completes the rectangle and brings results into view itself.
        touch = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True,
                                    has_touch=True, locale="en-US")
        touch.add_init_script("localStorage.setItem('uzgeodata-lang', 'en')")
        mobile = touch.new_page()
        mobile.on("pageerror", lambda error: errors.append(str(error)))
        mobile.goto(base)
        mobile.get_by_role("button", name="Draw area", exact=True).click()
        map_box = mobile.locator(".leaflet-container").bounding_box()
        x, y = map_box["x"] + 160, map_box["y"] + 200
        session = touch.new_cdp_session(mobile)
        session.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
        session.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x + 35, "y": y + 35}]})
        session.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        expect(mobile.locator(".land-aoi-summary")).to_be_visible()
        with mobile.expect_download():
            mobile.get_by_role("button", name="Basin list ids, system, area CSV").click()
        touch.close()
        assert not errors, errors
        browser.close()
        print("Passed: basin charts, CSV/JSON downloads, attributes, estimates, rectangle selection, search recovery, mobile.")


if __name__ == "__main__":
    run()
