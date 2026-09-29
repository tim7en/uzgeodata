# Scientific QA research log

This log records what agents actually inspected, executed, and concluded. A proposed task or a generated plan is not evidence of a completed scientific check. All times are UTC. Work is on branch `qa/scientific-research-agents-20260929`.

## Sequence

1. Research Continuity Architect — persistent registry, checkpoints, handoff and resumption.
2. QA Architect & Orchestrator — repository and data inventory, executable QA foundation.
3. Functional QA Engineer — bounded interface and API checks.
4. Independent Data Auditor — topology and numerical checks with independent expectations.
5. Model Validation Scientist — evaluate existing model claims and uncertainty.
6. Scientific Research Replicator — source-backed reproduction feasibility and one bounded study.
7. Independent Scientific Reviewer — evidence review and issue triage.

Agents run in this order so each can use the previous agent's persisted evidence. Scope expands only where actual source data and methods permit it. The Research Backlog examples in the supplied brief are illustrations, not projects already running.

## Entries

### 2026-09-29 12:12 UTC — Initial repository survey (orchestrator)

- **Source:** supplied `Pasted text.txt`, `README.md`, `docs/ARCHITECTURE.md`, `package.json`, `.github/workflows/ci.yml`, `.gitignore`.
- **Observed:** the project has a public Cloudflare Worker/R2 deployment, a local Node admin service, Python ingestion pipelines, a core observation/model layer, and existing Python and Node tests. `WORKSPACE/` is ignored and contains local checkpoints and derived data. The admin update queue persists in `WORKSPACE/data-updates/state.json`; that queue concerns data updates and is not a research registry.
- **Observed limitation:** the existing CI workflow explicitly omits the full Python suite because of a known stale case-study manifest hash. This is a pre-existing test gate gap, not a new test result.
- **Decision:** work in a separate branch; start with research continuity as recommended at the end of the brief. Keep research state separate from published datasets and production calculations.
- **Next:** run the continuity agent, inspect its changes and evidence, then hand off to the QA architect.

### 2026-09-29 12:13 UTC — Snapshot and test-surface check (orchestrator)

- **Source:** `PUBLISHED/data/atlas/latest.json`, `PUBLISHED/data/atlas/observations/manifest.json`, `PUBLISHED/data/atlas/seasonal-forecast/skill.json`, `DATA-LICENSING.md`, `TESTS/`.
- **Observed:** the local default release pointer is `uz-20260924T150158900Z`; its `span` contains 288 calendar positions through 2026-12, which does not imply 288 observed months. The observation manifest identifies 14 dated attributes, 20 basins in that particular observation store, and 83 attributes without pinned sources. These counts have different scopes from the 7,445 basins described in `README.md`.
- **Observed:** the repository has existing browser scripts using Playwright, but Playwright is absent from `package.json` dependencies. `DATA-LICENSING.md` requires source-specific licence checks and warns that snow is withdrawn from trend use pending a missingness investigation.
- **Decision:** the QA agents must pin the exact release, variable, basin, period and source, and must not infer observed coverage from calendar slots. Browser execution depends on a usable local Playwright installation; absence should be recorded as a blocker for those checks.
- **Environment check:** Python `playwright` imports in this workspace; Node `playwright` is absent. Browser binaries and actual launch are not yet checked.
- **Baseline execution:** `python -m pytest TESTS/test_basin_api_selection.py -q` passed (5 tests); `node --test TESTS/test_assessment_model.mjs` passed (4 tests). These are existing scoped tests, not scientific validation of the full release.

### 2026-09-29 12:15 UTC — Research Continuity Architect, first pass

- **Artifacts:** `qa/continuity/` and `tests/test_research_continuity.py`.
- **Implemented:** local JSON research registry, task transitions and dependencies, ownership separation for approval and validation, atomic state writes with an exclusive lock, SHA-256 evidence checkpoints, handoff, memory, status and resume CLI.
- **Executed by orchestrator:** `python -m pytest TESTS/test_research_continuity.py -q` (4 passed); `python -m qa.continuity --help` (exit 0). `TESTS` resolves to `tests` on this case-insensitive filesystem.
- **Limitations:** the climate calculation interruption-and-resumption acceptance scenario has not run. The CLI does not execute jobs or enforce its declared network, download, time and storage limits. No scheduler is installed. Continuity is therefore a tested foundation, not a claim that autonomous research is working end to end.
- **Next:** QA architect will inventory the actual repository and make QA commands and machine-readable results concrete.

