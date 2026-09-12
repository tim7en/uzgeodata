"""Build full Amu/Syr natural basins and nested headwater scopes at L7/L10/L12.

Every output preserves native HydroATLAS identifiers and routing fields so the
new transboundary frame can join the existing level-12 downstream model. The
full basin is selected by MAIN_BAS; the runoff-formation subset is selected by
reverse NEXT_DOWN traversal from the configured control point.

    python PIPELINES/build_transboundary_basins.py
    python PIPELINES/build_transboundary_basins.py --levels 10 12
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from shapely import coverage_simplify
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from build_headwater_pilot import _download_geojson, sha256, trace_upstream, write_json

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "ONTOLOGY/vocab/hydroclimate-system.json"
SOURCE_DIR = ROOT / "GEODATA/transboundary_basins_v2"
PUBLISHED_DIR = ROOT / "PUBLISHED/data/hydroclimate"
PROJECT = "ee-sabitovty"
FIELDS = [
    "HYBAS_ID", "NEXT_DOWN", "NEXT_SINK", "MAIN_BAS", "DIST_SINK", "DIST_MAIN",
    "SUB_AREA", "UP_AREA", "PFAF_ID", "ENDO", "COAST", "ORDER_", "SORT",
]
SYSTEM_IDS = {
    "upper_amu_darya": "amu_darya",
    "upper_syr_darya": "syr_darya",
}


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def chunks(values: list[int], size: int = 400):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def download_ids(source, ids: list[int]) -> list[dict]:
    features: list[dict] = []
    batches = list(chunks(ids))
    for position, batch in enumerate(batches, start=1):
        # inList retains native geometries and avoids uploading a client-side AOI.
        import ee

        selected = source.filter(ee.Filter.inList("HYBAS_ID", batch))
        document = _download_geojson(selected, FIELDS)
        features.extend(document["features"])
        print(f"      geometry batch {position}/{len(batches)}", flush=True)
    features.sort(key=lambda feature: int(feature["properties"]["HYBAS_ID"]))
    if len(features) != len(ids):
        raise RuntimeError(f"Requested {len(ids)} basin IDs but downloaded {len(features)}")
    return features


def prefix_parent(child_pfaf: int, parent_by_pfaf: dict[int, int], parent_level: int) -> int | None:
    text = str(int(child_pfaf))
    if len(text) < parent_level:
        return None
    return parent_by_pfaf.get(int(text[:parent_level]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--levels", nargs="+", type=int, default=[7, 10, 12])
    args = parser.parse_args()
    levels = sorted(set(args.levels))
    if any(level not in {7, 10, 12} for level in levels):
        raise SystemExit("Supported implementation levels are 7, 10 and 12")

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
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    manifests: list[dict] = []
    features_by_level: dict[int, list[dict]] = {}

    for level in levels:
        asset = f"WWF/HydroATLAS/v1/Basins/level{level:02d}"
        source = ee.FeatureCollection(asset)
        level_features: list[dict] = []
        routing_rows: list[dict] = []
        membership_rows: list[dict] = []
        system_summaries: list[dict] = []
        seen: set[int] = set()
        print(f"Level {level} | {asset}")

        for pilot in config["pilotSystems"]:
            headwater_id = pilot["id"]
            system_id = SYSTEM_IDS[headwater_id]
            point = pilot["controlPoint"]
            outlet = source.filterBounds(
                ee.Geometry.Point([point["longitude"], point["latitude"]])
            ).first()
            outlet_props = outlet.toDictionary(FIELDS).getInfo()
            outlet_id = int(outlet_props["HYBAS_ID"])
            main_basin_id = int(outlet_props["MAIN_BAS"])
            network_info = (
                source.filter(ee.Filter.eq("MAIN_BAS", main_basin_id))
                .select(FIELDS, retainGeometry=False)
                .getInfo()
            )
            network_rows = [feature["properties"] for feature in network_info["features"]]
            full_ids = sorted(int(row["HYBAS_ID"]) for row in network_rows)
            headwater_ids = trace_upstream(network_rows, outlet_id)
            if seen.intersection(full_ids):
                raise RuntimeError(f"Level {level}: Amu and Syr full-basin selections overlap")
            seen.update(full_ids)
            row_by_id = {int(row["HYBAS_ID"]): row for row in network_rows}
            headwater_set = set(headwater_ids)
            full_set = set(full_ids)

            print(
                f"  {system_id}: full {len(full_ids):,}, "
                f"headwater {len(headwater_ids):,}, outlet {outlet_id}"
            )
            downloaded = download_ids(source, full_ids)
            source_area = 0.0
            headwater_area = 0.0
            for feature in downloaded:
                props = feature["properties"]
                basin_id = int(props["HYBAS_ID"])
                in_headwaters = basin_id in headwater_set
                props.update({
                    "system_id": system_id,
                    "headwater_system_id": headwater_id,
                    "basin_level": level,
                    "in_full_basin": True,
                    "in_headwater_formation": in_headwaters,
                    "is_headwater_outlet_unit": basin_id == outlet_id,
                })
                level_features.append(feature)
                area = float(props["SUB_AREA"])
                source_area += area
                if in_headwaters:
                    headwater_area += area

                next_down = int(props.get("NEXT_DOWN") or 0)
                if next_down in full_set:
                    scope = "inside_full_basin"
                elif next_down == 0:
                    scope = "terminal"
                else:
                    scope = "outside_full_basin"
                routing_rows.append({
                    "level": level,
                    "system_id": system_id,
                    "hybas_id": basin_id,
                    "pfaf_id": int(props["PFAF_ID"]),
                    "next_down": next_down,
                    "next_down_scope": scope,
                    "main_bas": int(props["MAIN_BAS"]),
                    "headwater_outlet_hybas_id": outlet_id,
                    "in_headwater_formation": int(in_headwaters),
                })
                membership_rows.append({
                    "level": level,
                    "system_id": system_id,
                    "hybas_id": basin_id,
                    "full_basin": 1,
                    "headwater_formation": int(in_headwaters),
                    "headwater_outlet_hybas_id": outlet_id,
                })

            system_summaries.append({
                "systemId": system_id,
                "headwaterSystemId": headwater_id,
                "level": level,
                "mainBasinId": main_basin_id,
                "headwaterOutletHybasId": outlet_id,
                "controlPoint": point,
                "fullUnitCount": len(full_ids),
                "headwaterUnitCount": len(headwater_ids),
                "fullSourceAreaKm2": round(source_area, 1),
                "headwaterSourceAreaKm2": round(headwater_area, 1),
                "headwaterOutletUpAreaKm2": round(float(outlet_props["UP_AREA"]), 1),
            })

        level_features.sort(
            key=lambda feature: (feature["properties"]["system_id"], int(feature["properties"]["HYBAS_ID"]))
        )
        features_by_level[level] = level_features
        exact_document = {
            "type": "FeatureCollection",
            "name": f"amu_syr_full_basins_hydroatlas_level{level:02d}",
            "features": level_features,
        }
        exact_path = SOURCE_DIR / f"hydroatlas-level{level:02d}-full-basins.geojson"
        write_json(exact_path, exact_document, compact=True)

        web_features = []
        # One coverage per level, so neighbours keep their shared borders; simplifying
        # polygon by polygon opens slivers that a choropleth makes obvious.
        # Coverage tolerances are area-based and read larger than the old distances.
        tolerance = 0.004 if level == 7 else 0.002
        simplified = coverage_simplify([shape(feature["geometry"]) for feature in level_features], tolerance)
        for feature, geometry in zip(level_features, simplified):
            props = feature["properties"]
            web_features.append({
                "type": "Feature",
                "properties": {
                    key: props[key]
                    for key in [
                        "HYBAS_ID", "NEXT_DOWN", "MAIN_BAS", "PFAF_ID", "SUB_AREA",
                        "UP_AREA", "ENDO", "ORDER_", "system_id", "headwater_system_id",
                        "basin_level", "in_full_basin", "in_headwater_formation",
                        "is_headwater_outlet_unit",
                    ]
                },
                "geometry": mapping(geometry),
            })
        write_json(
            PUBLISHED_DIR / f"basins-level{level:02d}.geojson",
            {"type": "FeatureCollection", "name": f"amu_syr_basins_level{level:02d}", "features": web_features},
            compact=True,
        )
        write_csv(
            PUBLISHED_DIR / f"basin-routing-level{level:02d}.csv",
            [
                "level", "system_id", "hybas_id", "pfaf_id", "next_down",
                "next_down_scope", "main_bas", "headwater_outlet_hybas_id",
                "in_headwater_formation",
            ],
            routing_rows,
        )
        write_csv(
            PUBLISHED_DIR / f"basin-membership-level{level:02d}.csv",
            [
                "level", "system_id", "hybas_id", "full_basin", "headwater_formation",
                "headwater_outlet_hybas_id",
            ],
            membership_rows,
        )
        manifests.append({
            "level": level,
            "asset": asset,
            "systems": system_summaries,
            "counts": {
                "fullUnits": len(level_features),
                "headwaterUnits": sum(int(f["properties"]["in_headwater_formation"]) for f in level_features),
                "routingRows": len(routing_rows),
            },
            "outputs": {
                "exactGeoJSON": str(exact_path.relative_to(ROOT)).replace("\\", "/"),
                "webGeoJSON": f"PUBLISHED/data/hydroclimate/basins-level{level:02d}.geojson",
                "routingCSV": f"PUBLISHED/data/hydroclimate/basin-routing-level{level:02d}.csv",
                "membershipCSV": f"PUBLISHED/data/hydroclimate/basin-membership-level{level:02d}.csv",
            },
            "sha256": sha256(exact_path),
        })

        if level == 7:
            headwater_features = []
            for feature in web_features:
                if not feature["properties"]["in_headwater_formation"]:
                    continue
                compatible = {
                    "type": "Feature",
                    "properties": dict(feature["properties"]),
                    "geometry": feature["geometry"],
                }
                compatible["properties"]["river_system_id"] = compatible["properties"]["system_id"]
                compatible["properties"]["system_id"] = compatible["properties"]["headwater_system_id"]
                headwater_features.append(compatible)
            write_json(
                PUBLISHED_DIR / "headwater-units.geojson",
                {"type": "FeatureCollection", "name": "transboundary_headwater_units_level07", "features": headwater_features},
                compact=True,
            )
            full_systems = []
            headwater_systems = []
            for system_id in sorted(SYSTEM_IDS.values()):
                group = [f for f in level_features if f["properties"]["system_id"] == system_id]
                for target, subset, scope in [
                    (full_systems, group, "full_basin"),
                    (headwater_systems, [f for f in group if f["properties"]["in_headwater_formation"]], "headwater_formation"),
                ]:
                    geometry = unary_union([shape(f["geometry"]) for f in subset])
                    headwater_name = subset[0]["properties"]["headwater_system_id"]
                    target.append({
                        "type": "Feature",
                        "properties": {
                            "system_id": headwater_name if scope == "headwater_formation" else system_id,
                            "river_system_id": system_id,
                            "scope": scope,
                            "basin_level": level,
                            "unit_count": len(subset),
                            "source_area_km2": round(sum(float(f["properties"]["SUB_AREA"]) for f in subset), 1),
                        },
                        "geometry": mapping(geometry.simplify(0.002, preserve_topology=True)),
                    })
            write_json(
                PUBLISHED_DIR / "basin-systems.geojson",
                {"type": "FeatureCollection", "name": "amu_syr_full_basin_systems", "features": full_systems},
                compact=True,
            )
            write_json(
                PUBLISHED_DIR / "headwater-systems.geojson",
                {"type": "FeatureCollection", "name": "amu_syr_headwater_systems", "features": headwater_systems},
                compact=True,
            )

    hierarchy_rows: list[dict] = []
    ordered = sorted(features_by_level)
    for parent_level, child_level in zip(ordered, ordered[1:]):
        parents = features_by_level[parent_level]
        children = features_by_level[child_level]
        for system_id in sorted(SYSTEM_IDS.values()):
            parent_lookup = {
                int(feature["properties"]["PFAF_ID"]): int(feature["properties"]["HYBAS_ID"])
                for feature in parents if feature["properties"]["system_id"] == system_id
            }
            for child in (f for f in children if f["properties"]["system_id"] == system_id):
                props = child["properties"]
                parent_id = prefix_parent(int(props["PFAF_ID"]), parent_lookup, parent_level)
                hierarchy_rows.append({
                    "system_id": system_id,
                    "child_level": child_level,
                    "child_hybas_id": int(props["HYBAS_ID"]),
                    "child_pfaf_id": int(props["PFAF_ID"]),
                    "parent_level": parent_level,
                    "parent_hybas_id": parent_id or "",
                    "match_rule": "pfaf_prefix" if parent_id else "unresolved",
                })
    write_csv(
        PUBLISHED_DIR / "basin-hierarchy.csv",
        [
            "system_id", "child_level", "child_hybas_id", "child_pfaf_id",
            "parent_level", "parent_hybas_id", "match_rule",
        ],
        hierarchy_rows,
    )

    manifest = {
        "version": "2.0",
        "generatedAt": generated,
        "selection": {
            "full_basin": "all HydroATLAS units sharing MAIN_BAS with the control-point unit",
            "headwater_formation": "reverse NEXT_DOWN trace to the configured upper control-point unit",
            "administrativeBoundaryFilter": False,
        },
        "levels": manifests,
        "hierarchy": {
            "container": "PUBLISHED/data/hydroclimate/basin-hierarchy.csv",
            "rows": len(hierarchy_rows),
            "rule": "Pfafstetter prefix between implemented analysis levels",
            "unresolved": sum(row["match_rule"] == "unresolved" for row in hierarchy_rows),
        },
        "compatibility": {
            "nativeFields": FIELDS,
            "existingDownstreamReference": "BasinATLAS level 12 / HYBAS_ID / NEXT_DOWN",
            "note": "Level-12 outputs use the same identifier family and routing fields as the existing downstream frame; managed canals remain a separate graph.",
        },
        "sources": {
            "platform": "Google Earth Engine",
            "catalog": "https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroATLAS_v1_Basins_level12",
            "retrievedAt": generated,
        },
    }
    write_json(SOURCE_DIR / "manifest.json", manifest)
    write_json(PUBLISHED_DIR / "transboundary-basins-manifest.json", manifest)
    print(f"Manifest -> {(PUBLISHED_DIR / 'transboundary-basins-manifest.json').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
