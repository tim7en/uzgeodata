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
| `INTERFACE/` | The browser application — React sources, stylesheets, and the three page entry points. This is Vite's root. |
| `PUBLISHED/` | Files the browser fetches, served at `/`. `data/` is a public URL namespace, so it stays lowercase. |
| `GEODATA/` | Source deliveries: the HydroSHEDS and BasinATLAS geodatabases and the Uzbekistan extractions taken from them. Subfolders keep their package names because manifests and licences reference them. |
| `WORKSPACE/` | Derived data, uploads and the private dataset registry. Not in version control. |
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
```

`ontology:build` needs only the standard library. The geospatial pipelines need
`geopandas`, `rasterio` and `py7zr`; `ontology:validate` and the tests need
`jsonschema` and `pytest`.
