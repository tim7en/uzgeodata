"""Did CAMS see the pollution event coming? Verification at a point, by lead time.

The skill table beside this one measures forecasts against analyses on average.
Averages are not what a city cares about. Tashkent cares whether the model called
the day the sky went orange, and a product can track the mean well while missing
every spike — so events are verified separately, on their own terms.

An event is a value above a percentile of the analysis record, and for each lead
time the question is how many were caught, how many were missed, and how often an
event was forecast that did not arrive. Probability of detection and false alarm
ratio, which is how meteorologists have always judged this.

What the numbers said for Tashkent, 2024 to 2026, above the 95th percentile:

    dust AOD   POD 0.75 at 24 h, still 0.66 at 120 h
    PM10       POD 0.48 at 24 h, down to 0.19 by 96 h

Those describe different things and the gap is physical, not statistical. Dust
optical depth is a column of transported aerosol driven by synoptic weather, and
weather is predictable for days. Surface PM10 adds local emission and depends on
how the boundary layer mixes that morning, which is not. On the largest event in
the record — 121 ug/m3 on 7 June 2025 — the dust column was within 20% of the
analysis at every lead out to five days while surface PM10 was under-forecast by
27% at one day and 65% at four.

A separate caveat applies to the point itself: the grid cell is about 1,470 km2,
so this verifies the cell containing Tashkent rather than the city. A street-level
episode inside one cell is invisible here either way.

    python PIPELINES/cams_event_verification.py --lon 69.24 --lat 41.30 --name TASHKENT
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ontology_paths import dataset_dir

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = dataset_dir("CAMS_EVENT_VERIFICATION", "ATMOSPHERE") / "cams-event-verification.csv"

PROJECT = "ee-sabitovty"
ASSET = "ECMWF/CAMS/NRT"
SCALE = 44453
LEADS = (24, 48, 72, 96, 120)

# The coarse and dust-specific bands exist only from 2021-07-01. They are the
# ones an event question needs: dust is mostly coarse, so PM2.5 under-represents
# exactly the episodes people notice.
BANDS = {
    "dust_aod": "dust_aerosol_optical_depth_at_550nm_surface",
    "pm10": "particulate_matter_d_less_than_10_um_surface",
    "pm2p5": "particulate_matter_d_less_than_25_um_surface",
}
FACTOR = {"pm10": 1e9, "pm2p5": 1e9, "dust_aod": 1.0}
UNIT = {"pm10": "ug/m3", "pm2p5": "ug/m3", "dust_aod": "index"}
FIELDS = ["site", "lat", "lon", "period_start", "period_end", "variable",
          "lead_hours", "percentile", "pairs", "metric", "value", "unit"]


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def series(ee, lead: int, point, start: str, end: str) -> dict:
    collection = (ee.ImageCollection(ASSET).filterDate(start, end)
                  .filter(ee.Filter.eq("model_forecast_hour", lead))
                  .select(list(BANDS.values())))
    rows = collection.getRegion(point, SCALE).getInfo()
    header = rows[0]
    time_at = header.index("time")
    index = {name: header.index(band) for name, band in BANDS.items()}
    out = {}
    for row in rows[1:]:
        if row[index["dust_aod"]] is None:
            continue
        out[row[time_at]] = {name: row[position] * FACTOR[name]
                             for name, position in index.items()}
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lon", type=float, default=69.24)
    parser.add_argument("--lat", type=float, default=41.30)
    parser.add_argument("--name", default="TASHKENT")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default=date.today().isoformat(),
                        help="Exclusive end date. Default: today; never a future hard-coded date.")
    parser.add_argument("--percentile", type=int, default=95,
                        help="An event is an analysis value at or above this percentile.")
    args = parser.parse_args()

    try:
        import ee
        ee.Initialize(project=PROJECT)
        ee.Number(1).getInfo()
    except Exception as error:
        raise SystemExit(f"Earth Engine unavailable: {str(error).strip()[:150]}\n"
                         f"  Run: earthengine authenticate --project {PROJECT}") from error

    point = ee.Geometry.Point([args.lon, args.lat])
    print(f"{args.name} ({args.lat}, {args.lon}) · {args.start} to {args.end}")
    store = {}
    for lead in (0, *LEADS):
        # A year at a time: the whole span in one call exceeds the memory limit.
        merged = {}
        year = int(args.start[:4])
        while year <= int(args.end[:4]):
            a = max(f"{year}-01-01", args.start)
            b = min(f"{year + 1}-01-01", args.end)
            if a < b:
                try:
                    merged.update(series(ee, lead, point, a, b))
                except Exception as error:
                    print(f"  ! +{lead}h {year}: {str(error).strip()[:70]}", flush=True)
            year += 1
        store[lead] = merged
        print(f"  +{lead:>3}h: {len(merged)} times", flush=True)

    truth = store[0]
    if not truth:
        raise SystemExit("no analyses returned")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for name in BANDS:
        values = [v[name] for v in truth.values()]
        threshold = statistics.quantiles(values, n=100)[args.percentile - 1]
        events = {t for t, v in truth.items() if v[name] >= threshold}
        for lead in LEADS:
            forecast = store[lead]
            common = [t for t in truth if t in forecast]
            if len(common) < 30:
                continue
            predicted = {t for t in common if forecast[t][name] >= threshold}
            actual = {t for t in common if t in events}
            hits = len(predicted & actual)
            misses = len(actual - predicted)
            false_alarms = len(predicted - actual)
            a = [truth[t][name] for t in common]
            b = [forecast[t][name] for t in common]
            ma, mb = sum(a) / len(a), sum(b) / len(b)
            numerator = sum((x - ma) * (y - mb) for x, y in zip(a, b))
            denominator = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
            for metric, value, unit in (
                    ("threshold", threshold, UNIT[name]),
                    ("events", len(actual), "count"),
                    ("hits", hits, "count"),
                    ("misses", misses, "count"),
                    ("false_alarms", false_alarms, "count"),
                    ("probability_of_detection", hits / len(actual) if actual else None, "fraction"),
                    ("false_alarm_ratio", false_alarms / len(predicted) if predicted else None, "fraction"),
                    ("correlation", numerator / denominator if denominator else None, "coefficient"),
                    ("mean_bias", mb - ma, UNIT[name])):
                if value is None:
                    continue
                rows.append([args.name, round(args.lat, 4), round(args.lon, 4),
                             args.start[:10], args.end[:10], name, lead,
                             args.percentile, len(common), metric, round(value, 6), unit])

    stored = read_rows(OUTPUT)
    run_key = (args.name, f"{args.lat:.4f}", f"{args.lon:.4f}", args.start[:10],
               args.end[:10], str(args.percentile))
    stored = [row for row in stored if (
        row["site"], f"{float(row['lat']):.4f}", f"{float(row['lon']):.4f}",
        row["period_start"], row["period_end"], row["percentile"]
    ) != run_key]
    stored.extend(dict(zip(FIELDS, row)) for row in rows)
    write_rows(OUTPUT, stored)
    print(f"\n  {len(rows):,} verification metrics -> {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
