"""Pentadal precipitation per basin from CHIRPS v3 — the canonical rainfall layer.

CHIRPS is computed at pentadal and monthly scales, and its daily product is a
disaggregation of the pentadal values rather than an independent measurement.
That is not a claim taken on trust: summed over a month, PENTAD and DAILY agree
to within 0.00% in every month tested between 2011 and 2026. The daily series
therefore carries no information at monthly scale, and the variation *within* a
pentad is an artefact of the disaggregation — not something to read as rainfall
on a particular day.

So the pentad is what gets stored. Six per month — days 1-5, 6-10, 11-15, 16-20,
21-25 and 26 to month end — each an accumulated total in millimetres. Monthly and
seasonal figures are sums of pentads and are derived on demand; storing them as
well would be a second set of numbers that could drift from the first.

A pentad is also the right grain for the indicators this feeds: SPI, 30/60/90-day
deficits, seasonal totals and basin water balance all accumulate over windows that
a monthly table cannot cut finely enough and a synthetic daily one cannot honestly
support.

On the two daily products: DAILY_SAT (from 1998) and DAILY_RNL (from 1981) return
identical values wherever they overlap, tested over Uzbekistan and over
station-dense East Africa. They differ only in how far back they reach, so
nothing here needs to choose between them.

    python PIPELINES/chirps_basin_service.py --start 2026-01 --end 2026-07
    python PIPELINES/chirps_basin_service.py --start 2011-01 --end 2025-12   # baseline

Basin level is chosen per product, from the source grid — not once for the whole
ontology. A basin smaller than the pixel it samples cannot hold a value of its
own; it inherits its neighbour's. CFSv2 is 34.8 km, so a level-12 basin covers a
tenth of a pixel and level 7 is as fine as it goes. CHIRPS and CHIRTS are 5.6 km,
where a level-12 basin covers about four pixels, so level 12 is honest for them —
and costs no more, because a reduction is priced by the raster it reads rather
than by the number of polygons laid over it.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import date
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parent.parent
BASINS = ROOT / "PUBLISHED" / "data" / "hydrography" / "basins.geojson"
from ontology_paths import dataset_dir
OUTPUT = dataset_dir("CHIRPS_V3_BASIN_PENTAD", "ATMOSPHERE") / "chirps-v3-basin-pentad.csv"

PROJECT = "ee-sabitovty"
ASSET = "UCSB-CHC/CHIRPS/V3/PENTAD"
SCALE = 5566

# Where each pentad of a month begins. The sixth runs to the end of the month, so
# it is five days in February and six in a 31-day month — a pentad is a fixed
# calendar slot, not a fixed duration, and an mm/day rate derived from one has to
# divide by the right number of days.
PENTAD_STARTS = (1, 6, 11, 16, 21, 26)


def pentads(start: str, end: str):
    """Every (year, month, index, first_day, last_day) in the requested range."""
    sy, sm = (int(p) for p in start.split("-"))
    ey, em = (int(p) for p in end.split("-"))
    year, month = sy, sm
    while (year, month) <= (ey, em):
        for index, first in enumerate(PENTAD_STARTS, start=1):
            if index < 6:
                last = PENTAD_STARTS[index] - 1
            else:
                last = (date(year + (month == 12), month % 12 + 1, 1) - date.resolution).day
            yield year, month, index, first, last
        month = month + 1 if month < 12 else 1
        if month == 1:
            year += 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", default="2026-01", help="First month, YYYY-MM.")
    parser.add_argument("--end", default="2026-07", help="Last month, YYYY-MM.")
    args = parser.parse_args()

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
    source = ee.ImageCollection(ASSET).select("precipitation")

    done = set()
    if OUTPUT.exists():
        with OUTPUT.open(encoding="utf8", newline="") as handle:
            done = {(r["year"], r["month"], r["pentad"]) for r in csv.DictReader(handle)}
    todo = [row for row in pentads(args.start, args.end)
            if (str(row[0]), str(row[1]), str(row[2])) not in done]

    print(f"CHIRPS v3 PENTAD · {len(document['features'])} level-12 basins · {len(todo)} pentads to measure")
    if not todo:
        print("  nothing to do")
        return

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fresh = not OUTPUT.exists()
    started, rows = time.time(), 0
    with OUTPUT.open("a", encoding="utf8", newline="") as handle:
        writer = csv.writer(handle)
        if fresh:
            writer.writerow(["basin_id", "year", "month", "pentad", "start_date", "end_date",
                             "days", "variable", "value", "unit", "quality"])
        for position, (year, month, index, first, last) in enumerate(todo, start=1):
            begin = ee.Date.fromYMD(year, month, first)
            # A half-open window on the day after the pentad's last day catches
            # exactly the one image CHIRPS stamps at its start.
            finish = ee.Date.fromYMD(year, month, last).advance(1, "day")
            window = source.filterDate(begin, finish)
            if window.size().getInfo() == 0:
                print(f"  {year}-{month:02d} p{index}: no image", flush=True)
                continue
            try:
                result = window.sum().reduceRegions(
                    collection=collection, reducer=ee.Reducer.mean(), scale=SCALE).getInfo()
            except Exception as error:
                print(f"  ! {year}-{month:02d} p{index}: {str(error).strip()[:100]}", flush=True)
                continue
            for feature in result["features"]:
                value = feature["properties"].get("mean")
                if value is None:
                    continue
                # CHIRPS marks gaps with a large negative sentinel; a negative
                # accumulation is that, not a dry pentad.
                quality = "ok" if value >= 0 else "implausible"
                writer.writerow([feature["properties"]["basin"], year, month, index,
                                 f"{year}-{month:02d}-{first:02d}", f"{year}-{month:02d}-{last:02d}",
                                 last - first + 1, "precipitation_total",
                                 round(value, 4), "mm", quality])
                rows += 1
            handle.flush()
            if position % 6 == 0 or position == len(todo):
                rate = (time.time() - started) / position
                print(f"  {year}-{month:02d} p{index} · {position}/{len(todo)} · {rate:.1f}s each · "
                      f"{(len(todo) - position) * rate / 60:.0f} min left", flush=True)

    print(f"\n  {rows:,} observations -> {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
