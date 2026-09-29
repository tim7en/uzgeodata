"""Small local browser/API functional pass. Run with a local Vite server at BASE_URL."""
import csv
import io
import json
import os
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:5175")
OUT = Path(__file__).parent
OUT.mkdir(exist_ok=True)
results = []


def record(name, status, detail):
    results.append({"scenario": name, "status": status, "detail": detail})


def get_json(path):
    with urlopen(BASE + path, timeout=20) as response:
        assert response.status == 200
        assert "json" in response.headers.get("content-type", "")
        return json.load(response)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900}, accept_downloads=True)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(BASE + "/", wait_until="domcontentloaded", timeout=30000)
        page.locator(".land-dock").wait_for(timeout=30000)
        page.locator(".land-aoi button").filter(has_text="Draw area").click()
        map_box = page.locator(".land-map").bounding_box()
        x, y = map_box["x"] + map_box["width"] * .60, map_box["y"] + map_box["height"] * .48
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x + 24, y + 24, steps=5)
        page.mouse.up()
        page.locator(".land-aoi-summary strong").wait_for(timeout=30000)
        count_text = page.locator(".land-aoi-summary strong").inner_text()
        count = int(count_text.split()[0].replace(",", ""))
        if not (0 < count <= 1000):
            record("AOI basin selection", "FAIL", f"Selected count {count}; expected 1..1000 for bounded export")
        else:
            record("AOI basin selection", "PASS", f"Map rectangle selected {count} level-12 basins")
            with page.expect_download(timeout=15000) as download_info:
                page.locator(".land-aoi-downloads button").filter(has_text="Basin list").click()
            download = download_info.value
            csv_path = OUT / "basin-list.csv"
            download.save_as(csv_path)
            rows = list(csv.DictReader(io.StringIO(csv_path.read_text(encoding="utf-8-sig"))))
            index = get_json("/data/atlas/basins/index.json")
            bad = []
            for row in rows:
                basin_id = row["hybas_id"]
                entry = index["by_basin"].get(basin_id)
                if not entry or entry.get("system") != row["system_id"]:
                    bad.append(basin_id)
            record("CSV basin identifiers and system", "PASS" if len(rows) == count and not bad else "FAIL",
                   f"CSV rows={len(rows)}, selected={count}, IDs absent or system mismatch={bad[:5]}")
            with page.expect_download(timeout=60000) as download_info:
                page.locator(".land-aoi-downloads button").filter(has_text="Everything").click()
            json_path = OUT / "area-export.json"
            download_info.value.save_as(json_path)
            exported = json.loads(json_path.read_text(encoding="utf-8"))
            ids = {row["hybas_id"] for row in rows}
            export_ids = {basin["hybas_id"] for basin in exported["basins"]}
            geometry = exported["area_of_interest"]["geometry"]
            ok = ids == export_ids and exported["selection"]["count"] == count and geometry["type"] == "Polygon"
            record("JSON identifiers and AOI geometry", "PASS" if ok else "FAIL",
                   f"CSV IDs={len(ids)}, JSON IDs={len(export_ids)}, geometry={geometry['type']}")
            metadata = bool(exported.get("attribute_meta")) and bool(exported.get("release"))
            record("JSON attribute and release metadata", "PASS" if metadata else "FAIL",
                   f"attribute_meta present={bool(exported.get('attribute_meta'))}, release present={bool(exported.get('release'))}")
        page.screenshot(path=str(OUT / "selection.png"))
    except Exception as exc:
        page.screenshot(path=str(OUT / "failure.png"))
        record("AOI browser selection/export", "FAIL", f"{type(exc).__name__}: {exc}")
    finally:
        browser.close()

record("Invalid coordinate input", "NOT TESTED", "Map AOI is pointer driven; coordinate upload validation was outside this bounded run")
record("Browser page errors", "PASS" if not errors else "FAIL", json.dumps(errors[:5]))
(OUT / "results.json").write_text(json.dumps({"base_url": BASE, "results": results}, indent=2), encoding="utf-8")
print(json.dumps(results, indent=2))
raise SystemExit(1 if any(row["status"] == "FAIL" for row in results) else 0)
