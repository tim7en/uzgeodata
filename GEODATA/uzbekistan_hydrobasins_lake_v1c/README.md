# Uzbekistan HydroBASINS lake extraction (v1.c)

All HydroBASINS lake-format polygons with a positive-area intersection with Uzbekistan are included for levels 01-12. Complete basin polygons are retained rather than clipped.

| Level | Features | EU | AS | UZB coverage (%) |
|---:|---:|---:|---:|---:|
| 01 | 2 | 1 | 1 | 100.000000 |
| 02 | 2 | 1 | 1 | 100.000000 |
| 03 | 4 | 2 | 2 | 99.999935 |
| 04 | 13 | 3 | 10 | 99.999932 |
| 05 | 34 | 8 | 26 | 99.999928 |
| 06 | 87 | 11 | 76 | 99.999915 |
| 07 | 255 | 46 | 209 | 99.999909 |
| 08 | 843 | 150 | 693 | 99.999886 |
| 09 | 2039 | 374 | 1665 | 99.999888 |
| 10 | 3643 | 632 | 3011 | 99.999891 |
| 11 | 4125 | 716 | 3409 | 99.999891 |
| 12 | 4147 | 720 | 3427 | 99.999890 |

## Contents and relationships

- `uzbekistan_hydrobasins_lake_v1c.gpkg`: the boundary, 12 basin layers, and hierarchy/routing/summary tables.
- `shapefiles/`: equivalent boundary and basin shapefiles.
- `relationships/pfaf_hierarchy.csv`: logical PFAF parent-child links.
- `relationships/feature_hierarchy_links.csv`: HYBAS links across adjacent levels; all spatial parent pieces are retained for lake/side splits and `primary_match=1` identifies the largest overlap.
- `relationships/downstream_links.csv`: native routing IDs and whether each target is inside or outside the national selection.

Native fields are unchanged. Added fields are `SRC_TILE`, `UZB_KM2`, and `UZB_PCT`. An `outside_selection` routing target exists in the source but does not overlap Uzbekistan. Vector CRS is EPSG:4326 and overlap area uses EPSG:6933. The GeoPackage wraps Polygon records as MultiPolygon for standards compliance; coordinates and attributes are unchanged, while shapefiles preserve the original geometry record types.

The locally listed ADM0 files returned Windows `STATUS_IN_PAGE_ERROR`; the identically named `uzb_admbnda_adm0_2018b` boundary was recovered from its ArcGIS Feature Service. The exact retrieved GeoJSON and URL are included.

## Storage note

The verified package is stored at `C:\earth_engine\uzbekistan_hydrobasins_lake_v1c`. Attempts to copy it to `D:` failed repeatedly with Windows error 433, so the partial `D:` folders must not be used.
