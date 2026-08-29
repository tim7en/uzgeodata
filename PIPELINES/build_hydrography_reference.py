"""Build an Uzbekistan hydrography relationship database around a basin reference.

The level-12 basins of the BasinATLAS Uzbekistan extraction are the reference
frame: every basin in that selection is published, and rivers and lakes are then
joined onto it.  The basin set is never derived from the feature layers, because
doing so drops any basin the features happen not to mention and leaves reaches
pointing at catchments that were never written.

BasinATLAS is in standard HydroBASINS format, which is the format HydroRIVERS'
``HYBAS_L12`` keys to.  The lake-format package this build previously read splits
basins at lakes and therefore mints different identifiers, so 569 of the 3,147
basins the reaches referenced had no polygon and 3,073 reaches were orphaned.

Anything that still fails to resolve is reported: a warning on stderr, a
``warnings`` list in both JSON outputs, and a ``basin_scope`` column on the link
tables.  Nothing is dropped silently.

The canonical local output is a GeoPackage containing clipped river, lake and
level-12 basin geometry plus explicit relationship tables.  Lightweight
GeoJSON and JSON projections are written for the browser explorer.  Run this
with the Python environment shipped with QGIS so ``osgeo`` is available.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from osgeo import gdal, ogr, osr
except ImportError as error:  # pragma: no cover - depends on workstation GIS install
    raise SystemExit(
        "GDAL Python bindings are required. Run with QGIS Python, for example "
        "scripts/run_hydrography_build.ps1"
    ) from error


RIVER_FIELDS = {
    "HYRIV_ID": ogr.OFTInteger64,
    "NEXT_DOWN": ogr.OFTInteger64,
    "MAIN_RIV": ogr.OFTInteger64,
    "LENGTH_KM": ogr.OFTReal,
    "DIST_DN_KM": ogr.OFTReal,
    "DIST_UP_KM": ogr.OFTReal,
    "CATCH_SKM": ogr.OFTReal,
    "UPLAND_SKM": ogr.OFTReal,
    "ENDORHEIC": ogr.OFTInteger,
    "DIS_AV_CMS": ogr.OFTReal,
    "ORD_STRA": ogr.OFTInteger,
    "ORD_CLAS": ogr.OFTInteger,
    "ORD_FLOW": ogr.OFTInteger,
    "HYBAS_L12": ogr.OFTInteger64,
}

LAKE_FIELDS = {
    "Hylak_id": ogr.OFTInteger64,
    "Lake_name": ogr.OFTString,
    "Country": ogr.OFTString,
    "Continent": ogr.OFTString,
    "Poly_src": ogr.OFTString,
    "Lake_type": ogr.OFTInteger,
    "Grand_id": ogr.OFTInteger64,
    "Lake_area": ogr.OFTReal,
    "Shore_len": ogr.OFTReal,
    "Shore_dev": ogr.OFTReal,
    "Vol_total": ogr.OFTReal,
    "Vol_res": ogr.OFTReal,
    "Vol_src": ogr.OFTInteger,
    "Depth_avg": ogr.OFTReal,
    "Dis_avg": ogr.OFTReal,
    "Res_time": ogr.OFTReal,
    "Elevation": ogr.OFTInteger,
    "Slope_100": ogr.OFTReal,
    "Wshd_area": ogr.OFTReal,
    "Pour_long": ogr.OFTReal,
    "Pour_lat": ogr.OFTReal,
}

# The HydroBASINS core as BasinATLAS carries it, plus the three fields the
# extraction adds.  BasinATLAS has no LAKE or SIDE field, and SRC_TILE becomes
# SRC_LAYER because the source is one global layer set rather than regional tiles.
BASIN_FIELDS = {
    "HYBAS_ID": ogr.OFTInteger64,
    "NEXT_DOWN": ogr.OFTInteger64,
    "NEXT_SINK": ogr.OFTInteger64,
    "MAIN_BAS": ogr.OFTInteger64,
    "DIST_SINK": ogr.OFTReal,
    "DIST_MAIN": ogr.OFTReal,
    "SUB_AREA": ogr.OFTReal,
    "UP_AREA": ogr.OFTReal,
    "PFAF_ID": ogr.OFTInteger64,
    "ENDO": ogr.OFTInteger,
    "COAST": ogr.OFTInteger,
    "ORDER_": ogr.OFTInteger,
    "SORT": ogr.OFTInteger64,
    "SRC_LAYER": ogr.OFTString,
    "UZB_KM2": ogr.OFTReal,
    "UZB_PCT": ogr.OFTReal,
}

BASIN_INTEGER_FIELDS = (
    "HYBAS_ID", "NEXT_DOWN", "NEXT_SINK", "MAIN_BAS",
    "PFAF_ID", "ENDO", "COAST", "ORDER_", "SORT",
)

WEB_RIVER_FIELDS = list(RIVER_FIELDS)
WEB_LAKE_FIELDS = list(LAKE_FIELDS) + ["HYBAS_L12"]
# The browser needs identity, routing, size and the national share; the sink
# distances and the sort key stay in the GeoPackage.
WEB_BASIN_FIELDS = [
    "HYBAS_ID", "NEXT_DOWN", "MAIN_BAS", "PFAF_ID", "SUB_AREA", "UP_AREA",
    "ENDO", "ORDER_", "SRC_LAYER", "UZB_KM2", "UZB_PCT",
]

# The 281 BasinATLAS attributes are deliberately not copied here.  They join on
# HYBAS_ID against the extraction's own GeoPackage layer and attribute CSVs, and
# every column is decoded in ontology/instances/hydroatlas-columns.json.
ATTRIBUTE_JOIN_KEY = "HYBAS_ID"

WARNINGS: list[dict] = []


def warn(code: str, message: str, **detail) -> None:
    """Record a defect instead of dropping a feature silently."""
    entry = {"code": code, "message": message}
    entry.update(detail)
    WARNINGS.append(entry)
    print(f"WARNING [{code}] {message}", file=sys.stderr)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def resolve_file_gdb(path: Path) -> Path:
    """Accept either a FileGDB itself or Explorer's same-named wrapper folder."""
    if not path.exists():
        raise FileNotFoundError(path)
    direct = gdal.OpenEx(str(path), gdal.OF_VECTOR | gdal.OF_READONLY)
    if direct is not None:
        direct = None
        return path
    nested = path / path.name
    if nested.is_dir():
        dataset = gdal.OpenEx(str(nested), gdal.OF_VECTOR | gdal.OF_READONLY)
        if dataset is not None:
            dataset = None
            return nested
    raise RuntimeError(f"No readable FileGDB found at {path}")


