# Development reference (legacy pipeline inventory)

For the current public preview, use the [launch README](../README.md). Historical
coverage claims below describe earlier pipeline milestones; consult release.json
for the deployed snapshot.

# UzGeoData

Environmental geodata for Uzbekistan: the 134-package national environmental
atlas, the HydroSHEDS hydrography extracted to the national boundary, and a
stored ontology that says what every dataset is and how it relates to the rest.

The hydroclimate expansion is transboundary. Natural runoff formation is
selected upstream from declared control sections and kept separate from the
managed allocation network and from administrative reporting overlays. See
[HYDROCLIMATE_REFACTOR_PLAN.md](../HYDROCLIMATE_REFACTOR_PLAN.md).

## Layout

The Pskem Earth Engine / HydroATLAS review is at `/dynamic-atlas.html`: saved
basin values, thematic crosswalks, native and temporal resolutions, live source
availability and refresh policies. Run `npm run atlas:audit` for a new live
availability check, or `npm run atlas:publish` to rebuild from saved evidence.
See [dynamic atlas methods](../ATLAS_MODULES/hydrosheds/DYNAMIC_ATLAS.md).

The [six-stage implementation plan](../ATLAS_MODULES/implementation-plan.json) is
visible at `/roadmap.html#implementation-plan`. Basin modals expose an **Updated
substitutes** tab with light-green available values, explicit pending basins,
and future spatial/temporal resolution flags. Regional runtime figures are
labelled projections; dated monthly updates need a representative batch benchmark.

Basin values are staged into an append-only observation store at
`PUBLISHED/data/atlas/observations/` by `npm run atlas:observations`. The contract
is [core/observations.py](../ATLAS_MODULES/core/observations.py), the executable form
of the long table in [core/REPRODUCIBILITY.md](../ATLAS_MODULES/core/REPRODUCIBILITY.md):
every row carries its source release, method, geometry and QA denominators, a
correction supersedes rather than overwrites, and no observation year is invented
for a static value or a climatology.

The first dated family is monthly MODIS snow cover for the pilot basins, 2003-2022
(`npm run atlas:dated-snow`). `npm run atlas:benchmark` measures a regional batch on
the real 7,445-basin frame rather than extrapolating one: the grouped reduction in
[core/zonal.py](../ATLAS_MODULES/core/zonal.py) replaced a per-basin scan and is about
405 times faster, and server-side acquisition returns basin values without
downloading a raster.

The dated series now covers the region: 1,786,800 monthly snow observations for all
7,445 basins, 2003-2022, in 2.25 hours (`npm run atlas:regional-snow`, resumable
from checkpoints). Read the
[run ledger](../PUBLISHED/data/atlas/observations/regional-snow-ledger.json) before
using it. It publishes two limitations with the data: basin support is uneven,
and source availability is not stable across the record, so a trend taken from
this series without accounting for null months may be a trend in the imagery.

Five more dated variables followed from TerraClimate and ERA5-Land
(`npm run atlas:regional-monthly <source>`), so six now cover the region for
2003-2022: 10,725,600 dated rows in total. The store's bulk partitions are derived data,
regenerable from the run checkpoints, and are deliberately not tracked in git; the
ledgers and provenance tables beside them are.

Each top-level folder is named for the kind of information it holds.

| Folder | What lives here |
| --- | --- |
| `ONTOLOGY/` | The knowledge graph: JSON Schema in `schema/`, controlled vocabularies in `vocab/`, the built graph and pipeline manifests in `instances/`. See [ONTOLOGY/README.md](../ONTOLOGY/README.md). |
| `PIPELINES/` | Every build and analysis script. `ontology/` projects the registries into the graph; the rest extract, convert and measure geodata. |
| `INTERFACE/` | Browser pages, React sources and styles. `features/case-studies/` holds reusable evidence views and charts. This is Vite's root. |
| `PUBLISHED/` | Files the browser fetches, served at `/`. `data/` is a public URL namespace, so it stays lowercase. |
| `GEODATA/` | Source deliveries: the HydroSHEDS and BasinATLAS geodatabases and the Uzbekistan extractions taken from them. Subfolders keep their package names because manifests and licences reference them. |
| `WORKSPACE/` | Derived data, uploads and the private dataset registry. Not in version control. `ontology:build` reads it, and without it the rebuilt graph loses roughly a third of its records — do not run that pipeline in a checkout that lacks it. |
| `TESTS/` | The ontology and converter test suites. |
| `storage/` | Original station, gauge, climate, soil-temperature and glacier deliveries; unchanged for provenance. |
| `CASE_STUDIES/` | Protocols and methodology; results remain in `PUBLISHED/data/case-studies/`. |

