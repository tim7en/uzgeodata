# Dynamic HydroATLAS pilot

The six-stage implementation programme is published at
`/roadmap.html#implementation-plan` from `ATLAS_MODULES/implementation-plan.json`.
It covers both HydroATLAS and the Uzbekistan environmental atlas, temporal
storage, regional batching, accessible research publication and reviewed
monitoring/ontology outputs. Temporal storage is a prerequisite for new dated
ingestion, not a final-stage addition.

The basin modal has an **Updated substitutes** tab, loaded on demand. Light
green marks a populated substitute for the exact level-12 basin and run,
including valid zeroes. It does not certify recency or accuracy. Other basin
IDs and coarser levels show a pending state; pilot values are not transferred.
Outlined spatial/temporal flags identify proposed research opportunities with
their limitations. `atlas:publish` derives these views from the frozen run into
`PUBLISHED/data/atlas/substitutes/<run_id>/`, with shared definitions and one
value file per basin. These are display projections; the immutable scientific
run and source lock remain the provenance authority.

Open `/dynamic-atlas.html` for the actual Pskem results, all 56 variable-family
crosswalks, native and processing resolutions, periods used, live source checks,
and the update pathway. This inventory covers BasinATLAS attributes on the 20
Pskem level-12 units, not a new RiverATLAS or LakeATLAS product.

## Commands

```powershell
# Rebuild the page's inventory from the saved batch, without Earth Engine.
npm run atlas:publish

# Inspect live Earth Engine assets and sample pilot data; no attribute recomputation.
npm run atlas:audit

# Repeat the saved fixed-period methodology using its cached sources.
python PIPELINES/update_pskem_atlas.py --offline
npm run atlas:publish

# Acquire surrogate sources afresh in an isolated cache directory.
# Original-vintage candidate caches remain pinned; no older source bytes are removed.
python PIPELINES/update_pskem_atlas.py --refresh-sources
npm run atlas:publish
```

`--refresh-sources` and `--offline` are mutually exclusive. Refreshing sources
does not change the hardcoded climatology periods, choose a new annual epoch or
create a monthly time series. It allows moving inventories such as GLIMS and WDPA
to be retrieved again while preserving older evidence. Every batch still has a
new immutable run directory. The live availability audit also retains dated JSON
reports in `PUBLISHED/data/atlas/availability/`.

The audit reports metadata and first-band pixel presence in the pilot bounding
box at a scale of at least 1 km, or intersecting feature counts. It is not a
full-period coverage check, required-band validation or a guarantee that a
future extraction will succeed. Collection timestamps may represent projected
epochs (GHSL), and static assets may have no timestamp. Probe errors remain
visible; offline publishing does not present the older check as a new check.

## Evidence and corrections

The September 9 baseline contains 281 original attributes, 34 independent source
candidates, 196 surrogate attributes and 51 attributes without a new estimate.
There are 3,920 populated surrogate basin-attribute values. Of the 230 attributes
with new estimates, 221 use Earth Engine; nine use local/provider archives.
These counts are computed again from each published batch by the inventory builder.

The saved source lock takes precedence over planning prose: MODIS uses
2003-01-01 through 2022-12-31, not through 2024. TerraClimate and ERA5 runoff use
1991–2020 normals. Glacier and protected-area polygons are painted at 30 m then
aggregated to 15 arc-seconds; lakes use vector intersections. The new page
shows these differences without rewriting the immutable historical package.

The original native resolutions come from the locally parsed HydroATLAS
vocabulary; unresolved original periods remain explicitly unresolved. Catalogue
links accompany every family. The imported reference, candidate and surrogate
units remain distinct. A zero reference is not itself proof that the source
inventory lacked coverage, and numerical agreement is not independent reproduction.

## Proposed time-series storage

Keep geometry in a versioned basin table keyed by HYBAS_ID and geometry version.
Store observations in a long table with:

* HYBAS_ID, geometry version, attribute code, value role (reference/candidate/surrogate).
* Value, physical unit, source asset/release and method version.
* Observation start and exclusive end, epoch type, temporal statistic, provisional flag.
* Native CRS/resolution, analysis CRS/grid, local/upstream spatial support.
* Spatial coverage, valid/expected observation counts, QA status and missing reason.
* Retrieval time, source content hash or snapshot manifest, run ID and revision ID.

Use these dimensions to distinguish observations and append revisions rather
than overwriting the original atlas. Store climatologies with their whole period
and calendar-month statistic; never assign them an observation year from their
download date. Separate units or changed class legends require new method
versions. Source licensing remains attached to the source, not inherited from
the reference atlas.

## Operating pathway

Monthly: check TerraClimate and ERA5-Land availability, append complete months,
and revisit provisional periods. Preserve daily valid-day counts for MODIS snow.
Use station observations for independent validation, particularly for mountain
precipitation and runoff-derived discharge. Discharge from accumulated runoff
lacks routing, reservoir operations and abstractions and is a proxy.

Release-based: keep terrain, soils and ecoregions as versioned static layers;
review population and built-surface epochs when released. Monitor GLIMS revisions
and monthly protected-area releases, retaining feature dates and snapshots.
Archived Copernicus land cover, DMSP and JRC v1.4 summaries do not become current
through repeated downloads.

Candidate atlas adapters (not implemented by this task): Dynamic World land-cover
composites with a reviewed nine-class crosswalk; CHIRPS monthly precipitation;
VIIRS radiance with its own units and cloud counts; JRC monthly water history for
historical change only. Existing project climate services can be reused, but
need the basin support, units and lineage contract above before an atlas join.
No scheduler or production geodatabase migration is installed by this review.

Sources: [HydroATLAS](https://www.hydrosheds.org/hydroatlas),
[TerraClimate](https://developers.google.com/earth-engine/datasets/catalog/IDAHO_EPSCOR_TERRACLIMATE),
[ERA5-Land](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_MONTHLY_AGGR),
[MODIS snow](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MYD10A1),
[Dynamic World](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1),
[CHIRPS](https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY),
[VIIRS](https://developers.google.com/earth-engine/datasets/catalog/NOAA_VIIRS_DNB_MONTHLY_V1_VCMSLCFG),
[JRC monthly water](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_MonthlyHistory),
[GHSL](https://developers.google.com/earth-engine/datasets/catalog/JRC_GHSL_P2023A_GHS_BUILT_S).