def open_layer(path: Path, layer_name: str):
    dataset = ogr.Open(str(path), 0)
    if dataset is None:
        raise RuntimeError(f"Could not open {path}")
    layer = dataset.GetLayerByName(layer_name)
    if layer is None:
        available = [dataset.GetLayerByIndex(i).GetName() for i in range(dataset.GetLayerCount())]
        raise RuntimeError(f"Layer {layer_name!r} not found in {path}; available: {available}")
    return dataset, layer


def read_boundary(path: Path):
    dataset = ogr.Open(str(path), 0)
    if dataset is None:
        raise RuntimeError(f"Could not open Uzbekistan boundary: {path}")
    layer = dataset.GetLayer(0)
    feature = layer.GetNextFeature()
    if feature is None or feature.GetGeometryRef() is None:
        raise RuntimeError(f"Boundary has no geometry: {path}")
    geometry = feature.GetGeometryRef().Clone()
    if not geometry.IsValid():
        geometry = geometry.MakeValid()
    dataset = None
    return geometry


def wgs84():
    spatial_reference = osr.SpatialReference()
    spatial_reference.ImportFromEPSG(4326)
    return spatial_reference


def create_layer(dataset, name: str, geometry_type: int, fields: dict):
    layer = dataset.CreateLayer(name, srs=wgs84(), geom_type=geometry_type)
    if layer is None:
        raise RuntimeError(f"Could not create layer {name}")
    for field_name, field_type in fields.items():
        definition = ogr.FieldDefn(field_name, field_type)
        if field_type == ogr.OFTString:
            definition.SetWidth(80)
        if layer.CreateField(definition) != ogr.OGRERR_NONE:
            raise RuntimeError(f"Could not create {name}.{field_name}")
    return layer


