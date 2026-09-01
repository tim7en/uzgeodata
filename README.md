# UzGeoData

Environmental geodata for Uzbekistan: the 134-package national environmental
atlas, the HydroSHEDS hydrography extracted to the national boundary, and a
stored ontology that says what every dataset is and how it relates to the rest.

## Layout

Each top-level folder is named for the kind of information it holds.

| Folder | What lives here |
| --- | --- |
| `ONTOLOGY/` | The knowledge graph: JSON Schema in `schema/`, controlled vocabularies in `vocab/`, the built graph and pipeline manifests in `instances/`. See [ONTOLOGY/README.md](ONTOLOGY/README.md). |
| `PIPELINES/` | Every build and analysis script. `ontology/` projects the registries into the graph; the rest extract, convert and measure geodata. |
| `INTERFACE/` | The browser application — React sources, stylesheets, and the four page entry points. This is Vite's root. |
| `PUBLISHED/` | Files the browser fetches, served at `/`. `data/` is a public URL namespace, so it stays lowercase. |
| `GEODATA/` | Source deliveries: the HydroSHEDS and BasinATLAS geodatabases and the Uzbekistan extractions taken from them. Subfolders keep their package names because manifests and licences reference them. |
| `WORKSPACE/` | Derived data, uploads and the private dataset registry. Not in version control. `ontology:build` reads it, and without it the rebuilt graph loses roughly a third of its records — do not run that pipeline in a checkout that lacks it. |
| `TESTS/` | The ontology and converter test suites. |

`dist/` is Vite's build output and `node_modules/` is npm's; both are tool-owned
and left as they are.

## Running it

```bash
npm install
npm run dev            # portal at http://localhost:5173
npm run build          # static build into dist/
```

The data pipelines are Python and run independently of the web app:

```bash
npm run ontology:build         # rebuild the graph from the registries
npm run ontology:validate      # schema, integrity and ML guard rails
npm run test:ontology          # the guard-rail tests
npm run hydrography:build      # river, lake and basin reference (needs GDAL)
npm run hydrography:atlaslinks # overlay atlas vectors onto basins
npm run hydrography:zonalstats # read atlas rasters per basin
npm run hydrography:attributes # publish the 281 BasinATLAS attributes per basin
npm run hydrography:adminlinks # overlay provinces and districts onto the basins
npm run catalogue:build        # pivot the graph into the dataset catalogue
npm run data:groups            # group every data reference and check what is on this machine
npm run data:items             # name every reference inside those groups, present or not
npm run review:build           # export every held layer to GeoJSON and index it for review
npm run landcover:stats        # annual land cover area per district or basin, from Earth Engine
npm run cfsv2:observe          # basin monthly state from CFSv2 (measurement)
npm run cfsv2:climatology      # the reference baseline the anomalies are measured against
npm run cfsv2:anomaly          # observations as z-scores, classified
npm run chirps:observe         # pentadal basin precipitation from CHIRPS v3 (canonical rainfall)
npm run data:currency          # how current every stored relationship is, and what refreshes it
npm run ontology:structure     # file the datasets by domain, numbered and sorted (--apply to move)
npm run ontology:audit         # check every table against the conventions the ontology settled on
npm run test:trace             # the upstream-trace and aggregation guard rails
```

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

## The pages

| Page | What it does |
| --- | --- |
| `/` | The portal SPA. |
| `/hydrography.html` | Rivers, lakes and sub-basins on a map. Selecting anything traces the catchment upstream of it, reads the BasinATLAS attributes for the traced set, and names the provinces and districts that drain to it, weighted by the area each contributes. A reach traces through the river network first, so what is reported is what lies above that reach rather than above the whole basin it sits in. |
| `/relationships.html` | The stored facts themselves, as sortable and exportable tables. |
| `/review.html` | Every layer the project holds, one at a time on a map, with its extent, geometry type and a sample of every attribute column. Stepping with the arrows walks the whole set; the fill percentage next to each field is what shows a column that carries nothing. |
| `/catalogue.html` | Opens with the data groups — every kind of data the project references, under a short code, with its status checked against the working copy. Below that, every dataset the graph describes: what it measures, where it came from, and whether this checkout can actually open it. Availability is checked against the filesystem, not taken from the recorded URL. |
