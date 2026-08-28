"""Build an Uzbekistan HydroRIVERS/HydroLAKES relationship database.

The canonical local output is a GeoPackage containing clipped river, lake and
level-12 basin geometry plus explicit relationship tables.  Lightweight
GeoJSON and JSON projections are written for the browser explorer.  Run this
with the Python environment shipped with QGIS so ``osgeo`` is available.
"""
from __future__ import annotations

import argparse
import json
import os
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

BASIN_FIELDS = {
    "HYBAS_ID": ogr.OFTInteger64,
    "NEXT_DOWN": ogr.OFTInteger64,
    "MAIN_BAS": ogr.OFTInteger64,
    "PFAF_ID": ogr.OFTInteger64,
    "SUB_AREA": ogr.OFTReal,
    "UP_AREA": ogr.OFTReal,
    "LAKE": ogr.OFTInteger,
    "ENDO": ogr.OFTInteger,
    "ORDER": ogr.OFTInteger,
    "SRC_TILE": ogr.OFTString,
    "UZB_KM2": ogr.OFTReal,
    "UZB_PCT": ogr.OFTReal,
}

WEB_RIVER_FIELDS = list(RIVER_FIELDS)
WEB_LAKE_FIELDS = list(LAKE_FIELDS) + ["HYBAS_L12"]
WEB_BASIN_FIELDS = list(BASIN_FIELDS)


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


def load_basins(path: Path):
    dataset, layer = open_layer(path, "hybas_uz_lev12")
    records = {}
    for feature in layer:
        values = {name: field_value(feature, name) for name in BASIN_FIELDS}
        basin_id = integer(values["HYBAS_ID"])
        values["HYBAS_ID"] = basin_id
        values["NEXT_DOWN"] = integer(values["NEXT_DOWN"])
        values["MAIN_BAS"] = integer(values["MAIN_BAS"])
        values["PFAF_ID"] = integer(values["PFAF_ID"])
        records[basin_id] = {"values": values, "geometry": feature.GetGeometryRef().Clone()}
    dataset = None
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


def copy_basins(target_layer, boundary, basins: dict, selected_ids: set[int]):
    records = []
    definition = target_layer.GetLayerDefn()
    for basin_id in sorted(selected_ids):
        basin = basins.get(basin_id)
        if not basin:
            continue
        geometry = clipped_geometry(basin["geometry"], boundary, "polygon")
        if geometry is None:
            continue
        target = ogr.Feature(definition)
        set_fields(target, basin["values"])
        target.SetGeometry(geometry)
        if target_layer.CreateFeature(target) != ogr.OGRERR_NONE:
            raise RuntimeError("Failed writing basin feature")
        records.append(basin["values"])
        target = None
    return records


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
    parser.add_argument("--rivers", type=Path, default=Path(r"D:\earth_engine\HydroRIVERS_v10_as.gdb"))
    parser.add_argument("--lakes", type=Path, default=Path(r"D:\earth_engine\HydroLAKES_polys_v10.gdb"))
    parser.add_argument(
        "--basins",
        type=Path,
        default=Path(r"C:\earth_engine\uzbekistan_hydrobasins_lake_v1c\uzbekistan_hydrobasins_lake_v1c.gpkg"),
    )
    parser.add_argument(
        "--boundary",
        type=Path,
        default=Path(r"C:\earth_engine\uzbekistan_hydrobasins_lake_v1c\boundary\uzb_admbnda_adm0_2018b_recovered.geojson"),
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    river_gdb = resolve_file_gdb(args.rivers.resolve())
    lake_gdb = resolve_file_gdb(args.lakes.resolve())
    basin_gpkg = args.basins.resolve()
    boundary_path = args.boundary.resolve()
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
    basins = load_basins(basin_gpkg)

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

    selected_basin_ids = {
        integer(record.get("HYBAS_L12"))
        for record in river_records + lake_records
        if integer(record.get("HYBAS_L12"))
    }
    basin_output = create_layer(database, "basins_level12", ogr.wkbMultiPolygon, BASIN_FIELDS)
    basin_output.StartTransaction()
    basin_records = copy_basins(basin_output, boundary, basins, selected_basin_ids)
    basin_output.CommitTransaction()

    selected_river_ids = {integer(record["HYRIV_ID"]) for record in river_records}
    downstream_rows = []
    river_basin_rows = []
    for record in river_records:
        source_id = integer(record["HYRIV_ID"])
        target_id = integer(record.get("NEXT_DOWN")) or 0
        scope = "selected" if target_id in selected_river_ids else "outlet" if target_id == 0 else "outside_selection"
        downstream_rows.append({"source_id": source_id, "target_id": target_id, "target_scope": scope})
        if record.get("HYBAS_L12"):
            river_basin_rows.append({"river_id": source_id, "basin_id": integer(record["HYBAS_L12"])})
    lake_basin_rows = [
        {"lake_id": integer(record["Hylak_id"]), "basin_id": integer(record["HYBAS_L12"])}
        for record in lake_records
        if record.get("HYBAS_L12")
    ]
    create_attribute_table(
        database,
        "river_downstream_links",
        {"source_id": ogr.OFTInteger64, "target_id": ogr.OFTInteger64, "target_scope": ogr.OFTString},
        downstream_rows,
    )
    create_attribute_table(
        database,
        "river_basin_links",
        {"river_id": ogr.OFTInteger64, "basin_id": ogr.OFTInteger64},
        river_basin_rows,
    )
    create_attribute_table(
        database,
        "lake_basin_links",
        {"lake_id": ogr.OFTInteger64, "basin_id": ogr.OFTInteger64},
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
            "sourceTile": r.get("SRC_TILE"),
        }
        for r in basin_records
    ]
    graph = {
        "version": "1.0",
        "generatedAt": utc_now(),
        "title": "Uzbekistan hydrography relationship graph",
        "sources": {
            "rivers": str(river_gdb),
            "lakes": str(lake_gdb),
            "basins": str(basin_gpkg),
            "boundary": str(boundary_path),
        },
        "selection": "geometry clipped to the Uzbekistan ADM0 boundary",
        "counts": {
            "rivers": len(river_nodes),
            "lakes": len(lake_nodes),
            "basins": len(basin_nodes),
            "downstreamLinks": len(downstream_rows),
            "riverBasinLinks": len(river_basin_rows),
            "lakeBasinLinks": len(lake_basin_rows),
        },
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
        "source": "HydroSHEDS / HydroRIVERS v1.0 / HydroLAKES v1.0",
        "license": "HydroSHEDS free data licence",
        "attribution": "HydroSHEDS (Lehner, Grill et al.) and HydroLAKES (Messager et al.)",
        "selection": graph["selection"],
        "crs": "EPSG:4326",
        "extent": bounds_for_geojson(boundary_geojson),
        "counts": graph["counts"],
        "sources": graph["sources"],
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
    print(json.dumps({"database": str(gpkg), **graph["counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
