# Pskem original-baseline batch

Run `npm run atlas:pskem` (or `python PIPELINES/update_pskem_atlas.py`).
Use `--offline` with Python to require cached candidate source rasters. Each run
creates a new immutable scientific package, then replaces only the latest-view
JSON. Open `/roadmap.html#pskem-all-attributes` for the live publication.

## Scope and current evidence

Only the 20 Pskem level-12 units are processed, ending at HYBAS_ID 4121289400.
The candidate catchment includes the complete outlet unit; the precise gauge to
reach placement still requires review. The routing table confirms that the pilot
contains all contributing units represented in that table.

Run `pskem-all281-20260909T173021971104Z` imported all 281 original attributes:
5,620 basin-attribute records, 5,611 populated values and 9 original missing values.
Raw numeric precision is preserved from the intact original level-12 geodatabase.
Stored units, physical conversions, spatial support, catalogue citations and
temporal policies accompany each record. Missing values remain missing.

34 attributes were recalculated from source rasters independently of their
reference attribute values. All 30 WorldClim temperature and precipitation
attributes passed the predeclared tolerance in all 20 basins. Elevation mean,
minimum, maximum and upstream mean passed in 15, 1, 0 and 19 basins respectively;
their maximum absolute errors were 10.055, 34, 76.12 and 1.276 metres.
These differences remain visible; tolerances were not widened.

247 attributes still require source-method preparation. Their authoritative atlas
values are available, but their independent reconstruction has not been performed.
For terrain slope and stream gradient, the DEM is already cached; the additional
slope/stream preprocessing and method verification remain to be implemented.
No attribute has passed the independent scientific reproduction release gate.

## Source methods

Elevation follows catalogue P01: mean-aggregate EarthEnv-DEM90 from 3 to 15 arc
seconds, then compute local zonal arithmetic means/extrema. Upstream candidates
combine unique contributing units using additive, latitude-area-weighted sums.
Vector cell-center zones and basin-union upstream support require review against
the original native zone grid and pixel flow accumulation.

Climate uses the Earth Engine `WORLDCLIM/V1/MONTHLY` mirror, with nearest-neighbour
disaggregation onto an aligned 15 arc-second grid and explicit NoData encoding.
Temperature annual means and lowest/highest monthly means derive from the twelve
`tavg` images; precipitation annual totals sum twelve monthly fields. Temporal
reductions occur before basin reductions. Upstream annual means are area weighted.
The mirror's exact equivalence to catalogue WorldClim v1.4 and its period
description remain under review, even though all numerical comparisons passed.

Sources: [BasinATLAS catalogue](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf),
[EarthEnv DEM90](https://www.earthenv.org/DEM.html),
[WorldClim V1 mirror](https://developers.google.com/earth-engine/datasets/catalog/WORLDCLIM_V1_MONTHLY).
Raw-source licences are retained separately from the atlas reference licence.
Original climatologies are not annual observations for 2000–2026.

## Processing time and reproducibility

Full scientific run: **177.076 seconds wall time**. Source and code provenance,
including hashing the complete 5.95 GB original database, took **160.201 seconds**;
elevation preparation **3.896 seconds**, elevation calculations/comparisons
**0.489 seconds**, WorldClim acquisition/preparation **10.156 seconds**, and climate
calculations/comparisons **0.455 seconds**. Setup and export are also included.
Per-attribute times appear in the audit and live page; shared preparation is
counted once. These timings exclude development, research, tests and web builds.
Subsequent offline runs still verify the complete original database.

Each run retains source hashes, the full original database file fingerprint list,
geometry and reference snapshots, code snapshots, Python environment, comparison
tolerances, events and wall/CPU timing. The original acquisition attempt and earlier
single-attribute attempts remain in run history. A repeat run by this operator
would check repeatability; an independent operator and method review are still
required before scientific release.

Exports live under `PUBLISHED/data/atlas/runs/<run_id>/`: `reference-wide.csv`,
`observations.csv`, `attribute-audit.csv`, `pilot-basins.geojson`, `batch.json`,
`source-lock.json`, `manifest.json`, `tolerance.json` and `timing.json`.
The workspace package additionally contains the executed code and native DEM.
The per-attribute registry reports link the implemented recipes to this run.
