"""Build transboundary headwater anomalies from ERA5-Land observations.

The baseline is calculated for 1991-2020 from the same Earth Engine asset,
spatial frame, variables and reduction scale as the current headwater table.
Historical monthly images are stacked by calendar month so only one remote
reduction is needed per month represented in the observation table.

    python PIPELINES/era5_headwater_anomaly_service.py
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from update_headwater_era5 import ASSET, PROJECT, SCALE, VARIABLES

ROOT = Path(__file__).resolve().parent.parent
GEOMETRY = ROOT / "PUBLISHED/data/hydroclimate/headwater-units.geojson"
OBSERVATIONS = ROOT / "PUBLISHED/data/hydroclimate/era5-land-headwaters-monthly.csv"
CLIMATOLOGY = ROOT / "PUBLISHED/data/hydroclimate/era5-land-headwater-climatology.csv"
ANOMALIES = ROOT / "PUBLISHED/data/hydroclimate/era5-land-headwater-anomaly.csv"
JSON_OUTPUT = ROOT / "PUBLISHED/data/hydroclimate/era5-land-headwater-anomaly.json"
MANIFEST = ROOT / "PUBLISHED/data/hydroclimate/era5-land-headwater-anomaly.manifest.json"

BASELINE_START = 1991
BASELINE_END = 2020

CLIMATOLOGY_FIELDS = [
    "system_id", "basin_id", "month", "variable", "mean", "sd", "unit",
    "years", "baseline_start", "baseline_end", "source_asset", "scale_m",
]
ANOMALY_FIELDS = [
    "system_id", "basin_id", "year", "month", "period_start", "variable",
    "value", "unit", "z_score", "classification", "baseline_mean", "baseline_sd",
    "baseline_start", "baseline_end", "source_asset", "source_image", "scale_m",
    "quality", "retrieved_at",
]


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def classification(variable: str, z_score: float) -> str:
    if variable == "air_temperature_mean":
        labels = ["extremely cold", "cold", "normal", "hot", "extremely hot"]
    else:
        labels = ["extremely low", "low", "normal", "high", "extremely high"]
    if z_score < -2:
        return labels[0]
    if z_score < -1:
        return labels[1]
    if z_score < 1:
        return labels[2]
    if z_score < 2:
        return labels[3]
    return labels[4]


def transformed_image(ee, image, suffix: str):
    return ee.Image.cat([
        image.select(variable.source)
        .multiply(variable.factor)
        .add(variable.offset)
        .rename(f"{variable.code}__{suffix}")
        for variable in VARIABLES
    ])


def fetch_climatology(months: list[int]) -> list[dict]:
    try:
        import ee

        ee.Initialize(project=PROJECT)
        ee.Number(1).getInfo()
    except Exception as error:
        raise SystemExit(
            f"Earth Engine unavailable: {str(error).strip()[:180]}\n"
            f"  Run: earthengine authenticate --project {PROJECT}"
        ) from error

    document = json.loads(GEOMETRY.read_text(encoding="utf-8"))
    features = [
        ee.Feature(ee.Geometry(feature["geometry"]), {
            "basin_id": int(feature["properties"]["HYBAS_ID"]),
            "system_id": feature["properties"]["system_id"],
        })
        for feature in document["features"]
    ]
    basins = ee.FeatureCollection(features)
    source = ee.ImageCollection(ASSET)
    rows: list[dict] = []

    for position, month in enumerate(months, start=1):
        images = []
        names = []
        for year in range(BASELINE_START, BASELINE_END + 1):
            begin = ee.Date.fromYMD(year, month, 1)
            image = source.filterDate(begin, begin.advance(1, "month")).first()
            images.append(transformed_image(ee, image, str(year)))
            names.extend(f"{variable.code}__{year}" for variable in VARIABLES)
        reduced = ee.Image.cat(images).reduceRegions(
            collection=basins,
            reducer=ee.Reducer.mean(),
            scale=SCALE,
            tileScale=4,
        ).select(["basin_id", "system_id", *names], retainGeometry=False).getInfo()

        for feature in reduced["features"]:
            props = feature["properties"]
            for variable in VARIABLES:
                values = [
                    float(props[f"{variable.code}__{year}"])
                    for year in range(BASELINE_START, BASELINE_END + 1)
                    if props.get(f"{variable.code}__{year}") is not None
                ]
                if not values:
                    continue
                rows.append({
                    "system_id": props["system_id"],
                    "basin_id": int(props["basin_id"]),
                    "month": month,
                    "variable": variable.code,
                    "mean": f"{statistics.mean(values):.5f}",
                    "sd": f"{statistics.pstdev(values):.5f}" if len(values) >= 3 else "",
                    "unit": variable.unit,
                    "years": len(values),
                    "baseline_start": BASELINE_START,
                    "baseline_end": BASELINE_END,
                    "source_asset": ASSET,
                    "scale_m": SCALE,
                })
        print(f"  baseline month {month:02d} ({position}/{len(months)})", flush=True)
    return sorted(rows, key=lambda row: (row["system_id"], row["basin_id"], row["month"], row["variable"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-baseline", action="store_true", help="Refetch the fixed 1991-2020 normal.")
    args = parser.parse_args()
    if not OBSERVATIONS.exists() or not GEOMETRY.exists():
        raise SystemExit("Headwater observations or geometry are absent; run headwaters:basins and headwaters:era5.")

    with OBSERVATIONS.open(encoding="utf-8", newline="") as handle:
        observations = list(csv.DictReader(handle))
    months = sorted({int(row["month"]) for row in observations})
    print(f"ERA5-Land headwater anomaly | baseline {BASELINE_START}-{BASELINE_END} | months {months}")
    previous = []
    if CLIMATOLOGY.exists() and not args.refresh_baseline:
        with CLIMATOLOGY.open(encoding="utf-8", newline="") as handle:
            previous = list(csv.DictReader(handle))
    covered_months = {int(row["month"]) for row in previous}
    missing_months = months if args.refresh_baseline else [month for month in months if month not in covered_months]
    refreshed = fetch_climatology(missing_months) if missing_months else []
    climatology_by_key = {
        (row["system_id"], str(row["basin_id"]), int(row["month"]), row["variable"]): row
        for row in previous
    }
    climatology_by_key.update({
        (row["system_id"], str(row["basin_id"]), int(row["month"]), row["variable"]): row
        for row in refreshed
    })
    climatology = [climatology_by_key[key] for key in sorted(climatology_by_key)]
    write_csv(CLIMATOLOGY, CLIMATOLOGY_FIELDS, climatology)

    baseline = {
        (row["system_id"], str(row["basin_id"]), int(row["month"]), row["variable"]): row
        for row in climatology
    }
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    anomalies: list[dict] = []
    skipped = 0
    for row in observations:
        reference = baseline.get((row["system_id"], row["basin_id"], int(row["month"]), row["variable"]))
        if not reference or not reference["sd"] or float(reference["sd"]) <= 0:
            skipped += 1
            continue
        value = float(row["value"])
        mean = float(reference["mean"])
        sd = float(reference["sd"])
        z_score = (value - mean) / sd
        if not math.isfinite(z_score):
            skipped += 1
            continue
        anomalies.append({
            **{field: row[field] for field in (
                "system_id", "basin_id", "year", "month", "period_start", "variable", "value", "unit"
            )},
            "z_score": f"{z_score:.5f}",
            "classification": classification(row["variable"], z_score),
            "baseline_mean": reference["mean"],
            "baseline_sd": reference["sd"],
            "baseline_start": BASELINE_START,
            "baseline_end": BASELINE_END,
            "source_asset": row["source_asset"],
            "source_image": row["source_image"],
            "scale_m": row["scale_m"],
            "quality": "review-extreme-reanalysis-anomaly" if abs(z_score) > 5 else "ok-reanalysis-anomaly",
            "retrieved_at": generated,
        })

    write_csv(ANOMALIES, ANOMALY_FIELDS, anomalies)
    JSON_OUTPUT.write_text(json.dumps({
        "version": "1.0",
        "temporalResolution": "month",
        "baseline": {"start": BASELINE_START, "end": BASELINE_END},
        "observations": anomalies,
    }, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    MANIFEST.write_text(json.dumps({
        "version": "1.0",
        "generatedAt": generated,
        "spatialScope": "headwater_formation",
        "spatialUnit": "HydroATLAS level-7 subbasin",
        "temporalResolution": "month",
        "baseline": {"start": BASELINE_START, "end": BASELINE_END, "kind": "fixed climate normal"},
        "source": {"asset": ASSET, "nominalScaleMetres": SCALE},
        "coverage": {
            "rows": len(anomalies),
            "basins": len({row["basin_id"] for row in anomalies}),
            "systems": len({row["system_id"] for row in anomalies}),
            "periods": sorted({row["period_start"][:7] for row in anomalies}),
            "variables": sorted({row["variable"] for row in anomalies}),
            "skipped": skipped,
        },
        "outputs": {
            "climatologyCSV": str(CLIMATOLOGY.relative_to(ROOT)).replace("\\", "/"),
            "anomalyCSV": str(ANOMALIES.relative_to(ROOT)).replace("\\", "/"),
            "anomalyJSON": str(JSON_OUTPUT.relative_to(ROOT)).replace("\\", "/"),
        },
        "qualityNotes": [
            "Current values and the baseline use the same ERA5-Land asset, basin geometry and scale.",
            "The 1991-2020 baseline is fixed and does not move when new observations are appended.",
            "These are reanalysis anomalies, not station or gauge anomalies.",
            "Absolute z-scores above 5 are retained but flagged for review rather than silently removed.",
        ],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  {len(climatology):,} climatology cells; {len(anomalies):,} anomalies; {skipped:,} skipped")


if __name__ == "__main__":
    main()
