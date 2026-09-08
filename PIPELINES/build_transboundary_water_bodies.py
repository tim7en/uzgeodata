"""Publish lakes and reservoirs of the whole Amu and Syr systems, not only Uzbekistan.

The national hydrography layer holds 647 water bodies and just 10 reservoirs,
because it was cut by the country boundary. Every reservoir that decides how much
water reaches Uzbekistan — Toktogul, Nurek, Kayrakkum, Andijan, Charvak — sits
outside that cut or is missing from it. This build takes HydroLAKES over the two
natural systems instead, and records for each body the subbasin it sits in and
whether that subbasin is a runoff-formation unit or a transit unit.

A reservoir is stored as a water body here, with its pour point. It becomes a
node of the managed graph only in step 3; this layer states where it is, not how
it is operated.

    python PIPELINES/build_transboundary_water_bodies.py
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone
import sys
from pathlib import Path

import pyogrio
from shapely.geometry import Point, mapping, shape
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hydrosheds_sources  # noqa: E402  (path set above)

ROOT = Path(__file__).resolve().parent.parent
PUBLISHED_DIR = ROOT / "PUBLISHED/data/hydroclimate"
BASIN_SOURCE = ROOT / "GEODATA/transboundary_basins_v2"
LAKES = hydrosheds_sources.require(
    "HydroLAKES_polys_v10.gdb/HydroLAKES_polys_v10.gdb",
    hint="HydroLAKES v1.0 is the source of every lake and reservoir in this build.",
)
ROLES = PUBLISHED_DIR / "basin-hydrological-roles.csv"
GEOJSON = PUBLISHED_DIR / "water-bodies-transboundary.geojson"
TABLE = PUBLISHED_DIR / "water-bodies-transboundary.csv"
LINKS = PUBLISHED_DIR / "water-body-basin-links.csv"
MANIFEST = PUBLISHED_DIR / "water-bodies-transboundary.manifest.json"
LAKE_COLUMNS = [
    "Hylak_id", "Lake_name", "Country", "Lake_type", "Grand_id", "Lake_area",
    "Vol_total", "Vol_res", "Depth_avg", "Dis_avg", "Res_time", "Elevation",
    "Wshd_area", "Pour_long", "Pour_lat",
]
LAKE_TYPES = {1: "lake", 2: "reservoir", 3: "lake_control"}
TABLE_FIELDS = [
    "water_body_id", "name", "water_body_type", "system_id", "country",
    "area_km2", "total_volume_mcm", "storage_volume_mcm", "mean_depth_m",
    "average_discharge_cms", "residence_time_days", "elevation_m",
    "watershed_area_km2", "pour_longitude", "pour_latitude",
    "hybas_id_level10", "hybas_id_level12", "flow_position", "channel_class",
    "in_headwater_formation", "grand_id", "source_asset", "retrieved_at",
]
LINK_FIELDS = [
    "water_body_id", "water_body_type", "system_id", "basin_level", "hybas_id",
    "in_headwater_formation", "method", "retrieved_at",
]


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def write_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
    os.replace(temporary, path)


def number(value, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return default if result != result else result


def text(value) -> str:
    cleaned = str(value).strip() if value is not None else ""
    return "" if cleaned in {"", "None", "nan", "NULL"} else cleaned


def basin_index(level: int):
    path = BASIN_SOURCE / f"hydroatlas-level{level:02d}-full-basins.geojson"
    if not path.exists():
        raise SystemExit(f"Missing {path.relative_to(ROOT)}; run npm run basins:transboundary first")
    features = json.loads(path.read_text(encoding="utf-8"))["features"]
    geometries = []
    records = []
    for feature in features:
        geometry = shape(feature["geometry"])
        geometries.append(geometry if geometry.is_valid else geometry.buffer(0))
        props = feature["properties"]
        records.append({
            "hybas_id": int(props["HYBAS_ID"]),
            "system_id": props["system_id"],
            "in_headwater_formation": bool(props["in_headwater_formation"]),
        })
    return STRtree(geometries), geometries, records


def read_roles() -> dict[tuple[int, int], dict]:
    if not ROLES.exists():
        return {}
    with ROLES.open(encoding="utf-8", newline="") as handle:
        return {
            (int(row["basin_level"]), int(row["hybas_id"])): row
            for row in csv.DictReader(handle)
        }


def locate(tree, geometries, records, point: Point) -> dict | None:
    for index in tree.query(point, predicate="intersects"):
        if geometries[int(index)].contains(point):
            return records[int(index)]
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simplify", type=float, default=0.0005, help="web simplification, degrees")
    args = parser.parse_args()
    if not LAKES.parent.exists():
        raise SystemExit(f"Missing {LAKES.parent.relative_to(ROOT)}")

    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    indexes = {level: basin_index(level) for level in (10, 12)}
    roles = read_roles()

    minimum = [1e9, 1e9]
    maximum = [-1e9, -1e9]
    for geometry in indexes[10][1]:
        x0, y0, x1, y1 = geometry.bounds
        minimum[0] = min(minimum[0], x0); minimum[1] = min(minimum[1], y0)
        maximum[0] = max(maximum[0], x1); maximum[1] = max(maximum[1], y1)
    bounds = (minimum[0], minimum[1], maximum[0], maximum[1])
    print(f"Water bodies | HydroLAKES bbox {[round(v, 2) for v in bounds]}")

    frame = pyogrio.read_dataframe(str(LAKES), bbox=bounds, columns=LAKE_COLUMNS)
    print(f"  {len(frame):,} water bodies in the bounding box")

    features = []
    table_rows = []
    link_rows = []
    for record in frame.itertuples(index=False):
        point = Point(number(record.Pour_long), number(record.Pour_lat))
        placed = {level: locate(*indexes[level], point) for level in (10, 12)}
        if placed[10] is None:
            continue
        system_id = placed[10]["system_id"]
        water_type = LAKE_TYPES.get(int(number(record.Lake_type, 0)), "unknown")
        role = roles.get((10, placed[10]["hybas_id"]), {})
        body_id = int(number(record.Hylak_id))
        geometry = record.geometry
        if geometry is None:
            continue
        table_rows.append({
            "water_body_id": body_id,
            "name": text(record.Lake_name),
            "water_body_type": water_type,
            "system_id": system_id,
            "country": text(record.Country),
            "area_km2": f"{number(record.Lake_area):.4f}",
            "total_volume_mcm": f"{number(record.Vol_total):.2f}",
            "storage_volume_mcm": f"{number(record.Vol_res):.2f}",
            "mean_depth_m": f"{number(record.Depth_avg):.2f}",
            "average_discharge_cms": f"{number(record.Dis_avg):.4f}",
            "residence_time_days": f"{number(record.Res_time):.2f}",
            "elevation_m": f"{number(record.Elevation):.0f}",
            "watershed_area_km2": f"{number(record.Wshd_area):.2f}",
            "pour_longitude": f"{point.x:.5f}",
            "pour_latitude": f"{point.y:.5f}",
            "hybas_id_level10": placed[10]["hybas_id"],
            "hybas_id_level12": placed[12]["hybas_id"] if placed[12] else "",
            "flow_position": role.get("flow_position", ""),
            "channel_class": role.get("channel_class", ""),
            "in_headwater_formation": int(placed[10]["in_headwater_formation"]),
            "grand_id": int(number(record.Grand_id)) or "",
            "source_asset": "HydroLAKES v1.0",
            "retrieved_at": retrieved,
        })
        for level in (10, 12):
            if placed[level] is None:
                continue
            link_rows.append({
                "water_body_id": body_id,
                "water_body_type": water_type,
                "system_id": system_id,
                "basin_level": level,
                "hybas_id": placed[level]["hybas_id"],
                "in_headwater_formation": int(placed[level]["in_headwater_formation"]),
                "method": "pour_point_containment",
                "retrieved_at": retrieved,
            })
        shaped = shape(mapping(geometry))
        features.append({
            "type": "Feature",
            "properties": {
                "water_body_id": body_id,
                "name": text(record.Lake_name),
                "water_body_type": water_type,
                "system_id": system_id,
                "area_km2": round(number(record.Lake_area), 3),
                "total_volume_mcm": round(number(record.Vol_total), 1),
                "hybas_id_level10": placed[10]["hybas_id"],
                "in_headwater_formation": int(placed[10]["in_headwater_formation"]),
                "flow_position": role.get("flow_position", ""),
            },
            "geometry": mapping(shaped.simplify(args.simplify, preserve_topology=True)),
        })

    table_rows.sort(key=lambda row: (row["system_id"], -float(row["total_volume_mcm"]), row["water_body_id"]))
    link_rows.sort(key=lambda row: (row["basin_level"], row["system_id"], row["water_body_id"]))
    features.sort(key=lambda item: item["properties"]["water_body_id"])

    write_csv(TABLE, TABLE_FIELDS, table_rows)
    write_csv(LINKS, LINK_FIELDS, link_rows)
    write_json(GEOJSON, {"type": "FeatureCollection", "name": "amu_syr_water_bodies", "features": features})

    reservoirs = [row for row in table_rows if row["water_body_type"] == "reservoir"]
    upstream = [row for row in reservoirs if row["in_headwater_formation"] == 1]
    storage = sum(float(row["total_volume_mcm"]) for row in reservoirs)
    manifest = {
        "version": "1.0",
        "generatedAt": retrieved,
        "observationClass": "inventory",
        "spatialScope": "full_basin",
        "source": {
            "asset": "HydroLAKES v1.0",
            "container": str(LAKES.relative_to(ROOT)).replace("\\", "/"),
            "selection": "pour point inside a level-10 unit of the Amu or Syr natural system",
        },
        "counts": {
            "waterBodies": len(table_rows),
            "reservoirs": len(reservoirs),
            "reservoirsInFormationZones": len(upstream),
            "lakes": sum(1 for row in table_rows if row["water_body_type"] == "lake"),
            "basinLinks": len(link_rows),
        },
        "reservoirStorageMcm": round(storage, 1),
        "largestReservoirs": [
            {
                "id": row["water_body_id"], "name": row["name"] or None,
                "volumeMcm": float(row["total_volume_mcm"]),
                "system": row["system_id"],
                "pour": [float(row["pour_longitude"]), float(row["pour_latitude"])],
                "inFormationZone": bool(int(row["in_headwater_formation"])),
            }
            for row in sorted(reservoirs, key=lambda r: -float(r["total_volume_mcm"]))[:12]
        ],
        "outputs": {
            "csv": str(TABLE.relative_to(ROOT)).replace("\\", "/"),
            "linkCSV": str(LINKS.relative_to(ROOT)).replace("\\", "/"),
            "geojson": str(GEOJSON.relative_to(ROOT)).replace("\\", "/"),
        },
        "qualityNotes": [
            "HydroLAKES stores a static shoreline and a nominal volume, not an operating level; "
            "it says a reservoir exists, never how full it is.",
            "A water body is placed by its pour point, so a lake straddling a divide belongs to "
            "the subbasin its outlet drains into.",
            "Reservoirs appear here as natural-frame objects. Releases, intakes and transfers "
            "belong to the managed graph of step 3 and are not implied by this layer.",
        ],
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  {len(table_rows):,} water bodies, {len(reservoirs)} reservoirs "
          f"({len(upstream)} inside formation zones), {storage:,.0f} MCM nominal storage")
    print(f"  -> {TABLE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