### 2026-09-29 12:19 UTC — QA Architect, first pass

- **Artifacts:** `qa/README.md`, `qa/release_integrity.py`, `qa/reports/catalogue-integrity.json`, `qa/reports/cube-index-integrity.json`.
- **Implemented:** scoped architecture and six-product data inventory, prioritized checks and blockers, and a CLI producing JSON byte-integrity results from a pinned release manifest.
- **Executed:** `catalogue.json` matched release `uz-20260924T150158900Z` (PASS, exit 0). Orchestrator reran `python -m qa.release_integrity --release-id uz-20260924T150158900Z --file cube/index.json`: FAIL, exit 1. Manifest states 17,212 bytes and SHA-256 `6f3c36818ef1e2108994e4a6958c8d87af6857fff0f6cfd59e39a7bd6edc8d6c`; local file is 17,435 bytes and SHA-256 `08a51a3ce4fcd8f7525cdb5164b6a48d9d7e3da630e14e9bdc909c5c4f2a18b2`.
- **Interpretation:** the local cube index does not match the pinned manifest. The reason and currently served R2 bytes remain unverified; do not alter the old manifest or assume which copy is authoritative.
- **Next:** functional agent will check a bounded user path and report separate interface and data findings.

### 2026-09-29 12:23 UTC — Functional QA, first pass

- **Artifacts:** `qa/functional/check_first_pass.py`, `REPORT.md`, `results.json`, `selection.png`, and captured CSV/JSON exports.
- **Target and method:** local Vite on `127.0.0.1:5175`, Python Playwright with Chromium, one small map AOI. No production API load.
- **Results:** 23 level-12 basins selected (PASS); CSV IDs and river systems matched the local basin index (PASS); JSON IDs and AOI polygon preserved (PASS); browser page errors absent on this path (PASS). Invalid coordinates, PDF, other variables, mobile and failure handling were NOT TESTED.
- **Failure:** local Everything JSON export had top-level `release: null` although `attribute_meta` was present. The local `/release.json` was unavailable; `AoiTool.jsx` converts that fetch failure to null. Agent test exited 1. Whether a deployed build supplies the metadata remains unverified.
- **Interpretation:** IDs agreeing across local browser and exports establish consistency of that path, not independent basin or scientific accuracy.
- **Next:** independently examine a source-backed data case and quantify any mismatch.

### 2026-09-29 12:25 UTC — Independent Data Auditor, first pass

- **Artifacts:** `qa/data_audit/check_syr_darya_level07.py`, `REPORT.md`, `results.json`.
- **Source and scope:** local GeoJSON export of `WWF/HydroATLAS/v1/Basins/level07`, generated 2026-09-08; upper Syr Darya outlet `HYBAS_ID=4070425650`, `MAIN_BAS=4070050240`. The source export SHA-256 matched its local manifest. This is static topology, not a climate time series.
- **Independent method:** reverse traversal of native `NEXT_DOWN` edges and sum of native `SUB_AREA`; production basin builder was not imported.
- **Executed by orchestrator:** `python qa/data_audit/check_syr_darya_level07.py` exited 0. Reconstructed 35 upstream units out of 177 source units; exact published membership match, no cycle or broken path. Source area sum 95,297.6 km² versus native outlet `UP_AREA` 95,297.0 km², an absolute difference of 0.6 km² within the 1.8 km² field-rounding bound.
- **Limitations:** the source is a local GEE export, not a separately downloaded original HydroBASINS shapefile. Geodesic area, other basins and climate rasters were not checked; licence terms for this export are not pinned.
- **Next:** model validator will inspect an actual held-out model claim and its baseline.

### 2026-09-29 12:29 UTC — Model Validation Scientist, first pass

