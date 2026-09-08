"""Publish one routed HydroRIVERS graph for the full Amu and Syr systems.

The legacy browser graph is a national intersection.  Its reach geometries are
clipped to Uzbekistan, although the native ``NEXT_DOWN`` identifiers still
describe a larger network.  This build uses the locally archived official Asia
HydroRIVERS v1.0 FileGDB and selects every reach whose native ``HYBAS_L12`` is
one of the level-12 units in the transboundary Amu/Syr frame.  Geometry and
topology therefore use the same spatial scope.

Outputs are deliberately available in three forms:

* GeoJSON for map and trace downloads;
* CSV for analysis outside the portal;
* compact JSON for search and graph traversal in the browser.

    python PIPELINES/build_unified_river_network.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pyogrio

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "GEODATA/HydroRIVERS_v10_as.gdb/HydroRIVERS_v10_as.gdb"
BASINS = ROOT / "GEODATA/transboundary_basins_v2/hydroatlas-level12-full-basins.geojson"
ROLES = ROOT / "PUBLISHED/data/hydroclimate/basin-hydrological-roles.csv"
NATIONAL = ROOT / "PUBLISHED/data/hydrography/relationships.json"
LAKES = ROOT / "PUBLISHED/data/hydroclimate/water-bodies-transboundary.csv"
OUTPUT_DIR = ROOT / "PUBLISHED/data/hydrography"
GEOJSON_OUTPUT = OUTPUT_DIR / "rivers-unified.geojson"
CSV_OUTPUT = OUTPUT_DIR / "rivers-unified.csv"
JSON_OUTPUT = OUTPUT_DIR / "relationships-unified.json"
MANIFEST_OUTPUT = OUTPUT_DIR / "relationships-unified.manifest.json"

SOURCE_COLUMNS = [
    "HYRIV_ID", "NEXT_DOWN", "MAIN_RIV", "LENGTH_KM", "DIST_DN_KM",
    "DIST_UP_KM", "CATCH_SKM", "UPLAND_SKM", "ENDORHEIC", "DIS_AV_CMS",
    "ORD_STRA", "ORD_CLAS", "ORD_FLOW", "HYBAS_L12",
]
CSV_COLUMNS = [
    *SOURCE_COLUMNS, "system_id", "flow_position", "channel_class",
    "in_headwater_formation", "in_national_extraction", "source_asset",
]


def atomic_json(path: Path, payload: object, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(
            payload,
            handle,
            ensure_ascii=False,
            separators=(",", ":") if compact else None,
            indent=None if compact else 2,
        )
        handle.write("\n")
    os.replace(temporary, path)


def atomic_csv(path: Path, rows: list[dict]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def coordinate_bounds(document: dict) -> tuple[float, float, float, float]:
    bounds = [180.0, 90.0, -180.0, -90.0]

    def visit(node) -> None:
        if isinstance(node[0], (int, float)):
            bounds[0] = min(bounds[0], float(node[0]))
            bounds[1] = min(bounds[1], float(node[1]))
            bounds[2] = max(bounds[2], float(node[0]))
            bounds[3] = max(bounds[3], float(node[1]))
            return
        for child in node:
            visit(child)

    for feature in document["features"]:
        visit(feature["geometry"]["coordinates"])
    return tuple(bounds)


def basin_roles() -> dict[int, dict]:
    with ROLES.open(encoding="utf-8", newline="") as handle:
        return {
            int(row["hybas_id"]): row
            for row in csv.DictReader(handle)
            if int(row["basin_level"]) == 12
        }


def rounded(value, digits: int = 3):
    return None if value is None else round(float(value), digits)


def integer(value):
    return None if value is None else int(value)


def main() -> None:
    for path in (SOURCE, BASINS, ROLES, NATIONAL, LAKES):
        if not path.exists():
            raise SystemExit(f"Missing {path.relative_to(ROOT)}")

    basin_document = json.loads(BASINS.read_text(encoding="utf-8"))
    basin_properties = {
        int(feature["properties"]["HYBAS_ID"]): feature["properties"]
        for feature in basin_document["features"]
    }
    basin_ids = set(basin_properties)
    roles = basin_roles()
    bounds = coordinate_bounds(basin_document)
    national_document = json.loads(NATIONAL.read_text(encoding="utf-8"))
    national_ids = {int(row["id"]) for row in national_document["rivers"]}
    national_basins = {int(row["id"]): row for row in national_document["basins"]}

    print(f"Unified HydroRIVERS | bbox {[round(value, 3) for value in bounds]}")
    frame = pyogrio.read_dataframe(str(SOURCE), bbox=bounds, columns=SOURCE_COLUMNS)
    frame = frame[frame["HYBAS_L12"].astype("int64").isin(basin_ids)].copy()
    if frame.empty:
        raise RuntimeError("No HydroRIVERS reaches matched the transboundary basin frame")
    for column in ("HYRIV_ID", "NEXT_DOWN", "MAIN_RIV", "ENDORHEIC", "ORD_STRA",
                   "ORD_CLAS", "ORD_FLOW", "HYBAS_L12"):
        frame[column] = frame[column].fillna(0).astype("int64")
    frame.sort_values("HYRIV_ID", inplace=True)
    if frame["HYRIV_ID"].duplicated().any():
        raise RuntimeError("The selected HydroRIVERS frame contains duplicate HYRIV_ID values")

    selected_ids = set(frame["HYRIV_ID"])
    dangling = sorted({
        int(value) for value in frame["NEXT_DOWN"]
        if int(value) and int(value) not in selected_ids
    })
    if dangling:
        raise RuntimeError(f"The full-system selection has dangling NEXT_DOWN links: {dangling[:10]}")

    frame["system_id"] = frame["HYBAS_L12"].map(
        lambda value: basin_properties[int(value)]["system_id"]
    )
    frame["flow_position"] = frame["HYBAS_L12"].map(
        lambda value: roles.get(int(value), {}).get("flow_position", "")
    )
    frame["channel_class"] = frame["HYBAS_L12"].map(
        lambda value: roles.get(int(value), {}).get("channel_class", "")
    )
    frame["in_headwater_formation"] = frame["HYBAS_L12"].map(
        lambda value: int(bool(basin_properties[int(value)]["in_headwater_formation"]))
    )
    frame["in_national_extraction"] = frame["HYRIV_ID"].map(
        lambda value: int(int(value) in national_ids)
    )
    frame["source_asset"] = "HydroRIVERS v1.0 (Asia)"

    records = []
    for row in frame[CSV_COLUMNS].itertuples(index=False, name=None):
        values = dict(zip(CSV_COLUMNS, row))
        records.append({
            key: integer(value) if key in {
                "HYRIV_ID", "NEXT_DOWN", "MAIN_RIV", "ENDORHEIC", "ORD_STRA",
                "ORD_CLAS", "ORD_FLOW", "HYBAS_L12", "in_headwater_formation",
                "in_national_extraction",
            } else rounded(value) if key in {
                "LENGTH_KM", "DIST_DN_KM", "DIST_UP_KM", "CATCH_SKM",
                "UPLAND_SKM", "DIS_AV_CMS",
            } else value
            for key, value in values.items()
        })

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    atomic_csv(CSV_OUTPUT, records)
    web_frame = frame[CSV_COLUMNS + [frame.geometry.name]].copy()
    web_frame.geometry = web_frame.geometry.simplify(0.0015, preserve_topology=False)
    temporary_geojson = GEOJSON_OUTPUT.with_suffix(".geojson.tmp")
    if temporary_geojson.exists():
        temporary_geojson.unlink()
    pyogrio.write_dataframe(
        web_frame,
        temporary_geojson,
        driver="GeoJSON",
        layer_options={"RFC7946": "YES", "COORDINATE_PRECISION": "5"},
    )
    os.replace(temporary_geojson, GEOJSON_OUTPUT)

    rivers = [{
        "id": row["HYRIV_ID"],
        "nextDown": row["NEXT_DOWN"],
        "mainRiver": row["MAIN_RIV"],
        "basinId": row["HYBAS_L12"],
        "lengthKm": row["LENGTH_KM"],
        "distanceDownKm": row["DIST_DN_KM"],
        "catchmentKm2": row["CATCH_SKM"],
        "upstreamKm2": row["UPLAND_SKM"],
        "dischargeCms": row["DIS_AV_CMS"],
        "strahlerOrder": row["ORD_STRA"],
        "flowOrder": row["ORD_FLOW"],
        "endorheic": bool(row["ENDORHEIC"]),
        "systemId": row["system_id"],
        "flowPosition": row["flow_position"],
        "channelClass": row["channel_class"],
        "inHeadwaterFormation": bool(row["in_headwater_formation"]),
        "inNationalExtraction": bool(row["in_national_extraction"]),
    } for row in records]
    basins = [{
        "id": basin_id,
        "pfafId": int(props["PFAF_ID"]),
        "nextDown": int(props.get("NEXT_DOWN") or 0),
        "mainBasin": int(props["MAIN_BAS"]),
        "areaKm2": round(float(props["SUB_AREA"]), 2),
        "upstreamKm2": round(float(props["UP_AREA"]), 2),
        "uzbekistanKm2": national_basins.get(basin_id, {}).get("uzbekistanKm2", 0),
        "uzbekistanPercent": national_basins.get(basin_id, {}).get("uzbekistanPercent", 0),
        "endorheic": int(props.get("ENDO") or 0) > 0,
        "order": int(props.get("ORDER_") or 0),
        "systemId": props["system_id"],
        "headwaterSystemId": props.get("headwater_system_id") or "",
        "inHeadwaterFormation": bool(props["in_headwater_formation"]),
        "flowPosition": roles.get(basin_id, {}).get("flow_position", ""),
        "channelClass": roles.get(basin_id, {}).get("channel_class", ""),
    } for basin_id, props in sorted(basin_properties.items())]

    lakes = []
    with LAKES.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            lakes.append({
                "id": int(row["water_body_id"]),
                "name": row["name"] or None,
                "basinId": int(row["hybas_id_level12"]),
                "country": row["country"] or None,
                "lakeType": row["water_body_type"],
                "areaKm2": rounded(row["area_km2"]),
                "volumeMcm": rounded(row["total_volume_mcm"]),
                "dischargeCms": rounded(row["average_discharge_cms"]),
                "elevationM": integer(float(row["elevation_m"])) if row["elevation_m"] else None,
                "systemId": row["system_id"],
                "flowPosition": row["flow_position"],
                "inHeadwaterFormation": row["in_headwater_formation"] == "1",
            })

    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    by_system = {}
    for system_id in sorted(set(frame["system_id"])):
        selection = frame[frame["system_id"] == system_id]
        by_system[system_id] = {
            "reaches": len(selection),
            "nationalIntersectionReaches": int(selection["in_national_extraction"].sum()),
            "formationReaches": int(selection["in_headwater_formation"].sum()),
        }
    graph = {
        "version": "2.0",
        "generatedAt": generated,
        "title": "Unified Amu Darya and Syr Darya hydrography relationship graph",
        "spatialScope": "full_basin",
        "nestedScope": "headwater_formation",
        "sources": {
            "rivers": "HydroRIVERS v1.0 Asia FileGDB",
            "basins": "HydroATLAS v1 level 12 via the transboundary basin build",
            "lakes": "HydroLAKES v1.0 via the transboundary water-body build",
        },
        "selection": {
            "rule": "HYBAS_L12 belongs to the full Amu Darya or Syr Darya frame",
            "administrativeClipping": False,
            "topology": "native HYRIV_ID and NEXT_DOWN retained",
        },
        "counts": {
            "rivers": len(rivers), "lakes": len(lakes), "basins": len(basins),
            "nationalIntersectionRivers": sum(row["inNationalExtraction"] for row in rivers),
            "riversPreviouslyUnavailable": sum(not row["inNationalExtraction"] for row in rivers),
            "downstreamLinks": len(rivers), "riverBasinLinks": len(rivers),
            "lakeBasinLinks": len(lakes),
        },
        "countsBySystem": by_system,
        "layers": {
            "rivers": "/data/hydrography/rivers-unified.geojson",
            "basins": "/data/hydroclimate/basins-level12.geojson",
            "lakes": "/data/hydroclimate/water-bodies-transboundary.geojson",
            "boundary": "/data/hydrography/boundary.geojson",
            "riverTable": "/data/hydrography/rivers-unified.csv",
        },
        "rivers": rivers,
        "lakes": lakes,
        "basins": basins,
        "integrity": {
            "uniqueRiverIds": len(selected_ids) == len(rivers),
            "danglingRiverTargets": 0,
            "unresolvedRiverBasins": sum(row["basinId"] not in basin_ids for row in rivers),
        },
        "qualityNotes": [
            "DIS_AV_CMS is modelled long-term natural discharge, not a gauge observation.",
            "inNationalExtraction marks identity overlap with the previous national graph; geometry in this file is never clipped to a national border.",
            "The full basin includes formation, transit and terminal reaches, so upstream and downstream are queried through one topology.",
        ],
        "warnings": [],
    }
    atomic_json(JSON_OUTPUT, graph, compact=True)
    atomic_json(MANIFEST_OUTPUT, {
        key: graph[key] for key in (
            "version", "generatedAt", "spatialScope", "nestedScope", "sources",
            "selection", "counts", "countsBySystem", "layers", "integrity", "qualityNotes",
        )
    } | {
        "files": {
            "relationships": {"path": str(JSON_OUTPUT.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(JSON_OUTPUT)},
            "geometry": {"path": str(GEOJSON_OUTPUT.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(GEOJSON_OUTPUT)},
            "table": {"path": str(CSV_OUTPUT.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(CSV_OUTPUT)},
        }
    })
    print(
        f"  {len(rivers):,} reaches; {graph['counts']['riversPreviouslyUnavailable']:,} newly accessible; "
        f"{len(basins):,} level-12 basins"
    )
    print(f"  -> {JSON_OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