def field_value(feature, name: str):
    index = feature.GetFieldIndex(name)
    if index < 0 or not feature.IsFieldSetAndNotNull(index):
        return None
    return feature.GetField(index)


def integer(value):
    if value in (None, ""):
        return None
    return int(float(value))


def set_fields(target, values: dict) -> None:
    for name, value in values.items():
        if value is not None:
            target.SetField(name, value)


def polygon_parts(geometry):
    flattened = ogr.GT_Flatten(geometry.GetGeometryType())
    if flattened in (ogr.wkbPolygon, ogr.wkbMultiPolygon):
        return ogr.ForceToMultiPolygon(geometry)
    if flattened == ogr.wkbGeometryCollection:
        result = ogr.Geometry(ogr.wkbMultiPolygon)
        for index in range(geometry.GetGeometryCount()):
            part = geometry.GetGeometryRef(index)
            if ogr.GT_Flatten(part.GetGeometryType()) == ogr.wkbPolygon:
                result.AddGeometry(part)
            elif ogr.GT_Flatten(part.GetGeometryType()) == ogr.wkbMultiPolygon:
                for child_index in range(part.GetGeometryCount()):
                    result.AddGeometry(part.GetGeometryRef(child_index))
        return result
    return None


def line_parts(geometry):
    flattened = ogr.GT_Flatten(geometry.GetGeometryType())
    if flattened in (ogr.wkbLineString, ogr.wkbMultiLineString):
        return ogr.ForceToMultiLineString(geometry)
    if flattened == ogr.wkbGeometryCollection:
        result = ogr.Geometry(ogr.wkbMultiLineString)
        for index in range(geometry.GetGeometryCount()):
            part = geometry.GetGeometryRef(index)
            if ogr.GT_Flatten(part.GetGeometryType()) == ogr.wkbLineString:
                result.AddGeometry(part)
            elif ogr.GT_Flatten(part.GetGeometryType()) == ogr.wkbMultiLineString:
                for child_index in range(part.GetGeometryCount()):
                    result.AddGeometry(part.GetGeometryRef(child_index))
        return result
    return None


def clipped_geometry(source_geometry, boundary, kind: str):
    if source_geometry is None or source_geometry.IsEmpty() or not source_geometry.Intersects(boundary):
        return None
    try:
        clipped = source_geometry.Intersection(boundary)
    except RuntimeError:
        clipped = source_geometry.MakeValid().Intersection(boundary)
    if clipped is None or clipped.IsEmpty():
        return None
    normalized = line_parts(clipped) if kind == "line" else polygon_parts(clipped)
    if normalized is None or normalized.IsEmpty():
        return None
    return normalized


def copy_selected_layer(source_layer, target_layer, boundary, field_types: dict, kind: str):
    source_layer.SetSpatialFilter(boundary)
    target_definition = target_layer.GetLayerDefn()
    records = []
    for source in source_layer:
        geometry = clipped_geometry(source.GetGeometryRef(), boundary, kind)
        if geometry is None:
            continue
        values = {name: field_value(source, name) for name in field_types}
        if "HYBAS_L12" in values:
            values["HYBAS_L12"] = integer(values["HYBAS_L12"])
        target = ogr.Feature(target_definition)
        set_fields(target, values)
        target.SetGeometry(geometry)
        if target_layer.CreateFeature(target) != ogr.OGRERR_NONE:
            raise RuntimeError(f"Failed writing feature to {target_layer.GetName()}")
        records.append(values)
        target = None
    source_layer.SetSpatialFilter(None)
    return records