See [hydromet modules](../PIPELINES/hydromet/README.md) and the implemented
[regional station–satellite study](../CASE_STUDIES/regional-station-environment.md),
available at `/case-studies.html#regional-study` alongside Chirchik/Pskem.

`dist/` is Vite's build output and `node_modules/` is npm's; both are tool-owned
and left as they are.

## Running it

```bash
npm install
npm run dev            # portal at http://localhost:5173
npm run build          # static build into dist/
```

The front-page research navigation now leads only to the case-study directory
at `/case-studies.html`. Individual studies retain deep links
`#chirchik-study` and `#regional-study`; other research tools remain accessible
at their existing URLs.

`npm run build` first runs `cases:publish`: it verifies current model scores
against the daily CSV and regenerates the study cards, chart JSON and figures.
This build step requires Python with NumPy and Matplotlib (`python -m pip install
numpy matplotlib`) and the published study inputs. It does not refit models or
contact Earth Engine. A deployment serving the resulting `dist/` needs no Python
runtime. `npm run cases:publish` refreshes the presentation without a full build;
`npm run casestudy:dailymodel` refits and then republishes it.
On Windows, stop the development server before rebuilding if it holds a
generated JSON file open; restart afterward. Publication remains atomic and
never truncates a live file to bypass a reader lock.

Browser checks: `python TESTS/study_landing_browser.py`; set `STUDY_TEST_URL` to
test another local deployment. Guardrails: `python -m pytest
TESTS/test_study_landing.py -q`.

The data pipelines are Python and run independently of the web app:

```bash
npm run ontology:build         # rebuild the graph from the registries
npm run ontology:earth-engine  # refresh remote EE sources without the private registry
npm run ontology:semantics     # refresh lexical facts without the private registry
npm run ontology:validate      # schema, integrity and ML guard rails
npm run test:ontology          # the guard-rail tests
npm run hydrography:build      # river, lake and basin reference (needs GDAL)
npm run hydrography:atlaslinks # overlay atlas vectors onto basins
npm run hydrography:zonalstats # read atlas rasters per basin
npm run hydrography:attributes # publish the 281 BasinATLAS attributes per basin
npm run hydrography:adminlinks # overlay provinces and districts onto the basins
npm run hydrography:align-basins # publish the canonical BasinATLAS level-12 frame
npm run headwaters:basins       # download/trace upper Amu and Syr headwater basins
npm run basins:transboundary    # full Amu/Syr natural systems at levels 7, 10 and 12
npm run basins:waterbodies      # lakes and reservoirs of the whole Amu/Syr systems
npm run basins:waterbody-review # native dam/lake links, nearby candidates and name/property audit
npm run basins:dams             # Global Dam Watch barriers, with basin/reach/lake links
npm run basins:wastewater       # HydroWASTE plants and the dilution factor below each
npm run rivers:condition        # GloRiC reach types and free-flowing connectivity status
npm run stations:pskem          # Pskem/Oygaing/Tashkent workbooks into station series
npm run cases:build             # observed-data analysis and six Chirchik case studies
npm run cases:forcing           # historical ERA5/CHIRPS station cells (needs EE auth)
npm run cases:figures           # export observation figure as PNG and vector PDF
npm run cases:update            # refresh EE inputs and rebuild extended studies
npm run cases:models            # physical, random-forest and Bayesian hindcasts
npm run cases:figures:validation # scientific atlas, cited report and workbook
npm run test:cases              # scientific validation and QC guard rails
npm run headwaters:elevation    # SRTM elevation-band areas inside headwaters
npm run headwaters:era5         # append every newly available ERA5-Land month
npm run headwaters:era5:elevation # the same monthly fields by elevation band
npm run headwaters:anomaly     # fixed 1991-2020 anomaly baseline for upstream basins
npm run headwaters:snow         # append native-daily MODIS snow by elevation band
npm run headwaters:update       # refresh upstream observations, anomalies and web projection
npm run catalogue:build        # pivot the graph into the dataset catalogue
npm run data:groups            # group every data reference and check what is on this machine
npm run data:items             # name every reference inside those groups, present or not
npm run review:build           # export every held layer to GeoJSON and index it for review
npm run landcover:stats        # annual land cover area per district or basin, from Earth Engine
npm run landcover:web          # compact the basin land-cover table into browser JSON
npm run cfsv2:observe          # basin monthly state from CFSv2 (measurement)
npm run cfsv2:climatology      # the reference baseline the anomalies are measured against
npm run cfsv2:anomaly          # observations as z-scores, classified
npm run chirps:observe         # pentadal basin precipitation from CHIRPS v3 (canonical rainfall)
npm run data:currency          # how current every stored relationship is, and what refreshes it
npm run ontology:structure     # file the datasets by domain, numbered and sorted (--apply to move)
npm run ontology:audit         # check every table against the conventions the ontology settled on
npm run test:trace             # the upstream-trace and aggregation guard rails
npm test                       # all Python/Node tests plus the production web build
```

