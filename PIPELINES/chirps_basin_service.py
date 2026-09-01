"""Monthly precipitation per basin from CHIRPS v3.

CHIRPS blends infrared cold-cloud duration with station data at 5.6 km, which is
roughly six times finer than the CFSv2 grid already in the ontology. Both carry
precipitation and they will not agree; having the two is the point, because
CHIRPS is built for rainfall while CFSv2 produces it as one output of a coupled
model.

Version 3 sits under a different provider path from the version 2 most code
still points at — UCSB-CHC, not UCSB-CHG — and the two are not interchangeable:
over Uzbekistan in July 2026 v3 gives 8.258 mm against v2's 7.556, about nine
percent apart.

Two v3 products are published and this reads both, because they answer different
questions:

    DAILY_SAT   near-real-time, satellite-only, from 1998. What fell recently.
    DAILY_RNL   reanalysis with station blending, from 1981. What to compare
                against — the longer and better-constrained record.

Daily images are summed to a monthly total, which is what precipitation is
usefully reported as; a mean of daily rates would be a number nobody quotes.

    python PIPELINES/chirps_basin_service.py --start 2026-01 --end 2026-07
    python PIPELINES/chirps_basin_service.py --product RNL --start 2011-01 --end 2011-12
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASINS = ROOT / "PUBLISHED" / "data" / "review" / "basinatlas" / "basinatlas_uz_lev07.geojson"
OUTPUT = ROOT / "PUBLISHED" / "data" / "analysis" / "chirps-v3-basin-monthly.csv"

PROJECT = "ee-sabitovty"
PRODUCTS = {
    "SAT": ("UCSB-CHC/CHIRPS/V3/DAILY_SAT", "near-real-time, satellite only, from 1998"),
    "RNL": ("UCSB-CHC/CHIRPS/V3/DAILY_RNL", "reanalysis with station blending, from 1981"),
}
SCALE = 5566


def months(start: str, end: str) -> list[tuple[int, int]]:
    sy, sm = (int(p) for p in start.split("-"))
    ey, em = (int(p) for p in end.split("-"))
    out, year, month = [], sy, sm
    while (year, month) <= (ey, em):
        out.append((year, month))
        month = month + 1 if month < 12 else 1
        if month == 1:
            year += 1
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--product", choices=sorted(PRODUCTS), default="SAT")
    parser.add_argument("--start", default="2026-01")
    parser.add_argument("--end", default="2026-07")
    args = parser.parse_args()
    asset, description = PRODUCTS[args.product]

    try:
        import ee
        ee.Initialize(project=PROJECT)
        ee.Number(1).getInfo()
    except Exception as error:
        raise SystemExit(f"Earth Engine unavailable: {str(error).strip()[:150]}\n"
                         f"  Run: earthengine authenticate --project {PROJECT}") from error

    document = json.loads(BASINS.read_text(encoding="utf8"))
    collection = ee.FeatureCollection([
        ee.Feature(ee.Geometry(f["geometry"]), {"basin": int(f["properties"]["HYBAS_ID"])})
        for f in document["features"]])
    source = ee.ImageCollection(asset)

    done = set()
    if OUTPUT.exists():
        with OUTPUT.open(encoding="utf8", newline="") as handle:
            done = {(r["product"], r["year"], r["month"]) for r in csv.DictReader(handle)}
    todo = [(y, m) for y, m in months(args.start, args.end)
            if (args.product, str(y), str(m)) not in done]

    print(f"CHIRPS v3 {args.product} · {description}")
    print(f"  {len(document['features'])} level-7 basins · {len(todo)} months to measure")
    if not todo:
        print("  nothing to do")
        return

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fresh = not OUTPUT.exists()
    started, rows = time.time(), 0
    with OUTPUT.open("a", encoding="utf8", newline="") as handle:
        writer = csv.writer(handle)
        if fresh:
            writer.writerow(["basin_id", "year", "month", "product", "variable",
                             "value", "unit", "quality"])
        for position, (year, month) in enumerate(todo, start=1):
            start = ee.Date.fromYMD(year, month, 1)
            window = source.filterDate(start, start.advance(1, "month")).select("precipitation")
            if window.size().getInfo() == 0:
                print(f"  {year}-{month:02d}: no images", flush=True)
                continue
            total = window.sum()
            try:
                result = total.reduceRegions(collection=collection,
                                             reducer=ee.Reducer.mean(), scale=SCALE).getInfo()
            except Exception as error:
                print(f"  ! {year}-{month:02d}: {str(error).strip()[:100]}", flush=True)
                continue
            for feature in result["features"]:
                value = feature["properties"].get("mean")
                if value is None:
                    continue
                # CHIRPS marks gaps with a large negative sentinel; a monthly total
                # below zero is that, not a dry month.
                quality = "ok" if value >= 0 else "implausible"
                writer.writerow([feature["properties"]["basin"], year, month, args.product,
                                 "precipitation_total", round(value, 4), "mm", quality])
                rows += 1
            handle.flush()
            rate = (time.time() - started) / position
            print(f"  {year}-{month:02d} · {position}/{len(todo)} · {rate:.0f}s each · "
                  f"{(len(todo) - position) * rate / 60:.0f} min left", flush=True)

    print(f"\n  {rows:,} observations -> {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
