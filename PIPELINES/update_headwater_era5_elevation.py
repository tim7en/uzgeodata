"""Update monthly ERA5-Land state by headwater system and elevation band.

This is the elevation-aware companion to update_headwater_era5.py. It retains
ERA5-Land's native monthly grain and uses the same variable conversions while
adding the configured SRTM elevation-band dimension.

    python PIPELINES/update_headwater_era5_elevation.py --start 2026-01
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from update_headwater_era5 import ASSET, PROJECT, SCALE, VARIABLES, month_tuple, months, next_month, shift_month

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "ONTOLOGY/vocab/hydroclimate-system.json"
SYSTEMS = ROOT / "PUBLISHED/data/hydroclimate/headwater-systems.geojson"
AREAS = ROOT / "PUBLISHED/data/hydroclimate/headwater-elevation-bands.csv"
OUTPUT = ROOT / "PUBLISHED/data/hydroclimate/era5-land-headwater-elevation-monthly.csv"
JSON_OUTPUT = ROOT / "PUBLISHED/data/hydroclimate/era5-land-headwater-elevation-monthly.json"
MANIFEST = ROOT / "PUBLISHED/data/hydroclimate/era5-land-headwater-elevation-monthly.manifest.json"
DEM_ASSET = "USGS/SRTMGL1_003"
FIELDS = [
    "observation_unit_id", "system_id", "river_system_id", "elevation_band",
    "minimum_m_inclusive", "maximum_m_exclusive", "area_km2", "year", "month",
    "period_start", "variable", "value", "unit", "statistic", "source_asset",
    "source_image", "scale_m", "quality", "retrieved_at",
]


def existing_rows() -> list[dict]:
    if not OUTPUT.exists():
        return []
    with OUTPUT.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def merge_rows(previous: list[dict], fresh: list[dict]) -> list[dict]:
    def key(row):
        return row["observation_unit_id"], int(row["year"]), int(row["month"]), row["variable"]

    merged = {key(row): row for row in previous}
    merged.update({key(row): row for row in fresh})
    return [merged[item] for item in sorted(merged)]


def write_csv(rows: list[dict]) -> None:
    temporary = OUTPUT.with_suffix(OUTPUT.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, OUTPUT)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=month_tuple)
    parser.add_argument("--end", type=month_tuple)
    args = parser.parse_args()

    try:
        import ee

        ee.Initialize(project=PROJECT)
        ee.Number(1).getInfo()
    except Exception as error:
        raise SystemExit(
            f"Earth Engine unavailable: {str(error).strip()[:180]}\n"
            f"  Run: earthengine authenticate --project {PROJECT}"
        ) from error

    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    system_doc = json.loads(SYSTEMS.read_text(encoding="utf-8"))
    system_fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry(feature["geometry"]), feature["properties"])
        for feature in system_doc["features"]
    ])
    with AREAS.open(encoding="utf-8", newline="") as handle:
        area_lookup = {
            (row["system_id"], row["elevation_band"]): row["area_km2"]
            for row in csv.DictReader(handle)
        }
    bands = config["elevationBandsMetres"]
    dem = ee.Image(DEM_ASSET).select("elevation")
    source = ee.ImageCollection(ASSET)
    latest_text = source.sort("system:time_start", False).first().date().format("YYYY-MM").getInfo()
    latest = month_tuple(latest_text)
    end = args.end or latest
    if end > latest:
        raise SystemExit(f"Requested end exceeds latest available month {latest_text}")
    previous = existing_rows()
    if args.start:
        start = args.start
    elif previous:
        start = next_month(max((int(row["year"]), int(row["month"])) for row in previous))
    else:
        start = shift_month(end, -11)
    if start > end:
        print(f"Elevation-aware ERA5-Land already current through {latest_text}")
        return

    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    fresh: list[dict] = []
    periods = list(months(start, end))
    print(f"ERA5-Land by elevation | {start[0]:04d}-{start[1]:02d}..{end[0]:04d}-{end[1]:02d}")
    for position, (year, month) in enumerate(periods, start=1):
        begin = ee.Date.fromYMD(year, month, 1)
        image = source.filterDate(begin, begin.advance(1, "month")).first()
        source_index = image.get("system:index").getInfo()
        output_bands = []
        for band in bands:
            elevation_mask = ee.Image(1)
            if band["minimum"] is not None:
                elevation_mask = elevation_mask.And(dem.gte(band["minimum"]))
            if band["maximum"] is not None:
                elevation_mask = elevation_mask.And(dem.lt(band["maximum"]))
            for variable in VARIABLES:
                output_bands.append(
                    image.select(variable.source)
                    .multiply(variable.factor)
                    .add(variable.offset)
                    .updateMask(elevation_mask)
                    .rename(f"{variable.code}__{band['id']}")
                )
        names = [f"{variable.code}__{band['id']}" for band in bands for variable in VARIABLES]
        reduced = ee.Image.cat(output_bands).reduceRegions(
            collection=system_fc,
            reducer=ee.Reducer.mean(),
            scale=SCALE,
            maxPixelsPerRegion=1_000_000,
            tileScale=4,
        ).select(["system_id", "river_system_id", *names], retainGeometry=False).getInfo()
        for feature in reduced["features"]:
            props = feature["properties"]
            for band in bands:
                for variable in VARIABLES:
                    value = props.get(f"{variable.code}__{band['id']}")
                    if value is None:
                        continue
                    unit_id = f"{props['system_id']}::{band['id']}"
                    fresh.append({
                        "observation_unit_id": unit_id,
                        "system_id": props["system_id"],
                        "river_system_id": props["river_system_id"],
                        "elevation_band": band["id"],
                        "minimum_m_inclusive": "" if band["minimum"] is None else band["minimum"],
                        "maximum_m_exclusive": "" if band["maximum"] is None else band["maximum"],
                        "area_km2": area_lookup[(props["system_id"], band["id"])],
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
                        "quality": "ok-reanalysis",
                        "retrieved_at": retrieved,
                    })
        print(f"  {year:04d}-{month:02d} ({position}/{len(periods)})", flush=True)

    merged = merge_rows(previous, fresh)
    write_csv(merged)
    JSON_OUTPUT.write_text(
        json.dumps({"version": "1.0", "temporalResolution": "month", "observations": merged}, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "version": "1.0",
        "generatedAt": retrieved,
        "temporalResolution": "month",
        "spatialDimensions": ["headwater_formation", "elevation_band"],
        "source": {
            "asset": ASSET,
            "demAsset": DEM_ASSET,
            "nominalScaleMetres": SCALE,
            "latestAvailableMonth": latest_text,
        },
        "coverage": {
            "rows": len(merged),
            "systems": len({row["system_id"] for row in merged}),
            "elevationBands": len({row["elevation_band"] for row in merged}),
            "periods": sorted({row["period_start"][:7] for row in merged}),
            "variables": sorted({row["variable"] for row in merged}),
        },
        "outputs": {
            "csv": str(OUTPUT.relative_to(ROOT)).replace("\\", "/"),
            "json": str(JSON_OUTPUT.relative_to(ROOT)).replace("\\", "/"),
        },
        "qualityNotes": [
            "The source monthly temporal resolution is preserved.",
            "ERA5-Land is reanalysis and modelled runoff is not gauge discharge.",
            "SRTM masks add an elevation dimension without changing basin identity.",
        ],
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  {len(fresh):,} refreshed; {len(merged):,} total -> {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
