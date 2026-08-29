# Uzbekistan BasinATLAS extraction (v1.0)

All BasinATLAS v1.0 basin polygons with a positive-area intersection with
Uzbekistan are included for levels 01-12. Complete basin polygons are retained
rather than clipped. This follows the rules of the companion
`uzbekistan_hydrobasins_lake_v1c` package so the two can be used together.

| Level | Features | UZB overlap (km²) | UZB coverage (%) | Repaired geometries |
|---:|---:|---:|---:|---:|
| 01 | 2 | 450,964.028 | 100.000000 | 2 |
| 02 | 2 | 450,964.028 | 100.000000 | 2 |
| 03 | 4 | 450,964.028 | 100.000000 | 4 |
| 04 | 12 | 450,964.028 | 100.000000 | 3 |
| 05 | 31 | 450,964.028 | 100.000000 | 3 |
| 06 | 92 | 450,964.028 | 100.000000 | 5 |
| 07 | 263 | 450,964.028 | 100.000000 | 9 |
| 08 | 805 | 450,964.028 | 100.000000 | 15 |
| 09 | 1,989 | 450,964.028 | 100.000000 | 22 |
| 10 | 3,608 | 450,964.028 | 100.000000 | 34 |
| 11 | 3,960 | 450,964.028 | 100.000000 | 36 |
| 12 | 3,981 | 450,964.028 | 100.000000 | 36 |

Overlap sums match the national area to eight significant figures at every level,
which is the check that the selection is complete: the basins tile the country.

## Contents and relationships

- `uzbekistan_basinatlas_v10.gpkg`: the boundary, 12 basin layers and the hierarchy, routing and
  summary tables, all in one file.
- `attributes/`: the full 299-column attribute table per level, as CSV.
- `shapefiles/`: the same basins carrying the core HydroBASINS fields only.
- `relationships/pfaf_hierarchy.csv`: logical PFAF parent-child links.
- `relationships/feature_hierarchy_links.csv`: HYBAS links across adjacent levels,
  with `primary_match=1` on the largest overlap.
- `relationships/downstream_links.csv`: native routing IDs, each marked inside or
  outside the national selection.

Native fields are unchanged. Added fields are `SRC_LAYER`, `UZB_KM2` and `UZB_PCT`.
Vector CRS is EPSG:4326 and overlap area uses EPSG:6933.

## What the routing shows

- 13,916 basins are endorheic sinks and 826 drain into one:
  Uzbekistan sits almost entirely inside the Aral Sea endorheic system, so
  only 7 of the selected basins drain to an ocean.
- 840 basins drain to a basin outside the national selection, and 731 are terminal.
  Transboundary flow is the rule here, not the exception.
- Every child basin has exactly one parent (0 straddle a parent boundary). The
  lake-format package reports a handful of split children; the standard format
  nests strictly, so this difference is expected rather than an error.

## Differences from the lake package

- BasinATLAS ships as one global layer set, not regional tiles, so `SRC_TILE`
  becomes `SRC_LAYER` and names the source feature class.
- BasinATLAS has no `LAKE` or `SIDE` fields, so the routing table omits them.
- Shapefiles carry only the core HydroBASINS fields: the format caps attributes at
  255 and field names at 10 characters, and BasinATLAS has
  299. The GeoPackage and `attributes/*.csv` hold every one.
- The geodatabase declares the identifier fields as doubles. They are cast back to
  integers so `HYBAS_ID` reads as `2030065840` rather than `2.03e+09` and joins
  against the relationship tables.

## Area convention

National area is 450,964.028 km² measured in EPSG:6933, against
450,991.181 km² measured geodesically on the WGS84
ellipsoid - a 0.0060% difference. The lake package records
450,941.334 km² for the same boundary. All three are the same
polygon under different area conventions; EPSG:6933 is used here for consistency
with the lake package.

The boundary is the ADM0 polygon recovered for the lake package from the
`uzb_admbnda_adm0_2018b` ArcGIS Feature Service, reused unchanged.

Regenerate with `python scripts/extract_uz_basinatlas.py`.