Install the tested base environment with `python -m pip install -r requirements.txt`;
use `requirements-pipelines.txt` for the full GIS and Earth Engine toolchain.
`ontology:build` needs only the standard library, and so do
`hydrography:attributes` and `catalogue:build` — a GeoPackage is a SQLite
database, so the attribute table is read with `sqlite3` rather than GDAL.
`hydrography:adminlinks` needs `pyshp`, `shapely` and `pyproj`, which is the
whole of what a shapefile overlay takes and a good deal less than the full stack.
The land cover pipelines need `earthengine-api` and an authenticated session:
run `earthengine authenticate --project ee-sabitovty` once, in a terminal with a
browser, because Earth Engine mints its token through a sign-in that cannot be
scripted. A token from an OAuth client still in testing status lasts seven days.
`landcover:cog` needs no Earth Engine at all — it reads the same product from its
open Cloud-Optimised GeoTIFF mirror, and is the cross-check on the Earth Engine
numbers.
The remaining geospatial pipelines need `geopandas`, `rasterio` and `py7zr`;
`ontology:validate` and the Python tests need `jsonschema` and `pytest`.
`test:trace` runs on Node's built-in test runner and needs nothing extra.

The full ontology build fails fast when `WORKSPACE/datasets.json` is absent,
because a partial rebuild would erase private-source records. The scoped
`ontology:earth-engine` command safely refreshes Earth Engine declarations and
the public graph projections without requiring that private registry.

## The pages

| Page | What it does |
| --- | --- |
| `/` | The portal SPA. |
| `/hydrography.html` | Rivers, lakes and sub-basins on a map. Selecting anything traces the catchment upstream of it, reads the BasinATLAS attributes for the traced set, and names the provinces and districts that drain to it, weighted by the area each contributes. A reach traces through the river network first, so what is reported is what lies above that reach rather than above the whole basin it sits in. |
| `/landcover.html` | An ontology-driven basin observatory: annual Esri land-cover area, share, dominant class and change rendered as a reactive BasinATLAS map with temporal and spatial charts, table rows and JSON evidence. |
| `/climate.html` | The same reactive map generalized across every other already-measured basin table: CFSv2 climate state and anomaly, CHIRPS precipitation, CHIRTS and CPC temperature, CAMS air quality, and GHM human modification. One time slider, one choropleth per basin level (6, 7 or 12), colour by raw value or, where a baseline exists, by anomaly z-score. `npm run climate:web` rebuilds its projection from `PIPELINES/build_basin_layers_web.py`. |
| `/relationships.html` | The stored facts themselves, as sortable and exportable tables. |
| `/case-studies.html` | Chirchik–Charvak validation, MODIS snow, 10 m land cover, elevation and energy profiles, physical/ML/Bayesian models, a readiness bar, scientific figures and supporting workbook. |
| `/review.html` | Every layer the project holds, one at a time on a map, with its extent, geometry type and a sample of every attribute column. Stepping with the arrows walks the whole set; the fill percentage next to each field is what shows a column that carries nothing. |
| `/catalogue.html` | Opens with the data groups — every kind of data the project references, under a short code, with its status checked against the working copy. Below that, every dataset the graph describes: what it measures, where it came from, and whether this checkout can actually open it. Availability is checked against the filesystem, not taken from the recorded URL. |

## Living atlas programme

The [atlas module workspace](../ATLAS_MODULES/README.md) defines the HydroSHEDS
methodology, 281 attribute recipes and mandatory scientific reproduction gates.
Open `/roadmap.html` for the visual roadmap, project updates and 2000–2026 history
planning. Run `npm run atlas:publish` to refresh its data after specification or
news changes; development startup and production builds also publish it.