def load_basins(path: Path, layer_name: str):
    """Read the basin reference: every level-12 basin of the extraction.

    Geometry is kept unclipped so a lake pour point just outside the border still
    resolves to its basin.  Clipping happens only on the way out.
    """
    dataset, layer = open_layer(path, layer_name)
    records = {}
    for feature in layer:
        values = {name: field_value(feature, name) for name in BASIN_FIELDS}
        for name in BASIN_INTEGER_FIELDS:
            values[name] = integer(values[name])
        basin_id = values["HYBAS_ID"]
        if basin_id is None:
            warn("basin-missing-id", f"A feature in {layer_name} has no HYBAS_ID and was skipped")
            continue
        geometry = feature.GetGeometryRef()
        if geometry is None or geometry.IsEmpty():
            warn("basin-missing-geometry", f"Basin {basin_id} has no geometry and was skipped",
                 basinId=basin_id)
            continue
        if basin_id in records:
            warn("basin-duplicate-id", f"Basin {basin_id} appears more than once in {layer_name}",
                 basinId=basin_id)
        records[basin_id] = {"values": values, "geometry": geometry.Clone()}
    dataset = None
    if not records:
        raise RuntimeError(f"Basin reference {layer_name} in {path} is empty")
    return records


def basin_for_lake(values: dict, clipped, basins: dict) -> int | None:
    longitude = values.get("Pour_long")
    latitude = values.get("Pour_lat")
    point = None
    if longitude not in (None, 0) and latitude not in (None, 0):
        point = ogr.Geometry(ogr.wkbPoint)
        point.AddPoint_2D(float(longitude), float(latitude))
    candidates = []
    if point is not None:
        candidates.append(point)
    centroid = clipped.Centroid()
    if centroid is not None and not centroid.IsEmpty():
        candidates.append(centroid)
    for candidate in candidates:
        x, y, _ = candidate.GetPoint(0)
        for basin_id, basin in basins.items():
            west, east, south, north = basin["geometry"].GetEnvelope()
            if west <= x <= east and south <= y <= north and basin["geometry"].Intersects(candidate):
                return basin_id
    return None


def copy_lakes(source_layer, target_layer, boundary, basins: dict):
    source_layer.SetSpatialFilter(boundary)
    target_definition = target_layer.GetLayerDefn()
    records = []
    for source in source_layer:
        geometry = clipped_geometry(source.GetGeometryRef(), boundary, "polygon")
        if geometry is None or geometry.GetArea() <= 0:
            continue
        values = {name: field_value(source, name) for name in LAKE_FIELDS}
        values["Hylak_id"] = integer(values["Hylak_id"])
        values["Grand_id"] = integer(values["Grand_id"])
        values["HYBAS_L12"] = basin_for_lake(values, geometry, basins)
        target = ogr.Feature(target_definition)
        set_fields(target, values)
        target.SetGeometry(geometry)
        if target_layer.CreateFeature(target) != ogr.OGRERR_NONE:
            raise RuntimeError("Failed writing lake feature")
        records.append(values)
        target = None
    source_layer.SetSpatialFilter(None)
    return records


def copy_basins(target_layer, boundary, basins: dict):
    """Publish the whole basin reference, clipped to the border.

    Every basin in the selection is written.  The set is not narrowed to what the
    rivers and lakes happen to mention, because that is what left reaches pointing
    at catchments with no polygon.
    """
    records = []
    dropped = []
    definition = target_layer.GetLayerDefn()
    for basin_id in sorted(basins):
        basin = basins[basin_id]
        geometry = clipped_geometry(basin["geometry"], boundary, "polygon")
        if geometry is None:
            dropped.append(basin_id)
            continue
        target = ogr.Feature(definition)
        set_fields(target, basin["values"])
        target.SetGeometry(geometry)
        if target_layer.CreateFeature(target) != ogr.OGRERR_NONE:
            raise RuntimeError(f"Failed writing basin {basin_id}")
        records.append(basin["values"])
        target = None
    if dropped:
        warn(
            "basin-clip-empty",
            f"{len(dropped)} reference basins intersect the boundary but clip to an empty "
            "geometry and were not published",
            count=len(dropped),
            sample=dropped[:10],
        )
    return records


