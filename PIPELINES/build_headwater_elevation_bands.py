"""Measure configured elevation-band areas inside each headwater system.

Elevation bands are raster masks derived from SRTM, not new basin identities.
This preserves the natural basin hierarchy while allowing every observation to
carry both a basin/system dimension and an elevation-band dimension.

    python PIPELINES/build_headwater_elevation_bands.py
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "ONTOLOGY/vocab/hydroclimate-system.json"
SYSTEMS = ROOT / "PUBLISHED/data/hydroclimate/headwater-systems.geojson"
OUTPUT = ROOT / "PUBLISHED/data/hydroclimate/headwater-elevation-bands.csv"
MANIFEST = ROOT / "PUBLISHED/data/hydroclimate/headwater-elevation-bands.manifest.json"
PROJECT = "ee-sabitovty"
ASSET = "USGS/SRTMGL1_003"
SCALE = 90


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "system_id", "river_system_id", "elevation_band", "minimum_m_inclusive",
        "maximum_m_exclusive", "area_km2", "share_percent", "mean_elevation_m",
        "source_asset", "scale_m", "retrieved_at",
    ]
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def main() -> None:
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
    systems = json.loads(SYSTEMS.read_text(encoding="utf-8"))["features"]
    bands = config["elevationBandsMetres"]
    dem = ee.Image(ASSET).select("elevation")
    pixel_area = ee.Image.pixelArea()
    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rows: list[dict] = []

    for feature in systems:
        props = feature["properties"]
        geometry = ee.Geometry(feature["geometry"])
        images = []
        for band in bands:
            mask = ee.Image(1)
            if band["minimum"] is not None:
                mask = mask.And(dem.gte(band["minimum"]))
            if band["maximum"] is not None:
                mask = mask.And(dem.lt(band["maximum"]))
            area_name = f"area__{band['id']}"
            weighted_name = f"weighted__{band['id']}"
            images.extend([
                pixel_area.updateMask(mask).rename(area_name),
                dem.multiply(pixel_area).updateMask(mask).rename(weighted_name),
            ])
        totals = ee.Image.cat(images).reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geometry,
            scale=SCALE,
            maxPixels=1_000_000_000,
            tileScale=4,
        ).getInfo()
        areas = {band["id"]: float(totals.get(f"area__{band['id']}") or 0) / 1e6 for band in bands}
        total_area = sum(areas.values())
        for band in bands:
            area = areas[band["id"]]
            weighted = float(totals.get(f"weighted__{band['id']}") or 0)
            rows.append({
                "system_id": props["system_id"],
                "river_system_id": props["river_system_id"],
                "elevation_band": band["id"],
                "minimum_m_inclusive": "" if band["minimum"] is None else band["minimum"],
                "maximum_m_exclusive": "" if band["maximum"] is None else band["maximum"],
                "area_km2": f"{area:.3f}",
                "share_percent": f"{area / total_area * 100:.4f}" if total_area else "",
                "mean_elevation_m": f"{weighted / (area * 1e6):.1f}" if area else "",
                "source_asset": ASSET,
                "scale_m": SCALE,
                "retrieved_at": retrieved,
            })
        print(f"  {props['system_id']}: {total_area:,.1f} km2 across {len(bands)} bands")

    write_csv(OUTPUT, rows)
    manifest = {
        "version": "1.0",
        "generatedAt": retrieved,
        "spatialScope": "headwater_formation",
        "source": {
            "platform": "Google Earth Engine",
            "asset": ASSET,
            "nativeResolutionMetres": 30,
            "analysisScaleMetres": SCALE,
            "catalogUrl": "https://developers.google.com/earth-engine/datasets/catalog/USGS_SRTMGL1_003",
        },
        "bands": bands,
        "output": str(OUTPUT.relative_to(ROOT)).replace("\\", "/"),
        "rows": len(rows),
        "semantics": {
            "minimum": "inclusive",
            "maximum": "exclusive",
            "identity": "ElevationBand is an analytical intersection dimension, not a replacement basin ID.",
        },
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  {len(rows)} rows -> {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
