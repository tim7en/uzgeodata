"""Build the non-contributing and terminal context around the Amu/Syr network.

The natural Amu Darya and Syr Darya selections are deliberately based on
HydroATLAS ``MAIN_BAS``.  Their union therefore contains a large interior gap:
closed desert catchments that do not route to either river.  The Aral Sea is a
terminal receiving water body, not another runoff-producing catchment.  This
pipeline publishes both kinds of context so the map can show a complete domain
without creating false river or basin links.

The desert units are downloaded from the same Earth Engine HydroATLAS source as
the two natural basin frames.  The Large and Small Aral reference polygons are
reused from the local HydroLAKES extraction.

    python PIPELINES/build_aral_hydrographic_domain.py
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon, mapping, shape
from shapely.ops import unary_union

from build_headwater_pilot import _download_geojson, sha256

ROOT = Path(__file__).resolve().parent.parent
PROJECT = "ee-sabitovty"
LEVEL = 7
NATURAL_BASINS = ROOT / "PUBLISHED/data/hydroclimate/basins-level07.geojson"
ARAL_WATER_BODIES = ROOT / "PUBLISHED/data/hydroclimate/water-bodies-transboundary.geojson"
OUTPUT = ROOT / "PUBLISHED/data/hydroclimate/aral-hydrographic-context.geojson"
TABLE = ROOT / "PUBLISHED/data/hydroclimate/aral-hydrographic-context.csv"
MANIFEST = ROOT / "PUBLISHED/data/hydroclimate/aral-hydrographic-context.manifest.json"
FIELDS = [
    "HYBAS_ID", "NEXT_DOWN", "NEXT_SINK", "MAIN_BAS", "SUB_AREA", "UP_AREA",
    "PFAF_ID", "ENDO", "COAST", "ORDER_", "SORT",
]
TABLE_FIELDS = [
    "entity_id", "entity_type", "label", "domain_role", "natural_connection",
    "contributes_to_amu_syr", "runoff_treatment", "climate_treatment",
    "hybas_id", "main_basin", "next_down", "pfaf_id", "area_km2",
    "source_asset", "retrieved_at",
]


def write_json(path: Path, payload: object, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(
            payload, handle, ensure_ascii=False,
            indent=None if compact else 2,
            separators=(",", ":") if compact else None,
        )
        handle.write("\n")
    os.replace(temporary, path)


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TABLE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def area_km2(geometry) -> float:
    return float(gpd.GeoSeries([geometry], crs=4326).to_crs(6933).area.iloc[0] / 1_000_000)


def principal_interior_gap(minimum_area_km2: float):
    frame = gpd.read_file(NATURAL_BASINS)
    combined = unary_union([geometry if geometry.is_valid else geometry.buffer(0) for geometry in frame.geometry])
    polygons = list(combined.geoms) if combined.geom_type == "MultiPolygon" else [combined]
    gaps = [
        Polygon(ring)
        for polygon in polygons
        for ring in polygon.interiors
        if area_km2(Polygon(ring)) >= minimum_area_km2
    ]
    if len(gaps) != 1:
        raise RuntimeError(
            f"Expected one interior non-contributing region above {minimum_area_km2:g} km2; found {len(gaps)}"
        )
    return gaps[0], frame


def desert_context(gap, natural_frame, simplify: float, retrieved: str):
    try:
        import ee

        ee.Initialize(project=PROJECT)
        ee.Number(1).getInfo()
    except Exception as error:
        raise SystemExit(
            f"Earth Engine unavailable: {str(error).strip()[:180]}\n"
            f"  Run: earthengine authenticate --project {PROJECT}"
        ) from error

    # A simplified polygon is sufficient for the server-side candidate query;
    # source geometries are returned without clipping and tested against the
    # exact gap locally.
    query_geometry = gap.simplify(0.01, preserve_topology=True)
    source = ee.FeatureCollection(f"WWF/HydroATLAS/v1/Basins/level{LEVEL:02d}")
    candidates = source.filterBounds(ee.Geometry(mapping(query_geometry)))
    document = _download_geojson(candidates, FIELDS)
    natural_main_basins = {int(value) for value in natural_frame["MAIN_BAS"]}

    features = []
    rows = []
    for feature in document["features"]:
        properties = feature["properties"]
        geometry = shape(feature["geometry"])
        if not geometry.is_valid:
            geometry = geometry.buffer(0)
        overlap = geometry.intersection(gap)
        if overlap.is_empty or overlap.area / geometry.area <= 0.5:
            continue
        if int(properties["MAIN_BAS"]) in natural_main_basins:
            continue

        basin_id = int(properties["HYBAS_ID"])
        is_sink = int(properties.get("ENDO") or 0) == 2 and basin_id == int(properties["MAIN_BAS"])
        label = f"Closed-drainage sink {properties['PFAF_ID']}" if is_sink else f"Internal catchment {properties['PFAF_ID']}"
        shared = {
            "entity_id": f"hybas:{basin_id}",
            "entity_type": "basin",
            "label": label,
            "domain_role": "non_contributing_internal_drainage",
            "natural_connection": "local_closed_sink",
            "contributes_to_amu_syr": False,
            "runoff_treatment": "local_runoff_only",
            "climate_treatment": "exposure_context",
            "hybas_id": basin_id,
            "main_basin": int(properties["MAIN_BAS"]),
            "next_down": int(properties.get("NEXT_DOWN") or 0),
            "pfaf_id": int(properties["PFAF_ID"]),
            "area_km2": round(float(properties["SUB_AREA"]), 1),
            "source_asset": f"WWF/HydroATLAS/v1/Basins/level{LEVEL:02d}",
            "retrieved_at": retrieved,
        }
        features.append({
            "type": "Feature",
            "properties": {**shared, "is_terminal_sink": is_sink},
            "geometry": mapping(geometry.simplify(simplify, preserve_topology=True)),
        })
        rows.append(shared)

    features.sort(key=lambda item: item["properties"]["hybas_id"])
    rows.sort(key=lambda item: item["hybas_id"])
    return features, rows


def aral_receptors(simplify: float, retrieved: str):
    document = json.loads(ARAL_WATER_BODIES.read_text(encoding="utf-8"))
    wanted = {"Large Aral Sea", "Small Aral Sea"}
    features = []
    rows = []
    for feature in document["features"]:
        properties = feature["properties"]
        if properties.get("name") not in wanted:
            continue
        body_id = int(properties["water_body_id"])
        system_id = properties["system_id"]
        geometry = shape(feature["geometry"])
        shared = {
            "entity_id": f"hydrolake:{body_id}",
            "entity_type": "water_body",
            "label": properties["name"],
            "domain_role": "terminal_receiving_waterbody",
            "natural_connection": f"receives_{system_id}",
            "contributes_to_amu_syr": False,
            "runoff_treatment": "terminal_water_balance",
            "climate_treatment": "precipitation_and_evaporation_over_water",
            "hybas_id": "",
            "main_basin": "",
            "next_down": "",
            "pfaf_id": "",
            "area_km2": round(float(properties["area_km2"]), 1),
            "source_asset": "HydroLAKES v1.0 static reference polygon",
            "retrieved_at": retrieved,
        }
        features.append({
            "type": "Feature",
            "properties": shared,
            "geometry": mapping(geometry.simplify(simplify, preserve_topology=True)),
        })
        rows.append(shared)
    if {feature["properties"]["label"] for feature in features} != wanted:
        raise RuntimeError("The transboundary HydroLAKES layer must contain Large and Small Aral Sea")
    return features, rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minimum-gap-km2", type=float, default=1000)
    parser.add_argument("--simplify", type=float, default=0.002, help="web geometry tolerance in degrees")
    args = parser.parse_args()
    for path in (NATURAL_BASINS, ARAL_WATER_BODIES):
        if not path.exists():
            raise SystemExit(f"Missing {path.relative_to(ROOT)}")

    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    gap, natural_frame = principal_interior_gap(args.minimum_gap_km2)
    desert_features, desert_rows = desert_context(gap, natural_frame, args.simplify, retrieved)
    receptor_features, receptor_rows = aral_receptors(args.simplify, retrieved)
    all_features = [*desert_features, *receptor_features]
    all_rows = [*desert_rows, *receptor_rows]

    write_json(OUTPUT, {
        "type": "FeatureCollection",
        "name": "aral_hydrographic_context",
        "features": all_features,
    }, compact=True)
    write_csv(TABLE, all_rows)

    desert_source_area = sum(float(row["area_km2"]) for row in desert_rows)
    sink_count = sum(1 for feature in desert_features if feature["properties"]["is_terminal_sink"])
    manifest = {
        "version": "1.0",
        "generatedAt": retrieved,
        "spatialScope": "aral_hydrographic_domain",
        "purpose": "Explain non-river areas without assigning false Amu/Syr connectivity.",
        "selection": {
            "naturalFrame": "union of Amu and Syr level-7 MAIN_BAS selections",
            "desertContext": "HydroATLAS level-7 units with more than half their geometry in the principal interior gap",
            "terminalContext": "Large and Small Aral Sea records from the transboundary HydroLAKES extraction",
        },
        "counts": {
            "internalDrainageUnits": len(desert_features),
            "independentInternalDrainageSystems": len({row["main_basin"] for row in desert_rows}),
            "terminalSinkUnits": sink_count,
            "terminalReceivingWaterBodies": len(receptor_features),
        },
        "areasKm2": {
            "principalInteriorGap": round(area_km2(gap), 1),
            "selectedHydroAtlasUnits": round(desert_source_area, 1),
        },
        "sources": {
            "internalDrainage": f"WWF/HydroATLAS/v1/Basins/level{LEVEL:02d} via Earth Engine",
            "terminalWaterBodies": "HydroLAKES v1.0 local transboundary extraction",
        },
        "outputs": {
            "geojson": str(OUTPUT.relative_to(ROOT)).replace("\\", "/"),
            "csv": str(TABLE.relative_to(ROOT)).replace("\\", "/"),
        },
        "qualityNotes": [
            "Internal-drainage units are domain context and do not contribute natural flow to the Amu Darya or Syr Darya.",
            "No synthetic river reaches or cross-basin links are created in desert areas.",
            "HydroLAKES shorelines and areas are static reference inventory values, not current Aral water extent or storage.",
            "Managed canals and transfers require a separate infrastructure graph and must not be inferred from natural catchments.",
        ],
        "files": {
            "geojson": {"path": str(OUTPUT.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(OUTPUT)},
            "csv": {"path": str(TABLE.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(TABLE)},
        },
    }
    write_json(MANIFEST, manifest)
    print(
        f"Aral hydrographic context | {len(desert_features)} internal-drainage L7 units "
        f"in {manifest['counts']['independentInternalDrainageSystems']} systems; "
        f"{len(receptor_features)} terminal water bodies"
    )
    print(
        f"  gap {manifest['areasKm2']['principalInteriorGap']:,.1f} km2; "
        f"source units {manifest['areasKm2']['selectedHydroAtlasUnits']:,.1f} km2"
    )
    print(f"  -> {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
