"""Update monthly hydroclimate state for the transboundary headwater pilot.

ERA5-Land is a reanalysis, so runoff and snow variables are modelled estimates,
not gauge observations. Monthly flow bands are sums; state bands are monthly
means. Values are reduced onto the level-7 units built by
``build_headwater_pilot.py``.

    python PIPELINES/update_headwater_era5.py
    python PIPELINES/update_headwater_era5.py --start 2026-01
    python PIPELINES/update_headwater_era5.py --start 2025-01 --end 2025-12
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PILOT = ROOT / "PUBLISHED/data/hydroclimate/headwater-units.geojson"
OUTPUT = ROOT / "PUBLISHED/data/hydroclimate/era5-land-headwaters-monthly.csv"
SYSTEM_OUTPUT = ROOT / "PUBLISHED/data/hydroclimate/era5-land-headwater-systems-monthly.csv"
MANIFEST = ROOT / "PUBLISHED/data/hydroclimate/era5-land-headwaters-monthly.manifest.json"

PROJECT = "ee-sabitovty"
BASIN_ASSET = "WWF/HydroATLAS/v1/Basins/level07"
ASSET = "ECMWF/ERA5_LAND/MONTHLY_AGGR"
SCALE = 11132


@dataclass(frozen=True)
class Variable:
    source: str
    code: str
    unit: str
    statistic: str
    factor: float = 1.0
    offset: float = 0.0


VARIABLES = [
    Variable("temperature_2m", "air_temperature_mean", "degC", "monthly_mean", 1.0, -273.15),
    Variable("total_precipitation_sum", "precipitation_total", "mm", "monthly_sum", 1000.0),
    Variable("snowfall_sum", "snowfall_water_equivalent_total", "mm", "monthly_sum", 1000.0),
    Variable("snow_depth_water_equivalent", "snow_water_equivalent_mean", "mm", "monthly_mean", 1000.0),
    Variable("volumetric_soil_water_layer_1", "soil_moisture_layer_1_mean", "m3/m3", "monthly_mean"),
    Variable("runoff_sum", "modelled_runoff_total", "mm", "monthly_sum", 1000.0),
]

FIELDS = [
    "system_id", "basin_id", "year", "month", "period_start", "variable", "value",
    "unit", "statistic", "source_asset", "source_image", "scale_m", "quality",
    "retrieved_at",
]


def month_tuple(value: str) -> tuple[int, int]:
    try:
        year, month = (int(part) for part in value.split("-"))
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError("month must be YYYY-MM") from error
    if year < 1900 or not 1 <= month <= 12:
        raise argparse.ArgumentTypeError("month must be YYYY-MM")
    return year, month


def next_month(period: tuple[int, int]) -> tuple[int, int]:
    year, month = period
    return (year + 1, 1) if month == 12 else (year, month + 1)


def previous_month(period: tuple[int, int]) -> tuple[int, int]:
    year, month = period
    return (year - 1, 12) if month == 1 else (year, month - 1)


def shift_month(period: tuple[int, int], count: int) -> tuple[int, int]:
    result = period
    step = next_month if count >= 0 else previous_month
    for _ in range(abs(count)):
        result = step(result)
    return result


def months(start: tuple[int, int], end: tuple[int, int]):
    current = start
    while current <= end:
        yield current
        current = next_month(current)


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def merge_rows(previous: list[dict], fresh: list[dict]) -> list[dict]:
    key = lambda row: (
        row["system_id"], int(row["basin_id"]), int(row["year"]), int(row["month"]), row["variable"]
    )
    merged = {key(row): row for row in previous}
    merged.update({key(row): row for row in fresh})
    return [merged[item] for item in sorted(merged)]


def aggregate_systems(rows: list[dict], basin_areas: dict[int, float]) -> list[dict]:
    groups: dict[tuple, list[tuple[float, float]]] = {}
    metadata: dict[tuple, dict] = {}
    for row in rows:
        group = (row["system_id"], int(row["year"]), int(row["month"]), row["variable"])
        area = basin_areas[int(row["basin_id"])]
        groups.setdefault(group, []).append((float(row["value"]), area))
        metadata[group] = row

    result = []
    for group in sorted(groups):
        values = groups[group]
        total_area = sum(area for _, area in values)
        mean = sum(value * area for value, area in values) / total_area
        row = metadata[group]
        result.append({
            "system_id": group[0],
            "year": group[1],
            "month": group[2],
            "period_start": row["period_start"],
            "variable": group[3],
            "value": f"{mean:.5f}",
            "unit": row["unit"],
            "statistic": "subbasin_area_weighted_mean",
            "basin_count": len(values),
            "area_km2": f"{total_area:.1f}",
            "source_asset": ASSET,
            "quality": "ok-reanalysis",
            "retrieved_at": row["retrieved_at"],
        })
    return result


def write_manifest(
    rows: list[dict], latest: tuple[int, int], retrieved: str, *,
    manifest_path: Path = MANIFEST, geometry_path: Path = PILOT,
    spatial_scope: str = "headwater_formation",
) -> None:
    periods = sorted({f"{int(r['year']):04d}-{int(r['month']):02d}" for r in rows})
    payload = {
        "version": "1.0",
        "generatedAt": retrieved,
        "hydroclimateStage": "source",
        "datasetKind": "reanalysis",
        "source": {
            "platform": "Google Earth Engine",
            "asset": ASSET,
            "catalogUrl": "https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_MONTHLY_AGGR",
            "latestAvailableMonth": f"{latest[0]:04d}-{latest[1]:02d}",
            "nominalScaleMetres": SCALE,
            "retrievedAt": retrieved,
        },
        "spatialFrame": {
            "asset": BASIN_ASSET,
            "basinLevel": 7,
            "scope": spatial_scope,
            "selection": (
                "all units in the complete Amu Darya and Syr Darya natural systems"
                if spatial_scope == "full_basin"
                else "transboundary units upstream of the declared pilot control sections"
            ),
            "geometry": str(geometry_path.relative_to(ROOT)).replace("\\", "/"),
        },
        "variables": [variable.__dict__ for variable in VARIABLES],
        "coverage": {
            "rows": len(rows),
            "systems": len({r["system_id"] for r in rows}),
            "basins": len({r["basin_id"] for r in rows}),
            "periods": periods,
        },
        "qualityNotes": [
            "ERA5-Land is a model reanalysis constrained by observations; it is not a station or gauge record.",
            "Monthly *_sum bands are accumulated flows; temperature, SWE and soil moisture are monthly states.",
            "Modelled runoff is a formation indicator and must not be labelled observed river discharge.",
            "ERA5-Land has an approximately three-month publication lag; latest availability is queried at runtime.",
            "A polygon smaller than one ERA5-Land pixel is sampled at its representative centroid and explicitly flagged ok-reanalysis-centroid.",
        ],
    }
    temporary = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temporary, manifest_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=month_tuple, help="First month, YYYY-MM.")
    parser.add_argument("--end", type=month_tuple, help="Last month, YYYY-MM; defaults to latest available.")
    parser.add_argument(
        "--scope", choices=("headwaters", "full-basin"), default="headwaters",
        help="Use the pilot formation units or every level-7 unit in both complete river systems.",
    )
    args = parser.parse_args()

    full_basin = args.scope == "full-basin"
    geometry = ROOT / "PUBLISHED/data/hydroclimate/basins-level07.geojson" if full_basin else PILOT
    output = ROOT / "PUBLISHED/data/hydroclimate/era5-land-full-basins-monthly.csv" if full_basin else OUTPUT
    system_output = ROOT / "PUBLISHED/data/hydroclimate/era5-land-river-systems-monthly.csv" if full_basin else SYSTEM_OUTPUT
    manifest_path = ROOT / "PUBLISHED/data/hydroclimate/era5-land-full-basins-monthly.manifest.json" if full_basin else MANIFEST
    spatial_scope = "full_basin" if full_basin else "headwater_formation"

    if not geometry.exists():
        raise SystemExit(f"Basin geometry is absent: {geometry.relative_to(ROOT)}")

    try:
        import ee

        ee.Initialize(project=PROJECT)
        ee.Number(1).getInfo()
    except Exception as error:
        raise SystemExit(
            f"Earth Engine unavailable: {str(error).strip()[:180]}\n"
            f"  Run: earthengine authenticate --project {PROJECT}"
        ) from error

    pilot = json.loads(geometry.read_text(encoding="utf-8"))
    feature_rows = [feature["properties"] for feature in pilot["features"]]
    systems: dict[str, list[int]] = {}
    basin_areas: dict[int, float] = {}
    for props in feature_rows:
        basin_id = int(props["HYBAS_ID"])
        systems.setdefault(props["system_id"], []).append(basin_id)
        basin_areas[basin_id] = float(props["SUB_AREA"])

    source = ee.ImageCollection(ASSET)
    latest_image = source.sort("system:time_start", False).first()
    latest_text = latest_image.date().format("YYYY-MM").getInfo()
    latest = month_tuple(latest_text)
    end = args.end or latest
    if end > latest:
        raise SystemExit(f"Requested end {end[0]:04d}-{end[1]:02d} exceeds latest available {latest_text}")

    previous = read_rows(output)
    if args.start:
        start = args.start
    elif previous:
        newest = max((int(row["year"]), int(row["month"])) for row in previous)
        start = next_month(newest)
    else:
        start = shift_month(end, -11)
    if start > end:
        print(f"ERA5-Land already current through {end[0]:04d}-{end[1]:02d}")
        return

    basin_source = ee.FeatureCollection(BASIN_ASSET)
    basin_collection = None
    for system_id, ids in sorted(systems.items()):
        part = basin_source.filter(ee.Filter.inList("HYBAS_ID", ids)).map(
            lambda feature, value=system_id: feature.set("system_id", value)
        )
        basin_collection = part if basin_collection is None else basin_collection.merge(part)

    transformed_names = [variable.code for variable in VARIABLES]
    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    fresh: list[dict] = []
    periods = list(months(start, end))
    print(
        f"ERA5-Land monthly | {len(feature_rows)} basins | "
        f"{start[0]:04d}-{start[1]:02d}..{end[0]:04d}-{end[1]:02d}"
    )
    for position, (year, month) in enumerate(periods, start=1):
        begin = ee.Date.fromYMD(year, month, 1)
        finish = begin.advance(1, "month")
        image = source.filterDate(begin, finish).first()
        source_index = image.get("system:index").getInfo()
        bands = [
            image.select(variable.source).multiply(variable.factor).add(variable.offset).rename(variable.code)
            for variable in VARIABLES
        ]
        transformed = ee.Image.cat(bands)
        reduced = transformed.reduceRegions(
            collection=basin_collection,
            reducer=ee.Reducer.mean(),
            scale=SCALE,
            tileScale=4,
        ).select(["system_id", "HYBAS_ID", *transformed_names], retainGeometry=False)
        info = reduced.getInfo()
        returned_ids = {int(feature["properties"]["HYBAS_ID"]) for feature in info["features"]}
        if returned_ids != set(basin_areas):
            missing = sorted(set(basin_areas) - returned_ids)
            raise RuntimeError(f"{year}-{month:02d}: missing basin reductions: {missing[:10]}")

        # A very small polygon may contain no ERA5 pixel centre.  Keep it by
        # sampling a representative point and declare that fallback in quality.
        features_by_id = {
            int(feature["properties"]["HYBAS_ID"]): feature
            for feature in info["features"]
        }
        fallback_ids = [
            basin_id for basin_id, feature in features_by_id.items()
            if any(feature["properties"].get(name) is None for name in transformed_names)
        ]
        if fallback_ids:
            points = basin_collection.filter(ee.Filter.inList("HYBAS_ID", fallback_ids)).map(
                lambda feature: feature.setGeometry(feature.geometry().centroid(100))
            )
            sampled = transformed.sampleRegions(
                collection=points,
                properties=["system_id", "HYBAS_ID"],
                scale=SCALE,
                geometries=False,
            ).getInfo()
            for feature in sampled["features"]:
                features_by_id[int(feature["properties"]["HYBAS_ID"])] = feature
            unresolved = [
                basin_id for basin_id in fallback_ids
                if basin_id not in features_by_id
                or any(features_by_id[basin_id]["properties"].get(name) is None for name in transformed_names)
            ]
            if unresolved:
                raise RuntimeError(f"{year}-{month:02d}: sub-pixel fallback failed: {unresolved[:10]}")

        for basin_id in sorted(features_by_id):
            feature = features_by_id[basin_id]
            props = feature["properties"]
            for variable in VARIABLES:
                value = props.get(variable.code)
                if value is None:
                    continue
                fresh.append({
                    "system_id": props["system_id"],
                    "basin_id": int(props["HYBAS_ID"]),
                    "year": year,
                    "month": month,
                    "period_start": f"{year:04d}-{month:02d}-01",
                    "variable": variable.code,
                    "value": f"{float(value):.5f}",
                    "unit": variable.unit,
                    "statistic": variable.statistic,
                    "source_asset": ASSET,
                    "source_image": source_index,
                    "scale_m": SCALE,
                    "quality": "ok-reanalysis-centroid" if basin_id in fallback_ids else "ok-reanalysis",
                    "retrieved_at": retrieved,
                })
        print(f"  {year:04d}-{month:02d} ({position}/{len(periods)})", flush=True)

    merged = merge_rows(previous, fresh)
    write_csv(output, FIELDS, merged)
    system_rows = aggregate_systems(merged, basin_areas)
    system_fields = [
        "system_id", "year", "month", "period_start", "variable", "value", "unit",
        "statistic", "basin_count", "area_km2", "source_asset", "quality", "retrieved_at",
    ]
    write_csv(system_output, system_fields, system_rows)
    write_manifest(
        merged, latest, retrieved, manifest_path=manifest_path,
        geometry_path=geometry, spatial_scope=spatial_scope,
    )
    print(f"  {len(fresh):,} refreshed rows; {len(merged):,} total -> {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
