# GLIMS glacier outlines for the Amu Darya and Syr Darya formation zones v1

Exact Earth Engine downloads of `GLIMS/20230607`, clipped by intersection with
the `headwater_formation` system polygons:

- `glims-<system>-outlines.geojson`: `line_type == glac_bound`, reduced to the
  latest `src_date` per `glac_id`;
- `glims-<system>-internal-rock.geojson`: `line_type == intrnl_rock` polygons
  that belong to the same glacier and the same survey date as a retained
  outline.

GLIMS is a multi-temporal archive rather than a single-epoch inventory. The raw
collection holds one polygon per survey, so summing it double counts ice: inside
the upper Amu Darya the raw `glac_bound` area is 33,606 km² against 12,342 km²
after keeping the latest survey per glacier. Internal rock outcrops are stored
as separate polygons and must be subtracted before an outline is read as ice.

These files carry native GLIMS identifiers and attribution fields
(`glac_id`, `subm_id`, `anlys_id`, `rc_id`, `src_date`, `anlys_time`). They are
survey-epoch inventory geometry, not a state observation of the current water
year: survey dates in this package range from 1994 to 2009.

Derived tables — the per-glacier inventory, glacier to level-10/level-12
subbasin links, glacier and subbasin elevation-band areas, and the source
attribution register — are written to `PUBLISHED/data/hydroclimate/` by
`npm run headwaters:glaciers`. The published `glaciers-headwaters.geojson` is a
simplified web copy; this directory holds the unsimplified geometry.

Regenerate with `python PIPELINES/build_glacier_inventory.py --refresh-geometry`.
