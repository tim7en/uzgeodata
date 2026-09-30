"""Browser sweep of the public portal: every page, then one basin through every tab.

Run from repository root: python qa/deep_dive/data_quality/browse_portal.py [base-url]

Records, per page and viewport: HTTP status, console errors, failed or HTML-instead-of-
data requests, horizontal overflow, and text that leaks a programming value (NaN,
undefined, [object Object], Infinity). Then opens basin 4121292070 through the finder
and clicks each tab of its window. Writes browse.json and screenshots beside itself.
"""
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://uzgeodata.uz").rstrip("/")
HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots"
PAGES = ["/", "/about", "/guide", "/seasonal", "/drought", "/snow-forecast", "/agents", "/case-studies", "/research",
         "/examples", "/data-lineage", "/admin", "/roadmap", "/dynamic-atlas", "/catalogue", "/metadata", "/climate",
         "/trends", "/landcover", "/hydrography", "/water-flow", "/dry-spell", "/reservoir-monitoring", "/surrogates",
         "/atlas", "/ontology", "/relationships", "/project", "/projects", "/review"]
BASIN = "4121292070"
LEAK = re.compile(r"\bNaN\b|\bundefined\b|\[object Object\]|\bInfinity\b")
VIEWPORTS = {"desktop": (1366, 900), "phone": (390, 844)}


def watch(page, log):
    page.on("console", lambda m: m.type == "error" and log["console"].append(m.text[:300]))
    page.on("pageerror", lambda e: log["console"].append(f"pageerror: {str(e)[:300]}"))

    def response(r):
        url = r.url
        if not url.startswith(BASE):
            return
        kind = r.headers.get("content-type", "")
        if r.status >= 400:
            log["failed"].append(f"{r.status} {url[len(BASE):]}")
        elif re.search(r"\.(json|csv|parquet|bin|gz)(\?|$)", url) and "text/html" in kind:
            log["failed"].append(f"HTML instead of data: {url[len(BASE):]}")
    page.on("response", response)


def inspect(page, log):
    text = page.inner_text("body")
    leaks = sorted({m.group(0) for m in LEAK.finditer(text)})
    if leaks:
        log["leaks"] = leaks
        log["leak_context"] = [text[max(0, m.start() - 60):m.end() + 40].replace("\n", " ")
                               for m in list(LEAK.finditer(text))[:3]]
    log["overflow_px"] = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")


def sweep_pages(browser):
    results = []
    for name, (w, h) in VIEWPORTS.items():
        for path in PAGES:
            page = browser.new_page(viewport={"width": w, "height": h})
            log = {"page": path, "viewport": name, "console": [], "failed": []}
            watch(page, log)
            try:
                response = page.goto(BASE + path, wait_until="networkidle", timeout=45000)
                log["status"] = response.status if response else None
                log["title"] = page.title()
                page.wait_for_timeout(1200)
                inspect(page, log)
                if name == "phone":
                    page.screenshot(path=str(SHOTS / f"page{path.replace('/', '_') or '_home'}.png"))
            except Exception as error:
                log["error"] = str(error)[:300]
            results.append(log)
            page.close()
    return results


def sweep_basin(browser):
    page = browser.new_page(viewport={"width": 1366, "height": 900})
    log = {"basin": BASIN, "console": [], "failed": [], "tabs": {}}
    watch(page, log)
    page.goto(BASE + "/", wait_until="networkidle", timeout=60000)
    page.fill("input[aria-label='Search basins by HYBAS or PFAF identifier']", BASIN)
    page.wait_for_selector(".land-finder-result button", timeout=60000)
    page.click(".land-finder-result > button")
    page.wait_for_timeout(2500)
    tabs = page.locator("[role=tab], .land-modal-tabs button").all_inner_texts()
    log["tab_names"] = tabs
    for label in tabs:
        tab = {"console_before": len(log["console"]), "failed_before": len(log["failed"])}
        try:
            page.get_by_role("tab", name=label).first.click() if page.get_by_role("tab", name=label).count() \
                else page.locator(".land-modal-tabs button", has_text=label).first.click()
            page.wait_for_timeout(4000)
            body = page.inner_text("body")
            tab["leaks"] = sorted({m.group(0) for m in LEAK.finditer(body)})
            tab["mentions_observed"] = len(re.findall(r"\bobserv", body, re.I))
            tab["loading_left"] = bool(re.search(r"Loading", page.inner_text(".land-modal") if page.locator(".land-modal").count() else body))
            tab["errors_shown"] = [t[:160] for t in page.locator("[role=alert]").all_inner_texts()]
            page.screenshot(path=str(SHOTS / f"tab_{re.sub(r'[^a-z]+', '_', label.lower()).strip('_')}.png"), full_page=False)
        except Exception as error:
            tab["error"] = str(error)[:300]
        tab["new_console"] = log["console"][tab.pop("console_before"):]
        tab["new_failed"] = log["failed"][tab.pop("failed_before"):]
        log["tabs"][label] = tab
    page.close()
    return log


def main():
    SHOTS.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pages = sweep_pages(browser)
        basin = sweep_basin(browser)
        browser.close()
    result = {"base": BASE, "pages": pages, "basin": basin}
    (HERE / "browse.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    bad = [p for p in pages if p.get("status", 0) >= 400 or p.get("error") or p["console"] or p["failed"]
           or p.get("leaks") or p.get("overflow_px", 0) > 2]
    print(f"{len(pages)} page loads, {len(bad)} with a finding")
    for p in bad:
        print(json.dumps({k: v for k, v in p.items() if v not in ([], None)}, ensure_ascii=False)[:600])
    print("basin tabs:", basin.get("tab_names"))
    for name, tab in basin["tabs"].items():
        print(" ", name, json.dumps({k: v for k, v in tab.items() if v not in ([], None, False, 0)}, ensure_ascii=False)[:400])


if __name__ == "__main__":
    main()
