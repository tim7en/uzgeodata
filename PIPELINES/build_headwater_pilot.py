"""Build transboundary headwater basins by tracing HydroATLAS upstream.

The former national selection starts with polygons intersecting Uzbekistan. This
pipeline starts with a hydrological control section instead: every level-7 unit
whose NEXT_DOWN chain reaches the configured outlet is retained, irrespective of
country. Source geometry is downloaded from the public Earth Engine HydroATLAS
asset and is also published in a compact web layer.

    python PIPELINES/build_headwater_pilot.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "ONTOLOGY/vocab/hydroclimate-system.json"
SOURCE_DIR = ROOT / "GEODATA/transboundary_headwaters_v1"
PUBLISHED_DIR = ROOT / "PUBLISHED/data/hydroclimate"

PROJECT = "ee-sabitovty"
ASSET = "WWF/HydroATLAS/v1/Basins/level07"
LEVEL = 7
FIELDS = [
    "HYBAS_ID", "NEXT_DOWN", "NEXT_SINK", "MAIN_BAS", "DIST_SINK", "DIST_MAIN",
    "SUB_AREA", "UP_AREA", "PFAF_ID", "ENDO", "COAST", "ORDER_", "SORT",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: object, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(
            payload,
            handle,
            ensure_ascii=False,
            indent=None if compact else 2,
            separators=(",", ":") if compact else None,
        )
        handle.write("\n")
    os.replace(temporary, path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def trace_upstream(rows: Iterable[dict], outlet_id: int) -> list[int]:
    """Return every unit whose downstream chain reaches *outlet_id*.

    Keeping this as a pure function makes the selection rule testable without
    Earth Engine. A repeated ID is a topology defect and fails the build rather
    than being silently treated as an outlet.
    """
    downstream = {int(row["HYBAS_ID"]): int(row.get("NEXT_DOWN") or 0) for row in rows}
    if outlet_id not in downstream:
        raise ValueError(f"Outlet HYBAS_ID {outlet_id} is absent from its MAIN_BAS network")

    selected: list[int] = []
    for start in downstream:
        current = start
        seen: set[int] = set()
        while current:
            if current == outlet_id:
                selected.append(start)
                break
            if current in seen:
                raise ValueError(f"Cycle in NEXT_DOWN routing from {start}: {current}")
            seen.add(current)
            current = downstream.get(current, 0)
    return sorted(selected)


def _properties(feature: dict) -> dict:
    return feature.get("properties", feature)


def _download_geojson(collection, selectors: list[str]) -> dict:
    url = collection.getDownloadURL(filetype="GeoJSON", selectors=[".geo", *selectors])
    response = requests.get(url, timeout=300)
    response.raise_for_status()
    document = response.json()
    if document.get("type") != "FeatureCollection":
        raise RuntimeError("Earth Engine did not return a GeoJSON FeatureCollection")
    return document


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
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
    pilots = config["pilotSystems"]
    source = ee.FeatureCollection(ASSET)
    generated = utc_now()

    source_features: list[dict] = []
    web_features: list[dict] = []
    systems: list[dict] = []
    routing_rows: list[dict] = []
    membership_rows: list[dict] = []
    summaries: list[dict] = []
    all_ids: set[int] = set()

    for pilot in pilots:
        system_id = pilot["id"]
        outlet_id = int(pilot["outletHybasId"])
        point = pilot["controlPoint"]

        # Guard against a stale or mistyped control coordinate. The configured
        # outlet ID is authoritative for routing, while the point explains it.
        point_hit = source.filterBounds(
            ee.Geometry.Point([point["longitude"], point["latitude"]])
        ).first()
        point_id = int(point_hit.get("HYBAS_ID").getInfo())
        if point_id != outlet_id:
            raise RuntimeError(
                f"{system_id}: control point falls in {point_id}, expected {outlet_id}"
            )

        outlet = source.filter(ee.Filter.eq("HYBAS_ID", outlet_id)).first()
        outlet_properties = outlet.toDictionary(FIELDS).getInfo()
        main_basin_id = int(outlet_properties["MAIN_BAS"])
        network_info = (
            source.filter(ee.Filter.eq("MAIN_BAS", main_basin_id))
            .select(FIELDS, retainGeometry=False)
            .getInfo()
        )
        network_rows = [_properties(feature) for feature in network_info["features"]]
        selected_ids = trace_upstream(network_rows, outlet_id)
        duplicate = all_ids.intersection(selected_ids)
        if duplicate:
            raise RuntimeError(f"Pilot systems overlap at HYBAS_ID {min(duplicate)}")
        all_ids.update(selected_ids)

        selected = source.filter(ee.Filter.inList("HYBAS_ID", selected_ids))
        downloaded = _download_geojson(selected, FIELDS)
        downloaded["features"].sort(key=lambda f: int(f["properties"]["HYBAS_ID"]))
        if len(downloaded["features"]) != len(selected_ids):
            raise RuntimeError(
                f"{system_id}: selected {len(selected_ids)} IDs but downloaded "
                f"{len(downloaded['features'])} geometries"
            )

        selected_set = set(selected_ids)
        row_by_id = {int(row["HYBAS_ID"]): row for row in network_rows}
        geometries = []
        source_area = 0.0
        for feature in downloaded["features"]:
            props = feature["properties"]
            basin_id = int(props["HYBAS_ID"])
            props["system_id"] = system_id
            props["system_label"] = pilot["label"]
            props["hydroclimate_stage"] = "source"
            props["basin_level"] = LEVEL
            props["is_outlet_unit"] = basin_id == outlet_id
            source_features.append(feature)
            source_area += float(props["SUB_AREA"])
            geometries.append(shape(feature["geometry"]))

            web_props = {
                key: props[key]
                for key in [
                    "HYBAS_ID", "NEXT_DOWN", "MAIN_BAS", "PFAF_ID", "SUB_AREA",
                    "UP_AREA", "ENDO", "ORDER_", "system_id", "system_label",
                    "hydroclimate_stage", "basin_level", "is_outlet_unit",
                ]
            }
            web_geometry = mapping(shape(feature["geometry"]).simplify(0.002, preserve_topology=True))
            web_features.append({"type": "Feature", "properties": web_props, "geometry": web_geometry})

            next_down = int(row_by_id[basin_id].get("NEXT_DOWN") or 0)
            if next_down in selected_set:
                scope = "inside_system"
            elif basin_id == outlet_id:
                scope = "downstream_of_system"
            elif next_down == 0:
                scope = "terminal"
            else:
                scope = "outside_system"
            routing_rows.append({
                "system_id": system_id,
                "hybas_id": basin_id,
                "next_down": next_down,
                "next_down_scope": scope,
                "outlet_hybas_id": outlet_id,
            })
            membership_rows.append({
                "system_id": system_id,
                "hybas_id": basin_id,
                "relationship": "upstream_of_or_at",
                "target_hybas_id": outlet_id,
            })

        dissolved = unary_union(geometries)
        systems.append({
            "type": "Feature",
            "properties": {
                "system_id": system_id,
                "system_label": pilot["label"],
                "hydroclimate_stage": "source",
                "outlet_hybas_id": outlet_id,
                "main_basin_id": main_basin_id,
                "basin_level": LEVEL,
                "unit_count": len(selected_ids),
                "source_area_km2": round(source_area, 1),
                "outlet_up_area_km2": round(float(outlet_properties["UP_AREA"]), 1),
            },
            "geometry": mapping(dissolved.simplify(0.002, preserve_topology=True)),
        })
        summaries.append({
            "systemId": system_id,
            "label": pilot["label"],
            "definition": pilot["definition"],
            "outletHybasId": outlet_id,
            "mainBasinId": main_basin_id,
            "controlPoint": point,
            "unitCount": len(selected_ids),
            "sourceAreaKm2": round(source_area, 1),
            "outletUpAreaKm2": round(float(outlet_properties["UP_AREA"]), 1),
        })
        print(f"  {system_id}: {len(selected_ids)} units, {source_area:,.1f} km2")

    source_document = {
        "type": "FeatureCollection",
        "name": "transboundary_headwaters_hydroatlas_level07",
        "features": sorted(source_features, key=lambda f: (f["properties"]["system_id"], int(f["properties"]["HYBAS_ID"]))),
    }
    web_document = {
        "type": "FeatureCollection",
        "name": "transboundary_headwater_units_level07",
        "features": sorted(web_features, key=lambda f: (f["properties"]["system_id"], int(f["properties"]["HYBAS_ID"]))),
    }
    systems_document = {
        "type": "FeatureCollection",
        "name": "transboundary_headwater_systems",
        "features": systems,
    }

    source_geojson = SOURCE_DIR / "hydroatlas-level07-headwaters.geojson"
    write_json(source_geojson, source_document, compact=True)
    write_json(PUBLISHED_DIR / "headwater-units.geojson", web_document, compact=True)
    write_json(PUBLISHED_DIR / "headwater-systems.geojson", systems_document, compact=True)
    _write_csv(
        PUBLISHED_DIR / "headwater-routing.csv",
        ["system_id", "hybas_id", "next_down", "next_down_scope", "outlet_hybas_id"],
        sorted(routing_rows, key=lambda row: (row["system_id"], row["hybas_id"])),
    )
    _write_csv(
        PUBLISHED_DIR / "headwater-membership.csv",
        ["system_id", "hybas_id", "relationship", "target_hybas_id"],
        sorted(membership_rows, key=lambda row: (row["system_id"], row["hybas_id"])),
    )

    manifest = {
        "version": "1.0",
        "generatedAt": generated,
        "hydroclimateStage": "source",
        "selection": "reverse NEXT_DOWN routing from a declared control unit; no national boundary filter",
        "source": {
            "platform": "Google Earth Engine",
            "asset": ASSET,
            "basinLevel": LEVEL,
            "nativeKey": "HYBAS_ID",
            "routingField": "NEXT_DOWN",
            "catalogUrl": "https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroATLAS_v1_Basins_level07",
            "technicalDocumentation": "https://data.hydrosheds.org/file/technical-documentation/HydroBASINS_TechDoc_v1c.pdf",
            "retrievedAt": generated,
        },
        "systems": summaries,
        "counts": {
            "systems": len(systems),
            "units": len(source_features),
            "routingLinks": len(routing_rows),
        },
        "outputs": {
            "sourceGeometry": str(source_geojson.relative_to(ROOT)).replace("\\", "/"),
            "publishedUnits": "PUBLISHED/data/hydroclimate/headwater-units.geojson",
            "publishedSystems": "PUBLISHED/data/hydroclimate/headwater-systems.geojson",
            "routing": "PUBLISHED/data/hydroclimate/headwater-routing.csv",
            "membership": "PUBLISHED/data/hydroclimate/headwater-membership.csv",
        },
        "sha256": {"sourceGeometry": sha256(source_geojson)},
        "qualityNotes": [
            "HydroATLAS/HydroBASINS represents natural topographic routing, not canals or water allocation.",
            "The outlet control units are a reproducible pilot definition and must later be aligned to official gauge/control-section coordinates.",
            "SUB_AREA sums can differ from outlet UP_AREA because source attributes and polygon partitioning use different upstream accounting conventions.",
        ],
    }
    write_json(SOURCE_DIR / "manifest.json", manifest)
    write_json(PUBLISHED_DIR / "headwaters-manifest.json", manifest)
    print(f"  {len(source_features)} units -> {source_geojson.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