def resolve_basin_links(records, id_field: str, basin_field: str, link_id_name: str,
                       reference_ids: set, kind: str):
    """Join features onto the basin reference, reporting every failure.

    Returns the link rows, each carrying the scope of its basin the way
    ``river_downstream_links`` already carries the scope of its target, so an
    unresolved join survives into the data rather than living only in a log line.
    """
    rows = []
    unresolved = {}
    without_key = []
    for record in records:
        feature_id = integer(record.get(id_field))
        basin_id = integer(record.get(basin_field))
        if basin_id is None:
            without_key.append(feature_id)
            scope = "no_basin_key"
        elif basin_id in reference_ids:
            scope = "resolved"
        else:
            unresolved[basin_id] = unresolved.get(basin_id, 0) + 1
            scope = "outside_reference"
        rows.append({link_id_name: feature_id, "basin_id": basin_id or 0, "basin_scope": scope})
    if without_key:
        warn(
            f"{kind}-basin-no-key",
            f"{len(without_key)} {kind}s carry no basin identifier and could not be joined",
            count=len(without_key),
            sample=without_key[:10],
        )
    if unresolved:
        affected = sum(unresolved.values())
        warn(
            f"{kind}-basin-outside-reference",
            f"{affected} {kind}s reference {len(unresolved)} basin ids that are not in the "
            "basin reference; they are linked with scope outside_reference, not dropped",
            features=affected,
            basins=len(unresolved),
            sample=sorted(unresolved)[:10],
        )
    return rows, {
        "resolved": sum(1 for row in rows if row["basin_scope"] == "resolved"),
        "outsideReference": sum(unresolved.values()),
        "noBasinKey": len(without_key),
        "unresolvedBasinIds": len(unresolved),
    }


def scope_next_down(basin_records, reference_ids: set):
    """Tally how many basins drain to a basin that is outside the reference."""
    tally = {"inside_reference": 0, "terminal": 0, "outside_reference": 0}
    outside = []
    for record in basin_records:
        target = integer(record.get("NEXT_DOWN")) or 0
        if target == 0:
            tally["terminal"] += 1
        elif target in reference_ids:
            tally["inside_reference"] += 1
        else:
            tally["outside_reference"] += 1
            outside.append(integer(record.get("HYBAS_ID")))
    if outside:
        warn(
            "basin-next-down-outside-reference",
            f"{len(outside)} basins drain to a basin outside the reference; the explorer "
            "will show them as terminal nodes",
            count=len(outside),
            sample=outside[:10],
        )
    return tally


def create_attribute_table(dataset, name: str, fields: dict, rows: list[dict]):
    layer = dataset.CreateLayer(name, geom_type=ogr.wkbNone)
    for field_name, field_type in fields.items():
        definition = ogr.FieldDefn(field_name, field_type)
        if field_type == ogr.OFTString:
            definition.SetWidth(32)
        layer.CreateField(definition)
    layer.StartTransaction()
    definition = layer.GetLayerDefn()
    for row in rows:
        feature = ogr.Feature(definition)
        set_fields(feature, row)
        layer.CreateFeature(feature)
        feature = None
    layer.CommitTransaction()


def export_geojson(gpkg: Path, layer: str, target: Path, fields: list[str], simplify: float):
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()
    options = gdal.VectorTranslateOptions(
        options=["-simplify", str(simplify)],
        format="GeoJSON",
        layers=[layer],
        selectFields=fields,
        layerCreationOptions=["RFC7946=YES", "COORDINATE_PRECISION=5"],
    )
    result = gdal.VectorTranslate(str(temporary), str(gpkg), options=options)
    if result is None:
        raise RuntimeError(f"Failed exporting {layer} to {target}")
    result = None
    os.replace(temporary, target)


def rounded(value, digits=3):
    return None if value is None else round(float(value), digits)


