"""Intersect the environmental atlas with the level-12 basin reference.

The ontology can say which reach drains a basin and which lake sits in one, but
it could not say anything about the 134 atlas packages at basin level: they were
pinned to `uz:place/uzbekistan` and nothing finer. This script measures the
missing link.

For every atlas dataset that has published vector geometry it overlays the
features on the BasinATLAS Uzbekistan level-12 basins and records one row per
(dataset, basin) pair that actually overlaps, with the magnitude:

    polygons   overlap area in km2, on the equal-area CRS the extraction uses
    lines      length inside the basin, in km
    points     how many fall inside the basin

The result is an edge list, not an assertion set: at up to 3,981 basins per
dataset it belongs in a relationship table, registered in the graph by
`ontology/vocab/relationship-tables.json` and read from disk when someone asks.

Rasters that were never polygonised have no geometry to overlay, so they are
skipped and named in the manifest rather than silently dropped. Run
`scripts/raster_to_geojson.py` over them first to bring them in.

Usage:
    python scripts/build_atlas_basin_links.py [--root .] [--level 12]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import geopandas as gpd
    import pandas as pd
except ImportError as error:  # pragma: no cover - depends on the workstation
    raise SystemExit(
        "geopandas and pandas are required. This is the same environment "
        "scripts/extract_uz_basinatlas.py runs in."
    ) from error

VECTOR_CRS = "EPSG:4326"
# Planar equal-area, the same convention the BasinATLAS extraction reports areas
# in, so an overlap here is comparable with UZB_KM2 there.
AREA_CRS = "EPSG:6933"

# Where a distribution's storedName resolves, by role.
ROLE_DIRECTORIES = {
    "web-vector": Path("storage") / "derived" / "web-layers",
    "raster-polygonized": Path("storage") / "derived" / "raster-geojson",
}

POLYGONAL = {"Polygon", "MultiPolygon"}
LINEAR = {"LineString", "MultiLineString"}
PUNCTUAL = {"Point", "MultiPoint"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def atlas_layers(root: Path) -> list[dict]:
    """Every atlas dataset that has geometry, with the file that holds it.

    Identity comes from the graph rather than the layer registry, so the subject
    column carries a real dataset ID the validator can resolve.
    """
    entities = {e["id"]: e for e in
                read_json(root / "ontology" / "instances" / "entities.json",
                          {"entities": []})["entities"]}
    assertions = read_json(root / "ontology" / "instances" / "assertions.json",
                           {"assertions": []})["assertions"]

    distributions: dict[str, list[str]] = {}
    for assertion in assertions:
        if assertion["predicate"] == "uz:hasDistribution":
            distributions.setdefault(assertion["subject"], []).append(assertion["object"])

    layers = []
    for dataset in entities.values():
        if dataset.get("type") != "Dataset" or not dataset.get("catalogId"):
            continue
        for dist_id in distributions.get(dataset["id"], []):
            dist = entities.get(dist_id, {})
            directory = ROLE_DIRECTORIES.get(dist.get("role"))
            if directory is None or not dist.get("storedName"):
                continue
            path = root / directory / dist["storedName"]
            layers.append({
                "dataset": dataset["id"],
                "label": dataset["label"],
                "atlasNumber": dataset.get("atlasNumber"),
                "distribution": dist_id,
                "role": dist["role"],
                "path": path,
                "exists": path.exists(),
            })
    return sorted(layers, key=lambda item: item["dataset"])


def load_basins(root: Path, level: int) -> gpd.GeoDataFrame:
    package = root / "earth_engine" / "earth_engine" / "uzbekistan_basinatlas_v10"
    gpkg = package / "uzbekistan_basinatlas_v10.gpkg"
    if not gpkg.exists():
        raise SystemExit(f"Basin reference not found: {gpkg}")
    basins = gpd.read_file(gpkg, layer=f"basinatlas_uz_lev{level:02d}",
                           columns=["HYBAS_ID", "PFAF_ID", "UZB_KM2"])
    basins = basins.to_crs(VECTOR_CRS)
    basins["HYBAS_ID"] = basins["HYBAS_ID"].astype("int64")
    return basins[["HYBAS_ID", "geometry"]]


def measure_for(kind: str) -> tuple[str, str]:
    if kind == "polygon":
        return "overlap_km2", "km2"
    if kind == "line":
        return "length_km", "km"
    return "feature_count", "count"


def geometry_kind(frame: gpd.GeoDataFrame) -> str | None:
    kinds = set(frame.geom_type.dropna().unique())
    if kinds & POLYGONAL:
        return "polygon"
    if kinds & LINEAR:
        return "line"
    if kinds & PUNCTUAL:
        return "point"
    return None


def overlay(layer: dict, basins: gpd.GeoDataFrame) -> tuple[list[dict], dict]:
    """One row per (dataset, basin) the layer actually reaches."""
    frame = gpd.read_file(layer["path"])
    if frame.empty:
        return [], {"features": 0, "note": "layer has no features"}
    if frame.crs is None:
        # Every published layer is written as WGS 84; say so rather than guess
        # silently, so a future layer that is not gets caught by the note.
        frame = frame.set_crs(VECTOR_CRS)
        assumed = True
    else:
        frame = frame.to_crs(VECTOR_CRS)
        assumed = False

    frame = frame[frame.geometry.notna() & ~frame.geometry.is_empty]
    if frame.empty:
        return [], {"features": 0, "note": "no usable geometry"}
    kind = geometry_kind(frame)
    if kind is None:
        return [], {"features": len(frame), "note": "unsupported geometry type"}

    frame = frame[["geometry"]].copy()
    if not frame.geometry.is_valid.all():
        frame["geometry"] = frame.geometry.make_valid()

    column, unit = measure_for(kind)
    if kind == "point":
        joined = gpd.sjoin(frame, basins, how="inner", predicate="within")
        grouped = joined.groupby("HYBAS_ID").size().reset_index(name=column)
    else:
        pieces = gpd.overlay(frame, basins, how="intersection", keep_geom_type=True)
        if pieces.empty:
            return [], {"features": len(frame), "note": "no overlap with the basin reference"}
        pieces = pieces.to_crs(AREA_CRS)
        pieces[column] = (pieces.geometry.area / 1_000_000 if kind == "polygon"
                          else pieces.geometry.length / 1_000)
        grouped = pieces.groupby("HYBAS_ID").agg(
            **{column: (column, "sum"), "parts": (column, "size")}
        ).reset_index()

    rows = []
    for record in grouped.to_dict("records"):
        rows.append({
            "dataset_id": layer["dataset"],
            "atlas_number": layer["atlasNumber"],
            "basin_id": int(record["HYBAS_ID"]),
            "geometry_kind": kind,
            "feature_parts": int(record.get("parts", record.get(column, 0))
                                 if kind != "point" else record[column]),
            "measure": round(float(record[column]), 6),
            "measure_unit": unit,
            "distribution": layer["distribution"],
        })
    return rows, {"features": len(frame), "kind": kind, "basins": len(rows),
                  "crsAssumed": assumed}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--level", type=int, default=12,
                        help="BasinATLAS level to link against (default 12)")
    args = parser.parse_args(argv)
    root = args.root.resolve()

    layers = atlas_layers(root)
    present = [layer for layer in layers if layer["exists"]]
    missing = [layer for layer in layers if not layer["exists"]]
    print(f"atlas layers with geometry: {len(layers)} ({len(present)} on disk)")

    basins = load_basins(root, args.level)
    print(f"basin reference: {len(basins):,} level-{args.level:02d} basins")

    rows: list[dict] = []
    per_layer = []
    for index, layer in enumerate(present, start=1):
        try:
            produced, note = overlay(layer, basins)
        except Exception as error:  # a bad layer must not lose the other 77
            produced, note = [], {"error": str(error)}
        rows.extend(produced)
        per_layer.append({"dataset": layer["dataset"], "distribution": layer["distribution"],
                          "rows": len(produced), **note})
        print(f"  [{index:>3}/{len(present)}] {layer['dataset']:<52} "
              f"{len(produced):>5} basins  {note.get('kind') or note.get('note') or note.get('error', '')}")

    output = root / "storage" / "derived" / "atlas-basin-links.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    columns = ["dataset_id", "atlas_number", "basin_id", "geometry_kind",
               "feature_parts", "measure", "measure_unit", "distribution"]
    table = pd.DataFrame(rows, columns=columns)
    # Nullable integer: one dataset has no atlas number, and the default float
    # coercion would write every other one as "100.0".
    table["atlas_number"] = table["atlas_number"].astype("Int64")
    table.to_csv(output, index=False, encoding="utf-8", lineterminator="\n")

    # Rasters with no polygonised counterpart are the honest gap in the coverage.
    entities = {e["id"]: e for e in
                read_json(root / "ontology" / "instances" / "entities.json",
                          {"entities": []})["entities"]}
    linked = {layer["dataset"] for layer in layers}
    uncovered = sorted(e["id"] for e in entities.values()
                       if e.get("type") == "Dataset" and e.get("catalogId")
                       and e["id"] not in linked)

    manifest = {
        "version": "1.0",
        "generatedAt": utc_now(),
        "predicate": "uz:coversBasin",
        "subjectType": "Dataset",
        "objectType": "Basin",
        "basinLevel": args.level,
        "basinReference": f"uzbekistan_basinatlas_v10 :: basinatlas_uz_lev{args.level:02d}",
        "basins": int(len(basins)),
        "vectorCrs": VECTOR_CRS,
        "areaCrs": AREA_CRS,
        "measures": {"polygon": "overlap area, km2", "line": "length inside the basin, km",
                     "point": "features inside the basin, count"},
        "counts": {
            "atlasBasinLinks": len(rows),
            "datasetsLinked": len({row["dataset_id"] for row in rows}),
            "layersRead": len(present),
            "layersMissingOnDisk": len(missing),
            "datasetsWithoutGeometry": len(uncovered),
        },
        "output": str(output.relative_to(root)).replace("\\", "/"),
        "perLayer": per_layer,
        "missingOnDisk": [layer["distribution"] for layer in missing],
        "datasetsWithoutGeometry": uncovered,
        "note": (
            "Datasets without geometry are raster packages whose only derivative is a "
            "PNG preview. Run scripts/raster_to_geojson.py over them to bring them into "
            "this table."
        ),
    }
    write_json(root / "ontology" / "instances" / "atlas-basin-links.json", manifest)

    print(f"\n{len(rows):,} links across {manifest['counts']['datasetsLinked']} datasets "
          f"-> {output}")
    print(f"{len(uncovered)} atlas datasets still have no geometry to overlay")
    return 0


if __name__ == "__main__":
    sys.exit(main())
