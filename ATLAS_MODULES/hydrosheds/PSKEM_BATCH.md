# Pskem original-baseline batch

Run `npm run atlas:pskem` (or `python PIPELINES/update_pskem_atlas.py`).
Use `--offline` with Python to require cached candidate and surrogate rasters. Each
run creates a new immutable scientific package, then replaces only the latest-view
JSON. Open `/roadmap.html#pskem-all-attributes` for the live publication.

## Scope and current evidence

Only the 20 Pskem level-12 units are processed, ending at HYBAS_ID 4121289400.
The candidate catchment includes the complete outlet unit; the precise gauge to
reach placement still requires review. The routing table confirms that the pilot
contains all contributing units represented in that table.

Run `pskem-all281-20260909T182641263450Z` imported all 281 original attributes:
5,620 basin-attribute records, 5,611 populated values and 9 original missing values.
Raw numeric precision is preserved from the intact original level-12 geodatabase.
Stored units, physical conversions, spatial support, catalogue citations and
temporal policies accompany each record. Missing values remain missing.

34 attributes were recalculated from original-vintage source rasters, independently
of their reference attribute values. All 30 WorldClim temperature and precipitation
attributes passed the predeclared tolerance in all 20 basins. Elevation mean,
minimum, maximum and upstream mean passed in 15, 1, 0 and 19 basins respectively;
their maximum absolute errors were 10.055, 34, 76.12 and 1.276 metres.
These differences remain visible; tolerances were not widened.

A further 196 attributes now carry an **open-data surrogate estimate**: an
independent value built from a currently retrievable open dataset. A surrogate is
not a reproduction and never replaces the original value; see [SURROGATES.md](SURROGATES.md)
for the fidelity classes and the full policy. 51 attributes still carry neither a
candidate nor a surrogate, and each names the obstacle that blocks it.
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

Surrogates share that 15 arc-second grid and the same upstream support rule.
Seventeen builders cover TerraClimate water balance and moisture indices, MODIS
snow-covered-day climatologies, Horn slope on the native DEM, Copernicus land
cover crosswalked to the GLC2000 legend, BIOME 6000 potential vegetation,
OpenLandMap soils, GPW population, GHSL built surface, DMSP night lights, global
human modification, JRC surface water, GFSAD irrigated cropland, ERA5-Land runoff
and accumulated discharge, GLIMS glaciers, WDPA protected areas, RESOLVE
ecoregions and the local HydroLAKES archive.

Sources: [BasinATLAS catalogue](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf),
[EarthEnv DEM90](https://www.earthenv.org/DEM.html),
[WorldClim V1 mirror](https://developers.google.com/earth-engine/datasets/catalog/WORLDCLIM_V1_MONTHLY).
Every surrogate carries its own provider, release, period and licence in
`surrogate-registry.csv`. Raw-source licences are retained separately from the
atlas reference licence. Original climatologies are not annual observations for
2000–2026, and neither are the surrogate climatologies.

## What the surrogate differences show

174 surrogates are unit-convertible, and 118 of those sit against a non-zero
reference magnitude, so a relative difference is meaningful for them. The
differences are diagnostics, not tests.

Slope is the closest: mean local slope diverges by 0.08 percent of the stored
magnitude, 285.07 against 285 stated in stored units at the outlet unit, from an
independent Horn computation on the same DEM lineage. Monthly snow cover in the
accumulation season, the aridity index, population count and density, protected
area share, lake volume and soil texture all sit within roughly 5 to 25 percent.

Larger divergences are informative rather than defective. Soil organic carbon runs
about eight times the stored value, because OpenLandMap predicts a much larger
stock than SoilGrids1km here and because the atlas depth convention is unresolved.
Late-summer snow, forest cover and inundation diverge by multiples of a near-zero
reference. Glacier cover is the clearest source-vintage finding: the atlas records
zero glacier cover in all 20 units, while the current GLIMS release maps roughly
3.5 percent of the pilot as glacierised, so the 2012 snapshot cited by the atlas
appears to lack Western Tien Shan coverage rather than to disagree about area.

## Processing time and reproducibility

Full scientific run with an empty surrogate cache: **209.562 seconds wall time**,
23.891 seconds CPU. Surrogate stages accounted for 195.539 seconds, of which the
twelve MODIS monthly snow climatologies took 132.942 seconds; every other surrogate
source was acquired in under nine seconds. A rerun against the warm cache completed
the same 281 attributes in **26.489 seconds**. Source and code provenance took
6.773 seconds here; hashing the complete 5.95 GB original database costs
substantially more from cold storage, as an earlier run's 160.201 seconds shows.
Per-attribute times appear in the audit and live page; shared preparation is
counted once. These timings exclude development, research, tests and web builds.

Each run retains source hashes, the full original database file fingerprint list,
geometry and reference snapshots, code snapshots, Python environment, comparison
tolerances, surrogate source records with their crosswalk tables, events and
wall/CPU timing. The original acquisition attempt and earlier single-attribute
attempts remain in run history. A repeat run by this operator would check
repeatability; an independent operator and method review are still required
before scientific release.

Exports live under `PUBLISHED/data/atlas/runs/<run_id>/`: `reference-wide.csv`,
`observations.csv`, `attribute-audit.csv`, `surrogate-registry.csv`,
`pilot-basins.geojson`, `batch.json`, `source-lock.json`, `manifest.json`,
`tolerance.json` and `timing.json`. `observations.csv` carries the surrogate value,
its own unit, its stored-unit equivalent where convertible, and the native and
processing resolutions, so a future geodatabase can keep resolution beside value.
The workspace package additionally contains the executed code and native DEM.
The per-attribute registry reports link the implemented recipes to this run.
