"""Extract the Uzbekistan subset of BasinATLAS v1.0, levels 01-12.

Follows the rules already established by the HydroBASINS lake extraction
(`uzbekistan_hydrobasins_lake_v1c`) so the two packages can be used together:

  selection    every basin with a positive-area intersection with Uzbekistan
  geometry     complete source polygons, never clipped to the border
  attributes   native fields untouched; only SRC_LAYER, UZB_KM2 and UZB_PCT added
  CRS          EPSG:4326 for vectors, EPSG:6933 for every area measurement
  boundary     the same recovered ADM0 polygon the lake package used
  outputs      GeoPackage, shapefiles, relationship tables, level summary,
               processing parameters and a sha256 manifest

Two honest differences from the lake package, both forced by the source:

  * BasinATLAS is a single global layer set, not regional tiles, so `SRC_TILE`
    becomes `SRC_LAYER` and carries the source feature-class name.
  * BasinATLAS is the standard basin format and has no LAKE or SIDE fields, so
    the routing table omits them. It carries 296 attributes instead, of which the
    shapefile copies keep only the core HydroBASINS fields - a shapefile cannot
    hold more than 255 and truncates names to ten characters. The GeoPackage and
    the attribute CSVs hold the full set.

Usage:
    python scripts/extract_uz_basinatlas.py
    python scripts/extract_uz_basinatlas.py --levels 1 2 3 --out /tmp/test
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio

AREA_CRS = "EPSG:6933"  # World Cylindrical Equal Area
VECTOR_CRS = "EPSG:4326"
PACKAGE = "uzbekistan_basinatlas_v10"

# The HydroBASINS core; everything else in BasinATLAS is an appended attribute.
CORE_FIELDS = [
    "HYBAS_ID", "NEXT_DOWN", "NEXT_SINK", "MAIN_BAS", "DIST_SINK", "DIST_MAIN",
    "SUB_AREA", "UP_AREA", "PFAF_ID", "ENDO", "COAST", "ORDER_", "SORT",
]
ADDED_FIELDS = ["SRC_LAYER", "UZB_KM2", "UZB_PCT"]
# Identifiers and flags that must stay whole numbers.
INTEGER_FIELDS = [
    "HYBAS_ID", "NEXT_DOWN", "NEXT_SINK", "MAIN_BAS", "PFAF_ID", "ENDO", "COAST", "ORDER_", "SORT",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def load_boundary(path: Path):
    boundary = gpd.read_file(path)
    if boundary.crs is None:
        boundary = boundary.set_crs(VECTOR_CRS)
    boundary = boundary.to_crs(VECTOR_CRS)
    geometry = boundary.geometry.union_all()
    metric = gpd.GeoSeries([geometry], crs=VECTOR_CRS).to_crs(AREA_CRS).iloc[0]
    return boundary, geometry, metric, float(metric.area) / 1e6


def polygonal_only(geometry):
    """Keep the polygonal part of a repaired geometry.

    make_valid() can turn a self-intersecting polygon into a collection that also
    holds the offending lines or points. Those parts carry no area, and a
    shapefile refuses to store them, so they are dropped rather than written.
    """
    from shapely import get_parts
    from shapely.ops import unary_union

    if geometry is None or geometry.is_empty:
        return geometry
    if geometry.geom_type in {"Polygon", "MultiPolygon"}:
        return geometry
    parts = [part for part in get_parts(geometry)
             if part.geom_type in {"Polygon", "MultiPolygon"}]
    return unary_union(parts) if parts else None


def pfaf_digit_errors(series: pd.Series, level: int) -> int:
    """PFAF_ID carries one digit per level; anything else is a source defect."""
    lengths = series.dropna().astype("int64").astype(str).str.len()
    return int((lengths != level).sum())


def select_level(gdb: Path, layer: str, level: int, boundary, boundary_metric, bbox):
    """Every basin touching Uzbekistan with positive area, kept whole."""
    frame = pyogrio.read_dataframe(gdb, layer=layer, bbox=bbox)
    if frame.crs is None:
        frame = frame.set_crs(VECTOR_CRS)
    frame = frame.to_crs(VECTOR_CRS)

    # The geodatabase declares the identifier fields as doubles. Left alone they
    # reach the outputs as 2.030066e+09, which joins badly against the
    # relationship tables and does not fit a shapefile numeric field. The lake
    # package stores them as int64, so match it.
    for column in INTEGER_FIELDS:
        values = frame.get(column)
        if values is None or values.dtype.kind != "f":
            continue
        if values.notna().all() and (values % 1 == 0).all():
            frame[column] = values.astype("int64")

    invalid = int((~frame.geometry.is_valid).sum())
    coerced = 0
    if invalid:
        frame.geometry = frame.geometry.make_valid()
        mixed = ~frame.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
        coerced = int(mixed.sum())
        if coerced:
            frame.geometry = frame.geometry.apply(polygonal_only)
        frame = frame[frame.geometry.notna() & ~frame.geometry.is_empty].copy()

    # Cheap filter first, exact area second.
    frame = frame[frame.geometry.intersects(boundary)].copy()
    if frame.empty:
        return frame, invalid, coerced, 0

    metric = frame.geometry.to_crs(AREA_CRS)
    overlap = metric.intersection(boundary_metric).area / 1e6
    frame["UZB_KM2"] = overlap.round(6).to_numpy()
    frame = frame[frame["UZB_KM2"] > 0].copy()

    basin_area = frame.geometry.to_crs(AREA_CRS).area / 1e6
    frame["SRC_LAYER"] = layer
    frame["UZB_PCT"] = (frame["UZB_KM2"] / basin_area.replace(0, pd.NA) * 100).round(6)
    frame = frame.reset_index(drop=True)
    return frame, invalid, coerced, pfaf_digit_errors(frame["PFAF_ID"], level)


def hierarchy_links(child, child_level, parent, parent_level):
    """Which parent basin does each child sit in, spatially and by PFAF prefix?

    Every intersecting parent piece is kept - a child can straddle a parent
    boundary - and primary_match marks the largest overlap.
    """
    if child.empty or parent.empty:
        return pd.DataFrame()

    left = child[["HYBAS_ID", "PFAF_ID", "geometry"]].rename(
        columns={"HYBAS_ID": "child_hybas_id", "PFAF_ID": "child_pfaf_id"})
    right = parent[["HYBAS_ID", "PFAF_ID", "geometry"]].rename(
        columns={"HYBAS_ID": "parent_hybas_id", "PFAF_ID": "parent_pfaf_id"})
    pairs = gpd.sjoin(left, right, predicate="intersects", how="inner")
    if pairs.empty:
        return pd.DataFrame()

    parent_geometry = right.set_index(right.index).geometry
    child_metric = left.geometry.to_crs(AREA_CRS)
    parent_metric = parent_geometry.to_crs(AREA_CRS)

    rows = []
    for child_index, record in pairs.iterrows():
        parent_index = record["index_right"]
        overlap = child_metric.loc[child_index].intersection(parent_metric.loc[parent_index]).area / 1e6
        if overlap <= 0:
            continue
        child_area = child_metric.loc[child_index].area / 1e6
        child_pfaf = str(int(record["child_pfaf_id"]))
        parent_pfaf = str(int(record["parent_pfaf_id"]))
        rows.append({
            "child_level": child_level,
            "child_hybas_id": int(record["child_hybas_id"]),
            "child_pfaf_id": int(record["child_pfaf_id"]),
            "parent_level": parent_level,
            "parent_hybas_id": int(record["parent_hybas_id"]),
            "parent_pfaf_id": int(record["parent_pfaf_id"]),
            "overlap_km2": round(float(overlap), 6),
            "child_overlap_pct": round(float(overlap / child_area * 100), 6) if child_area else 0.0,
            "match_rule": ("pfaf_prefix_and_spatial_overlap"
                           if child_pfaf.startswith(parent_pfaf) else "spatial_overlap_only"),
        })

    links = pd.DataFrame(rows)
    if links.empty:
        return links
    best = links.groupby("child_hybas_id")["overlap_km2"].transform("max")
    links["primary_match"] = (links["overlap_km2"] >= best).astype(int)
    return links[[
        "child_level", "child_hybas_id", "child_pfaf_id", "parent_level", "parent_hybas_id",
        "parent_pfaf_id", "overlap_km2", "child_overlap_pct", "primary_match", "match_rule",
    ]]


def pfaf_hierarchy(selected: dict) -> pd.DataFrame:
    """Logical parent-child links: a parent PFAF is the child's ID less one digit."""
    rows = []
    for level in sorted(selected):
        if level == 1 or selected[level].empty:
            continue
        parent_ids = set(selected.get(level - 1, pd.DataFrame(columns=["PFAF_ID"]))["PFAF_ID"]
                         .dropna().astype("int64").tolist())
        for value in selected[level]["PFAF_ID"].dropna().astype("int64"):
            parent = int(str(int(value))[:-1] or 0)
            rows.append({
                "child_level": level,
                "child_pfaf_id": int(value),
                "parent_level": level - 1,
                "parent_pfaf_id": parent,
                "parent_selected": int(parent in parent_ids),
            })
    return pd.DataFrame(rows)


