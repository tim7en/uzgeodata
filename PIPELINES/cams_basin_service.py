"""CAMS atmospheric composition per basin, and how far its forecasts can be trusted.

CAMS is the first forecast product in the ontology, and that changes what has to
be stored. Every other source records a state that happened. CAMS issues two
five-day forecasts a day, so for any given moment it holds up to eleven images:
the analysis at +0h, and forecasts made 12 to 120 hours earlier that were aiming
at it. They disagree, and the disagreement is itself a measurement.

So this writes two tables.

    state       The +0h analysis per basin per day — the assimilated estimate of
                what the atmosphere actually was. This is the layer to join
                against everything else in the ontology.

    skill       Forecast against analysis at each lead time, as mean absolute
                error, bias and correlation. It answers how far ahead the product
                is worth believing, which a user of the state table needs to know
                and cannot derive from it.

One thing to be exact about: **this verifies forecasts against the analysis, not
against observations.** The +0h analysis is itself a model state, constrained by
assimilated satellite retrievals rather than measured directly. It is the
standard reference and the one ECMWF uses, but a forecast agreeing with it means
the model agreed with itself. Independent ground truth would need surface
monitors or AERONET sites, and Uzbekistan has very few of either.

Read at basin level 6. The grid is 0.4°, which at this latitude is 44.2 by
33.3 km — about 1,470 km² — so a level-7 basin covers 1.9 pixels, just under the
two-pixel floor, and a level-6 basin covers 6.7. Levels 9 and 12 would be 0.2 and
0.1 of a pixel: hundreds of basins sharing one number.

Before 2021-07-01 only two parameters exist — aerosol optical depth and PM2.5 —
so those are what this reads, for a record that runs whole.

    python PIPELINES/cams_basin_service.py state --start 2026-07 --end 2026-08
    python PIPELINES/cams_basin_service.py skill --start 2026-07 --end 2026-08
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ontology_paths import dataset_dir

ROOT = Path(__file__).resolve().parent.parent
BASINS = ROOT / "PUBLISHED" / "data" / "review" / "basinatlas" / "basinatlas_uz_lev06.geojson"
STATE = dataset_dir("CAMS_BASIN_DAILY", "ATMOSPHERE") / "cams-basin-daily.csv"
SKILL = dataset_dir("CAMS_FORECAST_SKILL", "ATMOSPHERE") / "cams-forecast-skill.csv"

PROJECT = "ee-sabitovty"
ASSET = "ECMWF/CAMS/NRT"
SCALE = 44453

# Only these two exist before 2021-07-01, so only these give a record that runs
# the whole way back without a silent change of content partway through.
VARIABLES = {
    "total_aerosol_optical_depth_at_550nm_surface": ("aod_550nm", "index", 1.0),
    # kg/m3 is unreadable at these magnitudes; micrograms per cubic metre is the
    # unit air quality is actually discussed in, and the conversion is exact.
    "particulate_matter_d_less_than_25_um_surface": ("pm2p5", "ug/m3", 1e9),
}
LEADS = (24, 48, 72, 96, 120)


def months(start: str, end: str):
    sy, sm = (int(p) for p in start.split("-"))
    ey, em = (int(p) for p in end.split("-"))
    year, month = sy, sm
    while (year, month) <= (ey, em):
        yield year, month
        month = month + 1 if month < 12 else 1
        if month == 1:
            year += 1


def initialise():
    try:
        import ee
        ee.Initialize(project=PROJECT)
        ee.Number(1).getInfo()
        return ee
    except Exception as error:
        raise SystemExit(f"Earth Engine unavailable: {str(error).strip()[:150]}\n"
                         f"  Run: earthengine authenticate --project {PROJECT}") from error


def basins(ee):
    document = json.loads(BASINS.read_text(encoding="utf8"))
    return ee.FeatureCollection([
        ee.Feature(ee.Geometry(f["geometry"]), {"basin": int(f["properties"]["HYBAS_ID"])})
        for f in document["features"]]), len(document["features"])


def state(args) -> None:
    """Monthly mean of the +0h analysis per basin."""
    ee = initialise()
    collection, count = basins(ee)
    source = ee.ImageCollection(ASSET).filter(ee.Filter.eq("model_forecast_hour", 0))

    done = set()
    if STATE.exists():
        with STATE.open(encoding="utf-8-sig", newline="") as handle:
            done = {(r["year"], r["month"]) for r in csv.DictReader(handle)}
    todo = [(y, m) for y, m in months(args.start, args.end) if (str(y), str(m)) not in done]

    print(f"CAMS state · {count} level-6 basins · {len(todo)} months")
    if not todo:
        print("  nothing to do")
        return

    STATE.parent.mkdir(parents=True, exist_ok=True)
    fresh = not STATE.exists()
    started, rows = time.time(), 0
    with STATE.open("a", encoding="utf8", newline="") as handle:
        writer = csv.writer(handle)
        if fresh:
            writer.writerow(["basin_id", "year", "month", "analyses",
                             "variable", "value", "unit", "quality"])
        for position, (year, month) in enumerate(todo, start=1):
            start = ee.Date.fromYMD(year, month, 1)
            window = source.filterDate(start, start.advance(1, "month")).select(list(VARIABLES))
            n = window.size().getInfo()
            if n == 0:
                print(f"  {year}-{month:02d}: no analyses", flush=True)
                continue
            try:
                result = window.mean().reduceRegions(
                    collection=collection, reducer=ee.Reducer.mean(), scale=SCALE).getInfo()
            except Exception as error:
                print(f"  ! {year}-{month:02d}: {str(error).strip()[:100]}", flush=True)
                continue
            for feature in result["features"]:
                properties = feature["properties"]
                for band, (name, unit, factor) in VARIABLES.items():
                    raw = properties.get(band)
                    if raw is None:
                        continue
                    value = raw * factor
                    writer.writerow([properties["basin"], year, month, n, name,
                                     round(value, 6), unit,
                                     "ok" if value >= 0 else "implausible"])
                    rows += 1
            handle.flush()
            rate = (time.time() - started) / position
            print(f"  {year}-{month:02d} · {position}/{len(todo)} · {rate:.0f}s each", flush=True)
    print(f"\n  {rows:,} observations -> {STATE.relative_to(ROOT)}")


def skill(args) -> None:
    """Forecast against analysis at each lead time, over the country."""
    ee = initialise()
    source = ee.ImageCollection(ASSET)
    region = ee.Geometry.Rectangle([56, 37.2, 73.2, 45.6])

    rows = []
    for year, month in months(args.start, args.end):
        start = ee.Date.fromYMD(year, month, 1)
        end = start.advance(1, "month")
        for band, (name, unit, factor) in VARIABLES.items():
            series = {}
            for lead in (0, *LEADS):
                window = (source.filterDate(start, end)
                          .filter(ee.Filter.eq("model_forecast_hour", lead)).select(band))

                def one(image, b=band):
                    value = image.reduceRegion(ee.Reducer.mean(), region, SCALE,
                                               maxPixels=1e9).get(b)
                    return ee.Feature(None, {"t": image.get("system:time_start"), "v": value})

                try:
                    features = ee.FeatureCollection(window.map(one)).getInfo()["features"]
                except Exception as error:
                    print(f"  ! {year}-{month:02d} {name} +{lead}h: {str(error).strip()[:80]}")
                    continue
                series[lead] = {f["properties"]["t"]: f["properties"]["v"] * factor
                                for f in features if f["properties"].get("v") is not None}
            truth = series.get(0, {})
            if len(truth) < 5:
                continue
            mean_truth = sum(truth.values()) / len(truth)
            for lead in LEADS:
                pairs = [(truth[t], series.get(lead, {})[t])
                         for t in series.get(lead, {}) if t in truth]
                if len(pairs) < 5:
                    continue
                errors = [b - a for a, b in pairs]
                mae = sum(abs(e) for e in errors) / len(errors)
                bias = sum(errors) / len(errors)
                ma = sum(a for a, _ in pairs) / len(pairs)
                mb = sum(b for _, b in pairs) / len(pairs)
                numerator = sum((a - ma) * (b - mb) for a, b in pairs)
                denominator = math.sqrt(sum((a - ma) ** 2 for a, _ in pairs)
                                        * sum((b - mb) ** 2 for _, b in pairs))
                correlation = numerator / denominator if denominator else None
                for metric, value, metric_unit in (
                        ("mae", mae, unit), ("bias", bias, unit),
                        ("mae_percent_of_mean", mae / mean_truth * 100 if mean_truth else None, "percent"),
                        ("correlation", correlation, "coefficient")):
                    if value is None:
                        continue
                    rows.append([year, month, name, lead, len(pairs), metric,
                                 round(value, 6), metric_unit])
            print(f"  {year}-{month:02d} {name}: {len(truth)} analyses, "
                  f"{len([r for r in rows if r[2] == name])} metrics", flush=True)

    if not rows:
        print("  nothing measured")
        return
    SKILL.parent.mkdir(parents=True, exist_ok=True)
    fresh = not SKILL.exists()
    with SKILL.open("a", encoding="utf8", newline="") as handle:
        writer = csv.writer(handle)
        if fresh:
            writer.writerow(["year", "month", "variable", "lead_hours", "pairs",
                             "metric", "value", "unit"])
        writer.writerows(rows)
    print(f"\n  {len(rows):,} skill metrics -> {SKILL.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="service", required=True)
    for name, run in (("state", state), ("skill", skill)):
        p = sub.add_parser(name)
        p.add_argument("--start", default="2026-07")
        p.add_argument("--end", default="2026-08")
        p.set_defaults(run=run)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