- **Artifacts:** `qa/model_validation/check_pskem.py`, `REPORT.md`, `results.json`.
- **Executed by orchestrator:** `python qa/model_validation/check_pskem.py` exited 0. Refit on 2003-01–2012-12 (120 months); held-out 2013-01–2017-12 (59 valid months). February 2015 was excluded for an invalid gauge day count.
- **Results:** the published coefficients and held-out metrics were reproduced at printed precision. Model bias +13.984, MAE 28.014, RMSE 35.834 mm/month; training-month climatology RMSE 19.278 mm/month. Nash–Sutcliffe versus evaluation mean is +0.550 while squared-error skill versus training-month climatology is −2.455. These use different reference baselines; the published artifact already reports the negative climatology skill.
- **Interpretation and limits:** same-month climate predictors support a retrospective reconstruction, not a demonstrated prospective discharge forecast. No predictive interval is published, so interval coverage is untestable. The check independently refits and scores, but observation row selection still uses the repository query view, so this is not a fully independent source-data rebuild.
- **Next:** a research replicator will identify a full accessible paper and determine whether one result can be reproduced with legally available inputs.

### 2026-09-29 12:31 UTC — Scientific Research Replicator, first pass

- **Artifacts:** `qa/replication/REPORT.md`, `literature.json`.
- **Primary sources inspected:** Siegfried et al. (2024), DOI [10.1007/s10584-024-03799-y](https://doi.org/10.1007/s10584-024-03799-y), full publisher text; author archive DOI [10.5281/zenodo.10125163](https://doi.org/10.5281/zenodo.10125163). The publisher reports 221 mountain catchments, a 1979–2011 modeled baseline and a −2.7% modeled discharge change in 2071–2100 under SSP5-8.5.
- **Status:** numerical replication **BLOCKED / NOT ASSESSABLE**. The listed 2.5 GB input archive was not downloaded, checksum-verified or inspected within this bounded pass. No numerical match or discrepancy is claimed.
- **Comparability:** the paper's catchments, baseline, climate forcing and future scenario differ from the UZGEODATA public historical record; direct numerical comparison requires a matched design.
- **Next:** independent reviewer will classify the four preceding findings and set evidence-based retest criteria.

### 2026-09-29 12:35 UTC — Independent Scientific Reviewer, first pass

- **Artifacts:** `qa/scientific_review/REPORT.md`, `triage.json` (six findings with evidence, alternatives, impact and retest criteria).
- **Repeated checks:** read-only release integrity returned catalogue PASS and cube index FAIL; topology audit returned PASS (35 units, 0.6 km² difference). Arithmetic on saved model scores confirmed squared-error ratio 3.45533 and skill −2.45533. Reviewer verified that `PUBLISHED/release.json` is absent while `dist/release.json` exists.
- **Triage:** SR-01 local release-integrity mismatch is a confirmed P1 defect in the checkout; SR-02 local development AOI export lacking release metadata is a confirmed P2 functional defect. SR-03 Pskem's poor seasonal-baseline skill is a disclosed methodological limitation, not an undisclosed model bug. SR-04 and SR-05 are missing validation and replication evidence; SR-06 records the limited scope of passing topology and functional checks.
- **Boundary:** deployed bytes, deployed export behavior, all-basin geometry, climate raster aggregation, prospective forecast skill and full paper replication remain unverified. The reviewer did not certify the portal as a whole.
- **Next:** seed a persistent proposed-task backlog from the triage, run final checks and prepare the branch for review.

### 2026-09-29 12:37 UTC — Persistent backlog and final local checks (orchestrator)

- **Artifacts:** `qa/seed_research_backlog.py`, `qa/research_state/registry.json`, `qa/research_state/README.md`. Six findings SR-01 through SR-06 are stored as `PROPOSED`, with next actions and hashed evidence. No follow-up task was marked approved or completed.
- **Executed:** `python -m qa.seed_research_backlog` twice; the second run left the six-task registry unchanged. A fresh `python -m qa.continuity --store qa/research_state --workspace . status` process read the persisted state. `python -m pytest TESTS/test_research_continuity.py TESTS/test_basin_api_selection.py -q` passed (9 tests). `python -m compileall -q qa` passed. All 9 JSON files under `qa/` parsed successfully.
- **Boundary:** reading the backlog from a new process verifies durable storage, not the requested full agent interruption-and-resumption climate experiment. The latter remains open. No scheduled agent process is running after this session.

### 2026-09-29 12:37 UTC — Review handoff (orchestrator)

- **Version control:** committed the first-pass QA workspace on `qa/scientific-research-agents-20260929` as `71358e652` and pushed the branch to `origin`.
- **Review:** opened [draft pull request #2](https://github.com/tim7en/uzgeodata/pull/2) against `main`. It presents the evidence and known failures for review; no merge or deployment was performed.

### 2026-09-29 12:47 UTC — Release provenance deep dive (agent follow-up)

- **Artifacts:** `qa/deep_dive/release/probe.py`, `evidence.json`, `REPORT.md`.
- **Executed:** four bounded public GETs over verified Windows Schannel HTTPS; all returned 200. Local Git history and published manifest were compared. The September 24 index, with its original CRLF line endings, matches the pinned manifest exactly. Commit `d9e3d917d` replaced the index on September 28 without a new atlas release pointer. The public pointer still names September 24, while the public cube index semantically matches the September 28 rebuild (28,856,820 rows versus 27,874,080 in the pinned release).
- **Conclusion:** the served fixed cube-index path and the public release pointer describe different dataset states. Scientific values and the served Parquet partitions were not independently verified. The site's leaf certificate is valid; an Anaconda Python certificate-chain failure on this machine does not establish a portal-wide TLS fault.
- **Next:** inspect built and deployed user-facing provenance and a broader functional workflow before recommending portal changes.

### 2026-09-29 12:52 UTC — Functional provenance follow-up

- **Artifacts:** `qa/deep_dive/functional/REPORT.md`, `scenarios.json`.
- **Observed:** local Vite development returned HTML fallback for `/release.json`, explaining `release: null` in its AOI Everything export. The existing built preview and public endpoint returned JSON at `/release.json`, but that object identifies a frontend build commit, while `/data/atlas/latest.json` identifies the scientific atlas release. A successful public browser export was not tested.
- **Executed:** the documented `tests/test_workflow_browser.py` suite stopped at its first English-labelled finder assertion; separate browser inspection saw Russian UI. Its later mobile, empty-state and retry cases did not run. The existing `dist` preview lacks local data assets and cannot complete an AOI export. Three bounded public metadata GETs passed over verified HTTPS.
- **Interpretation:** a frontend commit in the export does not pin the dataset, especially while the atlas release pointer and cube index diverge. The UI suite failure shows a test/language-state problem at its entry point; it does not establish failure of later user journeys.
- **Next:** independently recalculate one climate value from available source material and assess scientific coverage.

### 2026-09-29 12:56 UTC — One basin-month climate extraction

- **Artifacts:** `qa/deep_dive/climate/check_one_basin.py`, `result.json`, `README.md`.
- **Source and scope:** local 24-band ERA5-Land-derived GeoTIFF for 2003, a separate level-12 basin polygon `4121272730` in the Syr Darya system, and January 2003 published continuation rows. Input file SHA-256 hashes are recorded in `result.json`.
- **Executed by orchestrator:** `python qa/deep_dive/climate/check_one_basin.py` returned `PASS`. Independent Shapely cell intersections over 8 cells gave 0.7926014603 °C and 25.5709638122 mm, agreeing with published values to numerical precision under a predeclared 0.01-unit tolerance. Geodesic-area sensitivity was −0.000016 °C and −0.000159 mm.
- **Boundary:** this validates one local raster-to-basin extraction, not the upstream Earth Engine export, other months or basins, TerraClimate v1.1, model skill, or field truth. The GeoTIFF itself has no embedded source checksum or band labels; the acquisition manifest remains important.
- **Next:** independently review these deeper results and recommend the next portal changes with explicit acceptance criteria.

### 2026-09-29 12:59 UTC — Portal recommendation review

- **Artifact:** `qa/deep_dive/PORTAL_RECOMMENDATIONS.md` with five ranked changes and acceptance criteria.
- **Independent synthesis:** prioritize a coherent immutable atlas release, explicit frontend and dataset identities in exports, a complete language-aware browser gate, visible validation scope and model limits, then a broader independent science sample across both river systems.
- **Claims retained as unverified:** served Parquet bytes, public AOI export behavior, downstream browser scenarios, upstream provider-cell fidelity, all-basin accuracy and prospective discharge forecasting. The valid portal leaf certificate is not a site TLS defect; the local Anaconda Python trust-chain failure is client-specific.
