"""Publish every held layer as GeoJSON and index them for the review page.

Reviewing the data means looking at it, one layer at a time, on a map. Most of
what the project holds could not be looked at: the two HydroSHEDS deliveries keep
twenty-four basin levels inside GeoPackages, and only level 12 had ever been
projected out. This exports all of them, alongside the layers already published,
and writes one index describing what each is.

A GeoPackage is a SQLite database and its geometry column is a small header
followed by standard WKB, so this reads both with the standard library and
shapely — no GDAL. Coordinates are rounded to five decimals, about a metre, which
is precision this data never had: HydroSHEDS is derived from a 15-arc-second DEM,
roughly 450 m at this latitude. Vertices are kept in full; nothing is simplified,
so what the page draws is the geometry as delivered.

Usage:
    python PIPELINES/build_review_layers.py
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

try:
    from shapely import wkb
    from shapely.geometry import mapping
except ImportError as error:  # pragma: no cover - depends on the workstation
    raise SystemExit("shapely is required: pip install shapely") from error

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "PUBLISHED" / "data" / "review"
INDEX = ROOT / "PUBLISHED" / "data" / "review-layers.json"
PRECISION = 5

# The GeoPackage envelope sizes, indexed by the envelope code in the flag byte.
ENVELOPE = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}

PACKAGES = [
    {
        "slug": "basinatlas",
        "group": "HYDROBASINS",
        "path": "GEODATA/uzbekistan_basinatlas_v10/uzbekistan_basinatlas_v10.gpkg",
        "source": "BasinATLAS v1.0 Uzbekistan extraction (HydroSHEDS)",
        "titles": {"uzbekistan_adm0": "Uzbekistan boundary (as used for the extraction)"},
    },
    {
        "slug": "hydrobasins-lake",
        "group": "HYDROBASINS",
        "path": "GEODATA/uzbekistan_hydrobasins_lake_v1c/uzbekistan_hydrobasins_lake_v1c.gpkg",
        "source": "HydroBASINS v1c lake-format Uzbekistan extraction (HydroSHEDS)",
        "titles": {"uzb_adm0_selection_boundary": "Selection boundary (as used for the extraction)"},
    },
]

# Layers already served, which the review page lists beside the newly exported
# ones so a reviewer sees one list rather than two.
PUBLISHED = [
    ("ADMIN", "Provinces (ADM1)", "/data/admin/adm1.geojson", "OCHA/HDX COD uzb_admbnda 2018b"),
    ("ADMIN", "Districts (ADM2)", "/data/admin/adm2.geojson", "OCHA/HDX COD uzb_admbnda 2018b"),
    ("HYDROBASINS", "Level-12 basins, clipped to Uzbekistan", "/data/hydrography/basins.geojson", "HydroSHEDS, clipped"),
    ("HYDROBASINS", "National boundary", "/data/hydrography/boundary.geojson", "Uzbekistan ADM0"),
    ("HYDRORIVERS", "River reaches", "/data/hydrography/rivers.geojson", "HydroRIVERS v1.0, clipped"),
    ("HYDROLAKES", "Lakes and reservoirs", "/data/hydrography/lakes.geojson", "HydroLAKES v1.0, clipped"),
    ("HAZARDS", "Earthquakes 1990-2024", "/data/earthquakes.geojson", "Atlas derivative"),
    ("HAZARDS", "Flood risk", "/data/flood-risk.geojson", "Atlas derivative"),
    ("HAZARDS", "Glacial lakes", "/data/glacial-lakes.geojson", "Atlas derivative"),
    ("HAZARDS", "Seismicity clusters", "/data/analysis/seismicity-clusters.geojson", "PIPELINES/analysis"),
    ("PROTECTED", "Protected areas", "/data/protected-areas.geojson", "Atlas derivative"),
    ("WATERMGMT", "Water management zones", "/data/water-management.geojson", "Atlas derivative"),
]


def decode(blob: bytes):
    """A GeoPackage geometry blob is 'GP', version, flags, srs_id, envelope, WKB."""
    return wkb.loads(blob[8 + ENVELOPE[(blob[3] >> 1) & 0x07]:])


def round_coordinates(value, precision=PRECISION):
    if isinstance(value, (list, tuple)):
        if value and isinstance(value[0], (int, float)):
            return [round(float(number), precision) for number in value]
        return [round_coordinates(item, precision) for item in value]
    return value


def describe_fields(rows: list[dict], names: list[str]) -> list[dict]:
    """Field names with a type and the first value that is actually there.

    A sample matters more than a declared type when reviewing: a column of nulls
    and a column of codes both read as INTEGER, and only one of them is useful.
    """
    fields = []
    for name in names:
        sample = next((row[name] for row in rows if row[name] not in (None, "")), None)
        filled = sum(1 for row in rows if row[name] not in (None, ""))
        fields.append({
            "name": name,
            "type": type(sample).__name__ if sample is not None else "empty",
            "sample": sample if not isinstance(sample, (bytes, bytearray)) else None,
            "filled": filled,
        })
    return fields


def write_layer(features: list[dict], target: Path) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"type": "FeatureCollection", "features": features},
                   ensure_ascii=False, separators=(",", ":")),
        encoding="utf8",
    )
    return target.stat().st_size


def export_package(package: dict) -> list[dict]:
    path = ROOT / package["path"]
    if not path.exists():
        print(f"  {package['slug']}: not on disk, skipped")
        return []
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    geometry_columns = dict(connection.execute(
        "SELECT table_name, column_name FROM gpkg_geometry_columns"))
    entries = []
    for table, in connection.execute(
            "SELECT table_name FROM gpkg_contents WHERE data_type='features' ORDER BY table_name"):
        geometry_column = geometry_columns.get(table)
        if not geometry_column:
            continue
        names = [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')
                 if row[1] not in {"fid", geometry_column}]
        selection = ", ".join(f'"{name}"' for name in [geometry_column, *names])
        features, records = [], []
        bounds = None
        for row in connection.execute(f"SELECT {selection} FROM \"{table}\""):
            geometry = decode(row[0])
            shape = mapping(geometry)
            shape["coordinates"] = round_coordinates(shape["coordinates"])
            record = dict(zip(names, row[1:]))
            records.append(record)
            features.append({"type": "Feature", "properties": record, "geometry": shape})
            minx, miny, maxx, maxy = geometry.bounds
            bounds = (min(bounds[0], minx), min(bounds[1], miny),
                      max(bounds[2], maxx), max(bounds[3], maxy)) if bounds else (minx, miny, maxx, maxy)

        target = OUT_DIR / package["slug"] / f"{table}.geojson"
        size = write_layer(features, target)
        entries.append({
            "id": f"{package['slug']}/{table}",
            "group": package["group"],
            "title": package["titles"].get(table, table.replace("_", " ")),
            "layer": table,
            "package": package["slug"],
            "url": f"/data/review/{package['slug']}/{table}.geojson",
            "source": package["source"],
            "features": len(features),
            "geometryType": features[0]["geometry"]["type"] if features else None,
            "bbox": [round(value, 5) for value in bounds] if bounds else None,
            "bytes": size,
            "fields": describe_fields(records, names),
            "origin": "exported",
        })
        print(f"  {table:32} {len(features):6} features  {size / 1e6:6.2f} MB")
    return entries


def describe_published(group: str, title: str, url: str, source: str) -> dict | None:
    path = ROOT / "PUBLISHED" / url.lstrip("/")
    if not path.exists():
        print(f"  {url}: absent, skipped")
        return None
    collection = json.loads(path.read_text(encoding="utf8"))
    features = collection.get("features", [])
    names = sorted({key for feature in features[:400] for key in (feature.get("properties") or {})})
    records = [feature.get("properties") or {} for feature in features]
    bounds = None
    for feature in features:
        try:
            shape = __import__("shapely.geometry", fromlist=["shape"]).shape(feature["geometry"])
        except Exception:
            continue
        minx, miny, maxx, maxy = shape.bounds
        bounds = (min(bounds[0], minx), min(bounds[1], miny),
                  max(bounds[2], maxx), max(bounds[3], maxy)) if bounds else (minx, miny, maxx, maxy)
    return {
        "id": url.strip("/").replace("/", "-"),
        "group": group,
        "title": title,
        "layer": Path(url).stem,
        "package": "published",
        "url": url,
        "source": source,
        "features": len(features),
        "geometryType": features[0]["geometry"]["type"] if features else None,
        "bbox": [round(value, 5) for value in bounds] if bounds else None,
        "bytes": path.stat().st_size,
        "fields": describe_fields(records, names),
        "origin": "published",
    }


def main() -> None:
    layers = []
    for package in PACKAGES:
        print(f"{package['path']}:")
        layers.extend(export_package(package))
    print("already published:")
    for group, title, url, source in PUBLISHED:
        entry = describe_published(group, title, url, source)
        if entry:
            layers.append(entry)
            print(f"  {entry['layer']:32} {entry['features']:6} features  {entry['bytes'] / 1e6:6.2f} MB")

    INDEX.write_text(json.dumps({
        "version": "1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "crs": "EPSG:4326",
        "precision": f"coordinates rounded to {PRECISION} decimals (about a metre); no vertices removed",
        "layers": sorted(layers, key=lambda entry: (entry["group"], entry["title"])),
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf8")

    total = sum(entry["bytes"] for entry in layers)
    print(f"\n{len(layers)} reviewable layers, {total / 1e6:,.0f} MB total -> {INDEX.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