def bounds_for_geojson(path: Path):
    dataset = ogr.Open(str(path), 0)
    layer = dataset.GetLayer(0)
    west, east, south, north = layer.GetExtent()
    dataset = None
    return [round(west, 5), round(south, 5), round(east, 5), round(north, 5)]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    # Every input ships inside the delivery folder, so the defaults resolve under
    # --root rather than naming a drive letter that only one workstation has.
    parser.add_argument("--rivers", type=Path, default=None)
    parser.add_argument("--lakes", type=Path, default=None)
    parser.add_argument("--basins", type=Path, default=None,
                        help="GeoPackage holding the level-12 basin reference")
    parser.add_argument("--basin-layer", default="basinatlas_uz_lev12",
                        help="Layer inside --basins to use as the basin reference")
    parser.add_argument("--boundary", type=Path, default=None)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    delivery = root / "earth_engine" / "earth_engine"
    basinatlas = delivery / "uzbekistan_basinatlas_v10"
    river_gdb = resolve_file_gdb((args.rivers or delivery / "HydroRIVERS_v10_as.gdb").resolve())
    lake_gdb = resolve_file_gdb((args.lakes or delivery / "HydroLAKES_polys_v10.gdb").resolve())
    basin_gpkg = (args.basins or basinatlas / "uzbekistan_basinatlas_v10.gpkg").resolve()
    boundary_path = (
        args.boundary or basinatlas / "boundary" / "uzb_admbnda_adm0_2018b_recovered.geojson"
    ).resolve()
    boundary = read_boundary(boundary_path)

    output_dir = root / "storage" / "derived" / "hydrography"
    public_dir = root / "public" / "data" / "hydrography"
    output_dir.mkdir(parents=True, exist_ok=True)
    public_dir.mkdir(parents=True, exist_ok=True)
    gpkg = output_dir / "uzbekistan-hydrography.gpkg"
    temporary_gpkg = gpkg.with_name(gpkg.stem + ".tmp.gpkg")
    if temporary_gpkg.exists():
        temporary_gpkg.unlink()
    driver = ogr.GetDriverByName("GPKG")
    database = driver.CreateDataSource(str(temporary_gpkg))
    if database is None:
        raise RuntimeError(f"Could not create {temporary_gpkg}")

    river_source, river_layer = open_layer(river_gdb, "HydroRIVERS_v10_as")
    lake_source, lake_layer = open_layer(lake_gdb, "HydroLAKES_polys_v10")

    # The reference comes first. Everything after this is joined onto it.
    basins = load_basins(basin_gpkg, args.basin_layer)
    basin_output = create_layer(database, "basins_level12", ogr.wkbMultiPolygon, BASIN_FIELDS)
    basin_output.StartTransaction()
    basin_records = copy_basins(basin_output, boundary, basins)
    basin_output.CommitTransaction()
    reference_ids = {integer(record["HYBAS_ID"]) for record in basin_records}

    river_output = create_layer(database, "rivers_uzbekistan", ogr.wkbMultiLineString, RIVER_FIELDS)
    river_output.StartTransaction()
    river_records = copy_selected_layer(river_layer, river_output, boundary, RIVER_FIELDS, "line")
    river_output.CommitTransaction()

    lake_output = create_layer(
        database,
        "lakes_uzbekistan",
        ogr.wkbMultiPolygon,
        {**LAKE_FIELDS, "HYBAS_L12": ogr.OFTInteger64},
    )
    lake_output.StartTransaction()
    lake_records = copy_lakes(lake_layer, lake_output, boundary, basins)
    lake_output.CommitTransaction()

    river_basin_rows, river_join = resolve_basin_links(
        river_records, "HYRIV_ID", "HYBAS_L12", "river_id", reference_ids, "river")
    lake_basin_rows, lake_join = resolve_basin_links(
        lake_records, "Hylak_id", "HYBAS_L12", "lake_id", reference_ids, "lake")
    basin_routing = scope_next_down(basin_records, reference_ids)

    selected_river_ids = {integer(record["HYRIV_ID"]) for record in river_records}
    downstream_rows = []
    for record in river_records:
        source_id = integer(record["HYRIV_ID"])
        target_id = integer(record.get("NEXT_DOWN")) or 0
        scope = "selected" if target_id in selected_river_ids else "outlet" if target_id == 0 else "outside_selection"
        downstream_rows.append({"source_id": source_id, "target_id": target_id, "target_scope": scope})
    create_attribute_table(
        database,
        "river_downstream_links",
        {"source_id": ogr.OFTInteger64, "target_id": ogr.OFTInteger64, "target_scope": ogr.OFTString},
        downstream_rows,
    )
    create_attribute_table(
        database,
        "river_basin_links",
        {"river_id": ogr.OFTInteger64, "basin_id": ogr.OFTInteger64, "basin_scope": ogr.OFTString},
        river_basin_rows,
    )
    create_attribute_table(
        database,
        "lake_basin_links",
        {"lake_id": ogr.OFTInteger64, "basin_id": ogr.OFTInteger64, "basin_scope": ogr.OFTString},
        lake_basin_rows,
    )
    database = None
    river_source = None
    lake_source = None
    os.replace(temporary_gpkg, gpkg)

    river_geojson = public_dir / "rivers.geojson"
    lake_geojson = public_dir / "lakes.geojson"
    basin_geojson = public_dir / "basins.geojson"
    boundary_geojson = public_dir / "boundary.geojson"
    export_geojson(gpkg, "rivers_uzbekistan", river_geojson, WEB_RIVER_FIELDS, 0.0015)
    export_geojson(gpkg, "lakes_uzbekistan", lake_geojson, WEB_LAKE_FIELDS, 0.0008)
    export_geojson(gpkg, "basins_level12", basin_geojson, WEB_BASIN_FIELDS, 0.003)
    boundary_result = gdal.VectorTranslate(
        str(boundary_geojson.with_suffix(".geojson.tmp")),
        str(boundary_path),
        options=gdal.VectorTranslateOptions(
            format="GeoJSON", layerCreationOptions=["RFC7946=YES", "COORDINATE_PRECISION=5"]
        ),
    )
    if boundary_result is None:
        raise RuntimeError("Failed exporting boundary")
    boundary_result = None
    os.replace(boundary_geojson.with_suffix(".geojson.tmp"), boundary_geojson)

    river_nodes = [
        {
            "id": integer(r["HYRIV_ID"]),
            "nextDown": integer(r.get("NEXT_DOWN")) or 0,
            "mainRiver": integer(r.get("MAIN_RIV")),
            "basinId": integer(r.get("HYBAS_L12")),
            "lengthKm": rounded(r.get("LENGTH_KM")),
            "distanceDownKm": rounded(r.get("DIST_DN_KM")),
            "catchmentKm2": rounded(r.get("CATCH_SKM")),
            "upstreamKm2": rounded(r.get("UPLAND_SKM")),
            "dischargeCms": rounded(r.get("DIS_AV_CMS")),
            "strahlerOrder": integer(r.get("ORD_STRA")),
            "flowOrder": integer(r.get("ORD_FLOW")),
            "endorheic": bool(integer(r.get("ENDORHEIC")) or 0),
        }
        for r in river_records
    ]
    lake_nodes = [
        {
            "id": integer(r["Hylak_id"]),
            "name": (r.get("Lake_name") or "").strip() or None,
            "basinId": integer(r.get("HYBAS_L12")),
            "country": (r.get("Country") or "").strip() or None,
            "lakeType": integer(r.get("Lake_type")),
            "areaKm2": rounded(r.get("Lake_area")),
            "volumeMcm": rounded(r.get("Vol_total")),
            "depthM": rounded(r.get("Depth_avg")),
            "dischargeCms": rounded(r.get("Dis_avg")),
            "elevationM": integer(r.get("Elevation")),
        }
        for r in lake_records
    ]
    basin_nodes = [
        {
            "id": integer(r["HYBAS_ID"]),
            "pfafId": integer(r.get("PFAF_ID")),
            "nextDown": integer(r.get("NEXT_DOWN")) or 0,
            "mainBasin": integer(r.get("MAIN_BAS")),
            "areaKm2": rounded(r.get("SUB_AREA")),
            "upstreamKm2": rounded(r.get("UP_AREA")),
            "uzbekistanKm2": rounded(r.get("UZB_KM2")),
            "uzbekistanPercent": rounded(r.get("UZB_PCT")),
            "endorheic": bool(integer(r.get("ENDO")) or 0),
            "order": integer(r.get("ORDER_")),
            "sourceLayer": r.get("SRC_LAYER"),
        }
        for r in basin_records
    ]
    # Measured integrity of this run. The descriptive counterpart lives under
    # "basinReference" in the manifest; keep the names distinct so the two are
    # never confused for each other.
    integrity = {
        "basinReferencePackage": basinatlas.name,
        "basinReferenceLayer": args.basin_layer,
        "basinsInSelection": len(basins),
        "basinsPublished": len(basin_records),
        "basinNextDown": basin_routing,
        "riverBasinJoin": river_join,
        "lakeBasinJoin": lake_join,
    }
    graph = {
        "version": "1.0",
        "generatedAt": utc_now(),
        "title": "Uzbekistan hydrography relationship graph",
        "sources": {
            "rivers": str(river_gdb),
            "lakes": str(lake_gdb),
            "basins": f"{basin_gpkg} :: {args.basin_layer}",
            "boundary": str(boundary_path),
        },
        "selection": (
            "the BasinATLAS Uzbekistan level-12 selection is the basin reference; "
            "rivers and lakes are joined onto it, and all geometry is clipped to the "
            "Uzbekistan ADM0 boundary"
        ),
        "counts": {
            "rivers": len(river_nodes),
            "lakes": len(lake_nodes),
            "basins": len(basin_nodes),
            "downstreamLinks": len(downstream_rows),
            "riverBasinLinks": len(river_basin_rows),
            "lakeBasinLinks": len(lake_basin_rows),
        },
        "integrity": integrity,
        "warnings": WARNINGS,
        "layers": {
            "rivers": "/data/hydrography/rivers.geojson",
            "lakes": "/data/hydrography/lakes.geojson",
            "basins": "/data/hydrography/basins.geojson",
            "boundary": "/data/hydrography/boundary.geojson",
        },
        "rivers": river_nodes,
        "lakes": lake_nodes,
        "basins": basin_nodes,
    }
    relationships_json = public_dir / "relationships.json"
    atomic_json(relationships_json, graph)
    manifest = {
        "version": "1.0",
        "generatedAt": graph["generatedAt"],
        "source": "HydroSHEDS / BasinATLAS v1.0 / HydroRIVERS v1.0 / HydroLAKES v1.0",
        "license": "HydroSHEDS free data licence",
        "attribution": (
            "HydroSHEDS (Lehner, Grill et al.), BasinATLAS (Linke, Lehner et al.) "
            "and HydroLAKES (Messager et al.)"
        ),
        "selection": graph["selection"],
        "crs": "EPSG:4326",
        "extent": bounds_for_geojson(boundary_geojson),
        "counts": graph["counts"],
        "integrity": integrity,
        "warnings": WARNINGS,
        "sources": graph["sources"],
        "basinReference": {
            "package": basinatlas.name,
            "layer": args.basin_layer,
            "format": "standard HydroBASINS, the format HydroRIVERS HYBAS_L12 keys to",
            "geometry": "whole source polygons, clipped to the border only on publication",
            "attributes": {
                "note": (
                    "The 281 BasinATLAS attributes are not copied into this database. "
                    f"They join on {ATTRIBUTE_JOIN_KEY} against the extraction, which is "
                    "why the reference had to be standard format."
                ),
                "key": ATTRIBUTE_JOIN_KEY,
                "table": f"{basin_gpkg} :: {args.basin_layer}",
                "csv": str(basinatlas / "attributes" / f"{args.basin_layer}.csv"),
                "vocabulary": "ontology/instances/hydroatlas-columns.json",
                "nationalProfile": "ontology/instances/hydroatlas-uz-profile.json",
            },
        },
        "database": {
            "path": str(gpkg),
            "format": "GeoPackage",
            "tables": [
                "rivers_uzbekistan",
                "lakes_uzbekistan",
                "basins_level12",
                "river_downstream_links",
                "river_basin_links",
                "lake_basin_links",
            ],
        },
        "web": {
            "relationships": "/data/hydrography/relationships.json",
            **graph["layers"],
        },
        "fields": {"rivers": WEB_RIVER_FIELDS, "lakes": WEB_LAKE_FIELDS, "basins": WEB_BASIN_FIELDS},
    }
    atomic_json(root / "ontology" / "instances" / "hydrography.json", manifest)
    print(json.dumps(
        {"database": str(gpkg), **graph["counts"], "integrity": integrity,
         "warnings": len(WARNINGS)},
        indent=2,
    ))
    if WARNINGS:
        print(
            f"{len(WARNINGS)} warning(s) recorded in relationships.json and hydrography.json",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
