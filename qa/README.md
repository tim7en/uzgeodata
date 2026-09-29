# Scientific QA: first architecture pass

This workspace checks published evidence without invoking ingestion or changing scientific calculations. The audit below is scoped to repository contracts and selected artifacts on 2026-09-29; it is not a complete scientific validation.

## Architecture and data path

| Stage | Observed implementation | QA boundary |
| --- | --- | --- |
| Sources and ingestion | `PIPELINES/` contains Earth Engine, regional climate, topology, station, and case-study scripts. `ATLAS_MODULES/core/observations.py` defines long observation records. `requirements-pipelines.txt` covers heavier GIS/provider dependencies. | Network/provider credentials and untracked raw inputs are required for complete re-extraction; no extraction was run. |
| Published storage | `PUBLISHED/data/atlas/` contains release manifests, a 14-variable Parquet cube, reference catalogue, basin data, model/seasonal outputs and history. `ATLAS_MODULES/core/query.py` and `uzgeodata/` read published products. | Release files use mutable paths. A pinned manifest alone does not preserve old bytes. |
| Browser and API | Vite builds `INTERFACE/` with `PUBLISHED/` as public assets. `worker.js` serves `/data/*` from R2 and other requests from static assets. `server.mjs` is a separate local Node admin/upload service with `/api/*` routes. | The deployed Worker has no Python/admin execution. Do not equate a local admin API test with a public deployment test. |
| Analysis and reports | `ATLAS_MODULES/core/products.py` computes derived products from observations; `core/models.py` and `PIPELINES/` build model outputs. `INTERFACE/` consumes published JSON/cube files and renders downloads/reports. | Request-time computations and report rendering need path-specific tracing; this pass did not exhaustively enumerate them. |
| Existing controls | `tests/` has Python, Node and optional browser scripts. `.github/workflows/ci.yml` runs ontology validation, Node UI tests and launch build. | Full Python suite is omitted from CI due to an existing stale case-study hash. Playwright is not a declared package dependency. |

## Scientific data inventory: verified metadata, not observed coverage

| Product | Version / scope | Temporal and spatial metadata | Provenance and licence gap |
| --- | --- | --- | --- |
| Latest release | `uz-20260924T150158900Z`, `PUBLISHED/data/atlas/latest.json`; release manifest lists 36 files. | Calendar span `2003-01` to `2026-12`; this is not continuous observed coverage. | Manifest declares SHA-256 and byte sizes. Served R2 bytes and immutable retention were not verified. |
| Current cube | `PUBLISHED/data/atlas/cube/index.json`: 14 variables, 7,445 basins, 28,856,820 rows. | Index calendar span `2003-01` to `2026-12`; variable-specific non-null coverage requires inspection. | Local cube index has changed since the pinned release (see check below). Spatial support is basin; native source resolutions vary by product and need source-specific review. |
| Observation store manifest | `PUBLISHED/data/atlas/observations/manifest.json`: 295 attributes, 14 dated attributes, 20 level-12 basins in this particular store. | 29,487,000 dated rows in the manifest; counts are distinct from the public cube scope. | 83 attributes without pinned source; record-level partitions and adapter manifests are needed to audit revisions and missingness. |
| Snow adapter | `observations/dated-snow-manifest.json`: MODIS/061/MYD10A1, 20 basins, years 2003–2022, declared 15 arcsecond processing grid. | Monthly coverage and missingness require record-level audit. | `DATA-LICENSING.md` withdraws snow from trend use pending missing-month investigation. Source licensing must be checked before redistribution. |
| Pskem model | `models/pskem-discharge.json`: gauge-16290, 20 contributing basins; training 2003–2012, evaluation 2013–2017. | Published evaluation uses 59 months; skill figures are claims to independently verify. | Held-out data, baseline and uncertainty need separate audit. |
| Broader catalogue | `PUBLISHED/data/data-catalogue.json`: 190 entries; 55 contain a non-null `license` field, 80 a non-null `temporal` field. | Mixed source-specific spatial/temporal scope. | Null fields must be resolved per dataset; `DATA-LICENSING.md` grants no blanket redistribution licence. |

## Executable check

`qa.release_integrity` streams local bytes and independently compares SHA-256 and size against a pinned release manifest. It produces JSON with `PASS`, `FAIL` or `ERROR`, file-level evidence, and exit code 0 only on `PASS`. It checks byte integrity, not scientific correctness. No third-party dependency is needed.

Local, from repository root:

```powershell
python -m qa.release_integrity --release-id uz-20260924T150158900Z --file catalogue.json --output qa/reports/catalogue-integrity.json
python -m qa.release_integrity --release-id uz-20260924T150158900Z --file cube/index.json --output qa/reports/cube-index-integrity.json
```

CI (Linux shell), after checkout and Python setup; the second command is an intentional release-integrity gate and currently exits 1 until the manifest/bytes discrepancy is resolved through a reviewed release process:

```sh
python -m qa.release_integrity --release-id uz-20260924T150158900Z --file catalogue.json --output qa/reports/catalogue-integrity.json
python -m qa.release_integrity --release-id uz-20260924T150158900Z --file cube/index.json --output qa/reports/cube-index-integrity.json
```

Omit `--file` to check every manifest artifact; that reads all declared files and is deliberately not the default CI example. `qa/reports/` is for local/CI artifacts and should be uploaded by a CI job when used there.

## Prioritized next checks and blockers

1. **P1, FAIL:** Determine whether the current cube index and variable files are intentionally newer than the pinned release. Preserve a byte-identical immutable release snapshot or issue a reviewed new release; do not edit old hashes to silence the check. Compare actual served R2 bytes after a controlled deployment review. The independent reviewer classified the observed local mismatch as P1 in `qa/scientific_review/triage.json`; deployed bytes and scientific values remain unknown.
2. **P0, BLOCKED:** Audit source licenses and missing pinned sources at record level. Requires source agreements/URLs, adapter manifests, and access to raw partitions excluded from Git. Catalogue metadata alone cannot settle redistribution rights.
3. **P1, planned:** Add selected API/browser tests for basin selection, invalid input, and report/export consistency using an explicit local target. Browser dependency and test target must be installed/configured.
4. **P1, planned:** Independent topology and climate calculations on small source-backed fixtures with exact geometry, temporal bounds, units and source hashes. Production outputs must not provide the sole expected values.
5. **P1, planned:** Validate Pskem model against held-out gauge observations, climatology baseline, missingness and uncertainty interval; keep published skill unverified until reproduced.
6. **P2, planned:** Reproduce one accessible paper only after methods, source versions, license and computational budget are recorded. Scientific reviewer then adjudicates claims and retest criteria.

No production data, algorithms, R2 objects, or deployment were changed by this pass.
