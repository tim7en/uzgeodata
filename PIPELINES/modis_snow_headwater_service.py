"""Preserve daily MODIS snow cover by headwater system and elevation band.

The source is daily, so the stored relationship table stays daily. Monthly or
seasonal products must be derived from this table rather than replacing it.
Cloud/invalid retrievals are represented by valid_area_percent, not silently
treated as snow-free ground.

    python PIPELINES/modis_snow_headwater_service.py
    python PIPELINES/modis_snow_headwater_service.py --start 2026-08-01 --end 2026-08-31
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "ONTOLOGY/vocab/hydroclimate-system.json"
SYSTEMS = ROOT / "PUBLISHED/data/hydroclimate/headwater-systems.geojson"
OUTPUT = ROOT / "PUBLISHED/data/hydroclimate/modis-snow-headwaters-daily.csv"
JSON_OUTPUT = ROOT / "PUBLISHED/data/hydroclimate/modis-snow-headwaters-daily.json"
MANIFEST = ROOT / "PUBLISHED/data/hydroclimate/modis-snow-headwaters-daily.manifest.json"
PROJECT = "ee-sabitovty"
ASSET = "MODIS/061/MOD10A1"
DEM_ASSET = "USGS/SRTMGL1_003"
SCALE = 500
FIELDS = [
    "observation_unit_id", "system_id", "river_system_id", "elevation_band",
    "minimum_m_inclusive", "maximum_m_exclusive", "date", "year", "month", "day",
    "variable", "value", "unit", "valid_area_percent", "source_asset", "source_image",
    "scale_m", "quality", "retrieved_at",
]


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must be YYYY-MM-DD") from error


def read_rows() -> list[dict]:
    if not OUTPUT.exists():
        return []
    with OUTPUT.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def merge_rows(previous: list[dict], fresh: list[dict]) -> list[dict]:
    def key(row):
        return row["observation_unit_id"], row["date"], row["variable"]

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


def quality(valid_percent: float) -> str:
    if valid_percent >= 70:
        return "ok-satellite"
    if valid_percent >= 30:
        return "limited-clear-sky"
    return "insufficient-clear-sky"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=parse_date)
    parser.add_argument("--end", type=parse_date)
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
    bands = config["elevationBandsMetres"]
    source = ee.ImageCollection(ASSET)
    latest_text = source.sort("system:time_start", False).first().date().format("YYYY-MM-dd").getInfo()
    latest = parse_date(latest_text)
    end = args.end or latest
    if end > latest:
        raise SystemExit(f"Requested end {end} exceeds latest available {latest}")

    previous = read_rows()
    if args.start:
        start = args.start
    elif previous:
        start = max(parse_date(row["date"]) for row in previous) + timedelta(days=1)
    else:
        start = end - timedelta(days=30)
    if start > end:
        print(f"MODIS snow already current through {end}")
        return

    collection = source.filterDate(start.isoformat(), (end + timedelta(days=1)).isoformat()).sort("system:time_start")
    count = int(collection.size().getInfo())
    if not count:
        raise SystemExit(f"No MODIS snow images from {start} through {end}")
    image_list = collection.toList(count)
    indexes = collection.aggregate_array("system:index").getInfo()
    dates = collection.aggregate_array("system:time_start").map(
        lambda millis: ee.Date(millis).format("YYYY-MM-dd")
    ).getInfo()
    dem = ee.Image(DEM_ASSET).select("elevation")
    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    fresh: list[dict] = []
    print(f"MODIS daily snow | {start}..{end} | {count} images | {len(bands)} elevation bands")

    for position in range(count):
        image = ee.Image(image_list.get(position))
        snow = image.select("NDSI_Snow_Cover")
        output_bands = []
        for band in bands:
            elevation_mask = ee.Image(1)
            if band["minimum"] is not None:
                elevation_mask = elevation_mask.And(dem.gte(band["minimum"]))
            if band["maximum"] is not None:
                elevation_mask = elevation_mask.And(dem.lt(band["maximum"]))
            output_bands.extend([
                snow.updateMask(elevation_mask).rename(f"snow__{band['id']}"),
                snow.mask().unmask(0).updateMask(elevation_mask).rename(f"valid__{band['id']}"),
            ])
        reduced = ee.Image.cat(output_bands).reduceRegions(
            collection=system_fc,
            reducer=ee.Reducer.mean(),
            scale=SCALE,
            maxPixelsPerRegion=50_000_000,
            tileScale=4,
        ).select(
            ["system_id", "river_system_id", *[name for band in bands for name in (f"snow__{band['id']}", f"valid__{band['id']}")]],
            retainGeometry=False,
        ).getInfo()
        observed_date = parse_date(dates[position])
        for feature in reduced["features"]:
            props = feature["properties"]
            for band in bands:
                valid_percent = float(props.get(f"valid__{band['id']}") or 0) * 100
                value = props.get(f"snow__{band['id']}")
                if value is None:
                    continue
                system_id = props["system_id"]
                fresh.append({
                    "observation_unit_id": f"{system_id}::{band['id']}",
                    "system_id": system_id,
                    "river_system_id": props["river_system_id"],
                    "elevation_band": band["id"],
                    "minimum_m_inclusive": "" if band["minimum"] is None else band["minimum"],
                    "maximum_m_exclusive": "" if band["maximum"] is None else band["maximum"],
                    "date": observed_date.isoformat(),
                    "year": observed_date.year,
                    "month": observed_date.month,
                    "day": observed_date.day,
                    "variable": "snow_cover_percent",
                    "value": f"{float(value):.4f}",
                    "unit": "percent",
                    "valid_area_percent": f"{valid_percent:.2f}",
                    "source_asset": ASSET,
                    "source_image": indexes[position],
                    "scale_m": SCALE,
                    "quality": quality(valid_percent),
                    "retrieved_at": retrieved,
                })
        print(f"  {observed_date} ({position + 1}/{count})", flush=True)

    merged = merge_rows(previous, fresh)
    write_csv(merged)
    JSON_OUTPUT.write_text(
        json.dumps({"version": "1.0", "temporalResolution": "day", "observations": merged}, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    payload = {
        "version": "1.0",
        "generatedAt": retrieved,
        "temporalResolution": "day",
        "spatialDimensions": ["headwater_formation", "elevation_band"],
        "source": {
            "platform": "Google Earth Engine",
            "asset": ASSET,
            "demAsset": DEM_ASSET,
            "nominalScaleMetres": SCALE,
            "latestAvailableDate": latest.isoformat(),
            "catalogUrl": "https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD10A1",
        },
        "coverage": {
            "rows": len(merged),
            "systems": len({row["system_id"] for row in merged}),
            "elevationBands": len({row["elevation_band"] for row in merged}),
            "dates": sorted({row["date"] for row in merged}),
        },
        "outputs": {
            "csv": str(OUTPUT.relative_to(ROOT)).replace("\\", "/"),
            "json": str(JSON_OUTPUT.relative_to(ROOT)).replace("\\", "/"),
        },
        "qualityNotes": [
            "The source daily temporal resolution is preserved.",
            "Provider codes above 100 are masked in the NDSI_Snow_Cover band.",
            "Snow cover is averaged over valid retrieval area only; valid_area_percent exposes cloud and missing-data coverage.",
            "Elevation bands are SRTM raster masks and do not replace HydroATLAS basin identities.",
        ],
    }
    MANIFEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  {len(fresh):,} refreshed; {len(merged):,} total rows -> {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