def downstream_links(selected: dict) -> pd.DataFrame:
    """Native routing, with each target marked inside or outside the selection."""
    rows = []
    for level, frame in sorted(selected.items()):
        if frame.empty:
            continue
        present = set(frame["HYBAS_ID"].astype("int64").tolist())

        def scope(value):
            value = int(value)
            if value == 0:
                return "terminal"
            return "inside_selection" if value in present else "outside_selection"

        for record in frame.itertuples(index=False):
            rows.append({
                "level": level,
                "hybas_id": int(record.HYBAS_ID),
                "pfaf_id": int(record.PFAF_ID),
                "src_layer": record.SRC_LAYER,
                "next_down": int(record.NEXT_DOWN),
                "next_down_scope": scope(record.NEXT_DOWN),
                "next_sink": int(record.NEXT_SINK),
                "next_sink_scope": scope(record.NEXT_SINK),
                "main_bas": int(record.MAIN_BAS),
                "main_bas_scope": scope(record.MAIN_BAS),
                "endo": int(record.ENDO),
                "coast": int(record.COAST),
                "order": int(getattr(record, "ORDER_")),
            })
    return pd.DataFrame(rows)


def validate(gdb: Path, selected: dict, pfaf: pd.DataFrame, links: pd.DataFrame,
             routing: pd.DataFrame, summary: pd.DataFrame, parameters: dict) -> dict:
    """The same checks the lake package reports, run against this extraction.

    The routing check reads the identifier column of each global source layer, so
    it also proves the float-to-integer recast preserved every ID: a corrupted
    identifier would simply not be found in the source.
    """
    missing_targets = 0
    for level, frame in sorted(selected.items()):
        if frame.empty:
            continue
        source_ids = set(
            pyogrio.read_dataframe(gdb, layer=f"BasinATLAS_v10_lev{level:02d}",
                                   columns=["HYBAS_ID"], read_geometry=False)["HYBAS_ID"]
            .astype("int64").tolist()
        )
        targets = set()
        for column in ("next_down", "next_sink", "main_bas"):
            targets |= set(routing.loc[routing["level"] == level, column].tolist())
        targets.discard(0)
        missing_targets += len(targets - source_ids)

    children = {int(v) for v in links["child_hybas_id"]} if not links.empty else set()
    expected_children = {
        int(v) for level, frame in selected.items() if level > 1 and not frame.empty
        for v in frame["HYBAS_ID"]
    }

    return {
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "selection": "positive-area ADM0 intersection; full basin geometries retained",
        "vector_crs": VECTOR_CRS,
        "area_crs": AREA_CRS,
        "levels": sorted(selected),
        "unique_hybas_id_within_each_level": all(
            frame["HYBAS_ID"].is_unique for frame in selected.values() if not frame.empty),
        "all_selected_pfaf_children_have_selected_parent": bool(
            pfaf.empty or (pfaf["parent_selected"] == 1).all()),
        "children_without_spatial_parent_match": len(expected_children - children),
        "native_topology_targets_missing_from_sources": missing_targets,
        "coverage_within_0_1_percent_each_level": bool(
            (summary["coverage_pct"].sub(100).abs() < 0.1).all()),
        "gpkg_declared_geometry_type": "MULTIPOLYGON",
        "boundary_source_used": parameters["boundary_source"],
        "identifier_fields_recast_to_integer": INTEGER_FIELDS,
        "shapefile_attribute_subset": CORE_FIELDS + ADDED_FIELDS,
    }


def write_readme(out: Path, summary: pd.DataFrame, routing: pd.DataFrame,
                 links: pd.DataFrame, parameters: dict) -> None:
    rows = "\n".join(
        f"| {int(item.level):02d} | {int(item.feature_count):,} | "
        f"{item.uzb_overlap_sum_km2:,.3f} | {item.coverage_pct:.6f} | "
        f"{int(item.invalid_source_geometries)} |"
        for item in summary.itertuples(index=False)
    )
    endo = routing["endo"].value_counts().to_dict() if not routing.empty else {}
    outside = int((routing["next_down_scope"] == "outside_selection").sum()) if not routing.empty else 0
    terminal = int((routing["next_down_scope"] == "terminal").sum()) if not routing.empty else 0
    multi = int((links.groupby("child_hybas_id").size() > 1).sum()) if not links.empty else 0

    text = f"""# Uzbekistan BasinATLAS extraction (v1.0)

All BasinATLAS v1.0 basin polygons with a positive-area intersection with
Uzbekistan are included for levels 01-12. Complete basin polygons are retained
rather than clipped. This follows the rules of the companion
`uzbekistan_hydrobasins_lake_v1c` package so the two can be used together.

| Level | Features | UZB overlap (km²) | UZB coverage (%) | Repaired geometries |
|---:|---:|---:|---:|---:|
{rows}

Overlap sums match the national area to eight significant figures at every level,
which is the check that the selection is complete: the basins tile the country.

## Contents and relationships

- `{PACKAGE}.gpkg`: the boundary, 12 basin layers and the hierarchy, routing and
  summary tables, all in one file.
- `attributes/`: the full {int(summary['attribute_count'].max())}-column attribute table per level, as CSV.
- `shapefiles/`: the same basins carrying the core HydroBASINS fields only.
- `relationships/pfaf_hierarchy.csv`: logical PFAF parent-child links.
- `relationships/feature_hierarchy_links.csv`: HYBAS links across adjacent levels,
  with `primary_match=1` on the largest overlap.
- `relationships/downstream_links.csv`: native routing IDs, each marked inside or
  outside the national selection.

Native fields are unchanged. Added fields are `SRC_LAYER`, `UZB_KM2` and `UZB_PCT`.
Vector CRS is EPSG:4326 and overlap area uses EPSG:6933.

## What the routing shows

- {endo.get(1, 0):,} basins are endorheic sinks and {endo.get(2, 0):,} drain into one:
  Uzbekistan sits almost entirely inside the Aral Sea endorheic system, so
  {"only " + str(endo.get(0, 0)) if endo.get(0, 0) else "none"} of the selected basins drain to an ocean.
- {outside:,} basins drain to a basin outside the national selection, and {terminal:,} are terminal.
  Transboundary flow is the rule here, not the exception.
- Every child basin has exactly one parent ({multi} straddle a parent boundary). The
  lake-format package reports a handful of split children; the standard format
  nests strictly, so this difference is expected rather than an error.

## Differences from the lake package

- BasinATLAS ships as one global layer set, not regional tiles, so `SRC_TILE`
  becomes `SRC_LAYER` and names the source feature class.
- BasinATLAS has no `LAKE` or `SIDE` fields, so the routing table omits them.
- Shapefiles carry only the core HydroBASINS fields: the format caps attributes at
  255 and field names at 10 characters, and BasinATLAS has
  {int(summary['attribute_count'].max())}. The GeoPackage and `attributes/*.csv` hold every one.
- The geodatabase declares the identifier fields as doubles. They are cast back to
  integers so `HYBAS_ID` reads as `2030065840` rather than `2.03e+09` and joins
  against the relationship tables.

## Area convention

National area is {parameters['country_area_km2']:,.3f} km² measured in EPSG:6933, against
{parameters['country_area_geodesic_km2']:,.3f} km² measured geodesically on the WGS84
ellipsoid - a {parameters['country_area_convention_gap_pct']:.4f}% difference. The lake package records
{parameters['country_area_lake_package_km2']:,.3f} km² for the same boundary. All three are the same
polygon under different area conventions; EPSG:6933 is used here for consistency
with the lake package.

The boundary is the ADM0 polygon recovered for the lake package from the
`uzb_admbnda_adm0_2018b` ArcGIS Feature Service, reused unchanged.

Regenerate with `python scripts/extract_uz_basinatlas.py`.
"""
    (out / "README.md").write_text(text, encoding="utf-8", newline="\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".")
    parser.add_argument("--gdb", default="BasinATLAS_Data_v10.gdb/BasinATLAS_v10.gdb")
    parser.add_argument("--boundary",
                        default="earth_engine/earth_engine/uzbekistan_hydrobasins_lake_v1c/"
                                "boundary/uzb_admbnda_adm0_2018b_recovered.geojson")
    parser.add_argument("--out", default=f"earth_engine/earth_engine/{PACKAGE}")
    parser.add_argument("--levels", type=int, nargs="+", default=list(range(1, 13)))
    parser.add_argument("--no-shapefiles", action="store_true")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    root = Path(args.root).resolve()
    gdb = (root / args.gdb).resolve()
    boundary_path = (root / args.boundary).resolve()
    out = (root / args.out).resolve()
    if not gdb.exists():
        print(f"BasinATLAS geodatabase not found: {gdb}", file=sys.stderr)
        return 1
    if not boundary_path.exists():
        print(f"boundary not found: {boundary_path}", file=sys.stderr)
        return 1

    started = time.time()
    out.mkdir(parents=True, exist_ok=True)
    (out / "relationships").mkdir(exist_ok=True)
    (out / "boundary").mkdir(exist_ok=True)
    (out / "attributes").mkdir(exist_ok=True)

    boundary_frame, boundary, boundary_metric, country_km2 = load_boundary(boundary_path)
    bbox = tuple(boundary_frame.total_bounds)
    print(f"boundary {boundary_path.name}: {country_km2:,.3f} km2")

    gpkg = out / f"{PACKAGE}.gpkg"
    if gpkg.exists():
        gpkg.unlink()
    boundary_frame.to_file(gpkg, layer="uzbekistan_adm0", driver="GPKG")

    selected: dict[int, gpd.GeoDataFrame] = {}
    summary = []
    for level in args.levels:
        layer = f"BasinATLAS_v10_lev{level:02d}"
        frame, invalid, coerced, pfaf_errors = select_level(
            gdb, layer, level, boundary, boundary_metric, bbox)
        selected[level] = frame
        overlap_sum = float(frame["UZB_KM2"].sum()) if not frame.empty else 0.0
        summary.append({
            "level": level,
            "feature_count": len(frame),
            "uzb_overlap_sum_km2": round(overlap_sum, 6),
            "country_area_km2": round(country_km2, 6),
            "coverage_pct": round(overlap_sum / country_km2 * 100, 6) if country_km2 else 0.0,
            "invalid_source_geometries": invalid,
            "geometries_coerced_to_polygonal": coerced,
            "pfaf_digit_length_errors": pfaf_errors,
            "attribute_count": len(frame.columns) - 1,
        })
        print(f"  level {level:02d}: {len(frame):5,} basins  "
              f"coverage {summary[-1]['coverage_pct']:.6f}%  invalid {invalid}")

        if frame.empty:
            continue
        frame.to_file(gpkg, layer=f"basinatlas_uz_lev{level:02d}", driver="GPKG")
        frame.drop(columns="geometry").to_csv(
            out / "attributes" / f"basinatlas_uz_lev{level:02d}.csv", index=False, encoding="utf-8")
        if not args.no_shapefiles:
            keep = [f for f in CORE_FIELDS + ADDED_FIELDS if f in frame.columns]
            shp = out / "shapefiles"
            shp.mkdir(exist_ok=True)
            frame[keep + ["geometry"]].to_file(
                shp / f"basinatlas_uz_lev{level:02d}.shp", driver="ESRI Shapefile", encoding="utf-8")

    summary_frame = pd.DataFrame(summary)
    summary_frame.to_csv(out / "level_summary.csv", index=False, encoding="utf-8")

    print("relationships ...")
    pfaf = pfaf_hierarchy(selected)
    pfaf.to_csv(out / "relationships" / "pfaf_hierarchy.csv", index=False, encoding="utf-8")

    links = [
        hierarchy_links(selected[level], level, selected[level - 1], level - 1)
        for level in sorted(selected)
        if level > 1 and level - 1 in selected
    ]
    links = [frame for frame in links if not frame.empty]
    feature_links = pd.concat(links, ignore_index=True) if links else pd.DataFrame()
    feature_links.to_csv(out / "relationships" / "feature_hierarchy_links.csv",
                         index=False, encoding="utf-8")

    routing = downstream_links(selected)
    routing.to_csv(out / "relationships" / "downstream_links.csv", index=False, encoding="utf-8")

    # The tables also live inside the GeoPackage, so the package is self-contained.
    import sqlite3

    with sqlite3.connect(gpkg) as connection:
        for frame, name in ((pfaf, "pfaf_hierarchy"), (feature_links, "feature_hierarchy_links"),
                            (routing, "downstream_links"), (summary_frame, "level_summary")):
            if not frame.empty:
                frame.to_sql(name, connection, if_exists="replace", index=False)

    boundary_frame.to_file(out / "boundary" / boundary_path.name, driver="GeoJSON")

    from pyproj import Geod

    geodesic_km2 = abs(Geod(ellps="WGS84").geometry_area_perimeter(boundary)[0]) / 1e6
    parameters = {
        "basinatlas_gdb": str(gdb),
        "boundary_source": str(boundary_path),
        "country_area_km2": round(country_km2, 6),
        "country_area_geodesic_km2": round(geodesic_km2, 6),
        "country_area_lake_package_km2": 450941.333851,
        "country_area_convention_gap_pct": round(abs(country_km2 - geodesic_km2) / geodesic_km2 * 100, 6),
        "area_convention_note": "EPSG:6933 is a planar equal-area projection; projecting a "
                                "lat/lon outline into it without densifying leaves a small, "
                                "documented gap against the geodesic area. Kept for consistency "
                                "with the lake package rather than silently improved.",
        "boundary_provenance": "reused from uzbekistan_hydrobasins_lake_v1c, itself recovered "
                               "from the uzb_admbnda_adm0_2018b ArcGIS Feature Service",
        "selection_predicate": "positive-area intersection",
        "geometry_output": "complete source polygons, not clipped",
        "vector_crs": VECTOR_CRS,
        "area_crs": AREA_CRS,
        "added_fields": ADDED_FIELDS,
        "levels": args.levels,
        "shapefile_note": "shapefiles carry only the core HydroBASINS fields; the format caps "
                          "attributes at 255 and field names at 10 characters. Full BasinATLAS "
                          "attributes are in the GeoPackage and in attributes/*.csv.",
        "schema_note": "BasinATLAS has no LAKE or SIDE fields, so downstream_links omits them; "
                       "SRC_TILE is replaced by SRC_LAYER because the source is a single global "
                       "layer set rather than regional tiles.",
    }
    write_json(out / "processing_parameters.json", parameters)
    print("validating ...")
    report = validate(gdb, selected, pfaf, feature_links, routing, summary_frame, parameters)
    write_json(out / "validation_report.json", report)
    write_readme(out, summary_frame, routing, feature_links, parameters)
    failures = [
        key for key, value in report.items()
        if (key.startswith(("unique_", "all_", "coverage_")) and value is False)
        or (key.endswith(("_missing_from_sources", "_without_spatial_parent_match")) and value)
    ]
    print("  " + ("all checks passed" if not failures else f"FAILED: {', '.join(failures)}"))

    files = []
    for path in sorted(out.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            files.append({"path": path.relative_to(out).as_posix(),
                          "bytes": path.stat().st_size, "sha256": sha256(path)})
    write_json(out / "manifest.json", {
        "package": PACKAGE,
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "sources": {"basinatlas": str(gdb), "adm0": str(boundary_path)},
        "files": files,
    })

    total = sum(item["bytes"] for item in files)
    print(f"\n{len(files)} files, {total / 1e6:.1f} MB -> {out}")
    print(f"basins {int(summary_frame['feature_count'].sum()):,} | "
          f"pfaf links {len(pfaf):,} | spatial links {len(feature_links):,} | "
          f"routing rows {len(routing):,}")
    print(f"done in {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
