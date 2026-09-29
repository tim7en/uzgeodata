# Portal recommendations from the scientific QA follow-up

Date: 2026-09-29 UTC. This is an evidence-ranked review of the public preview, not a certification of its full dataset. Evidence comes from the [research log](../../docs/SCIENTIFIC_QA_RESEARCH_LOG.md), [release probe](release/REPORT.md), [functional probe](functional/REPORT.md), [climate extraction](climate/README.md), and [first-pass triage](../scientific_review/triage.json).

## What a reader can trust today

| Claim | Evidence | Appropriate portal wording |
| --- | --- | --- |
| The site is reachable and serves frontend, catalogue, pointer and cube-index JSON | Four bounded public GETs with Windows Schannel certificate verification; three more metadata GETs in the functional follow-up | "Public preview is accessible." Do not infer that every download or browser workflow succeeds. The site's leaf certificate was valid during the probe; one Python CA bundle's chain error does not establish a live TLS fault. |
| One upper Syr Darya level-7 routing set | Independent reverse traversal found exactly the published 35 source units; area difference 0.6 km² is within a 1.8 km² rounding bound | "This sampled topology case passed." It is not an all-basin geometry certificate. |
| One January 2003 ERA5-Land-derived extraction for level-12 basin `4121272730` | Independent eight-cell polygon overlay reproduced temperature and precipitation to < 1e-12 against a 0.01-unit tolerance | "This local raster-to-basin calculation reproduced." The local GeoTIFF is an Earth Engine transformed export, without embedded upstream asset checksum or band labels. It does not validate the original ERA data or the entire climate cube. |
| The Pskem model's published scores | Independent refit and scoring reproduced the reported 59-month holdout metrics | "Historical, same-month reconstruction evaluated for one catchment." Its RMSE was 35.834 versus 19.278 mm/month for training-month climatology; it has no demonstrated prospective forecast skill or predictive interval. |
| A local AOI selection/export path | One Playwright run matched 23 selected level-12 IDs across UI, CSV and JSON | "This sampled selection/export path was internally consistent." The sources share project data, so this is not independent geographic validation. Its Everything JSON lacked release metadata in Vite development. |

## Changes in priority order

### 1. Restore a coherent, citable atlas release before promoting more data

**Immediate release blocker.** The public `latest.json` still names `uz-20260924T150158900Z`, whose manifest records 27,874,080 cube rows. The served fixed-path cube index describes the September 28 rebuild with 28,856,820 rows. The old manifest has not been invalidated as a record of its original index; the September 24 index with CRLF line endings matches its recorded hash. Served Parquet partition bytes and scientific values have not been checked. The design permits R2 fixed-key replacement independently of pointer promotion.

Choose one complete dataset state, verify every indexed object and its source version, publish it under release-qualified immutable keys, then promote the default pointer only after a served-byte check. Preserve the historical manifest and artifacts. Account for `build_launch.mjs` JSON compaction: compare the hash of the actual distributed representation, or hash canonical content under an explicit contract. This takes precedence over relabelling the existing pointer or changing a single index file.

**Acceptance:** On a fresh public read, resolve `latest.json` once; fetch its manifest and every referenced cube index and partition from that release namespace; verify each served byte length and SHA-256 against the manifest; check declared row counts and source versions against the index; repeat after a newer release is promoted and prove the previous release's URLs still return the same bytes. The publish pipeline must refuse pointer promotion on any mismatch. Record the exact time, release ID and hashes in the research log.

### 2. Give every export an unambiguous data identity and make provenance failure visible

**Immediate portal fix.** `/release.json` names a frontend build commit, while `/data/atlas/latest.json` names the scientific atlas release. The Everything export currently stores the former in a field called `release`; in Vite development, `/release.json` falls through to HTML and the export stores `release: null`. Public AOI export behavior has not been exercised. Use explicit `frontend_build` and `atlas_release_id` fields, plus the actual dataset/object IDs read for the export. Resolve all data through one pinned release during the export and display an error or explicit incomplete-provenance state if that release cannot be confirmed. Do not silently serialize null as if the export were citable.

**Acceptance:** With a complete local release fixture and then in a bounded public browser test, select a known AOI and download Everything JSON. Assert basin IDs, period, sources, `frontend_build`, `atlas_release_id`, and referenced manifest digest match the exact records fetched. Simulate missing `/release.json`, missing `latest.json`, an HTML fallback, and a mid-export pointer change; each must produce a visible error or an explicitly marked incomplete export. CSV/JSON claims should cite the same data identity. Do not count a successful metadata GET as an export pass.

### 3. Repair and run the real browser release gate

**Immediate QA fix.** The documented browser suite stopped at its first English-label assertion while a separate inspection saw Russian UI. That result is a test/language-state problem at entry, not evidence that downstream empty-state, retry or mobile journeys fail. The existing local `dist` preview lacks data assets and cannot exercise AOI export. Build a full local publication fixture or test against a bounded deployed path, control language state explicitly, and run the complete suite.

**Acceptance:** The browser suite passes from a clean profile in both supported language states; the finder, basin profile, AOI drawing, CSV/JSON downloads, no-match message, 503/retry, desktop and mobile viewport, and touch interaction all complete. Assert accessible labels in the selected language and real JSON content types for metadata/data URLs. Capture a public run separately from local fixture results. If a scenario cannot run, report `NOT TESTED`, never `PASS`.

### 4. Show validation scope and model limitations beside the data

**Immediate content fix, followed by scientific work.** Keep the site labelled **public preview**. On climate series and downloads, show source asset/product version, observed versus provider-modelled versus locally estimated status, spatial/time support, units and transformations, coverage, release ID and the scope of independent checks. For the Pskem panel, identify same-month inputs, its single-basin 2013–2017 evaluation, and the poorer performance than seasonal climatology. Avoid an unqualified "validated model" or forecast caption. Keep snow withdrawn from trend use, and distinguish calendar slots after the last observed month from within-record gaps in the catchment tab (an already documented open finding in `docs/LAUNCH.md`).

**Acceptance:** A user can open a climate value and find its data release, source/version, method, units, coverage period, missingness and validation sample; the one-cell audit is visibly described as a single-case extraction check. The Pskem view reports both RMSE values, the reference baseline and lack of lead-time and interval validation. Tests assert that dates after the final observation are not rendered as 0% observed coverage, while real within-record missingness remains visible. Review every claim against its linked evidence artifact before publishing.

### 5. Expand science with a sampled, independent validation programme

**Longer scientific work.** Select multiple basins across both river systems, elevation and size classes; predeclare variables, periods, independent source versions, tolerances and sampling rules. Verify topology against separately obtained original geometry; verify climate values against upstream provider cells or independently acquired exports; rebuild model observation rows from pinned raw sources and test spatial/temporal transfer against climatology. Retain input hashes, acquisition manifests, scripts, failed cases and licence decisions. The chosen paper replication remains blocked until its 2.5 GB author archive is acquired, checksum-verified, licensed and executed; its future projection is not directly comparable to this portal's historical record.

**Acceptance:** Publish a sampling protocol before inspecting results; retain an auditable case manifest and machine-readable pass/fail results; require independent reviewer sign-off per claim. For an interval or forecast claim, define issue date, lead time, predictor availability, held-out periods/catchments, baseline skill and empirical interval coverage. A paper comparison needs a matched geography, baseline, forcing and scenario. Expand portal wording only to the scope that passes.

## Claims to keep in preview or blocked state

- **Public preview:** atlas-wide scientific validity, all-basin climate accuracy, full AOI geometry accuracy, TerraClimate v1.1 and upstream ERA provider-cell fidelity, and any implication that a positive Pskem NSE beats a seasonal forecast baseline.
- **Blocked for citation until priority 1 passes:** a claim that the current public `uz-20260924T150158900Z` pointer pins the served cube index or partitions. The exact served Parquet versions remain unknown.
- **Blocked for a feature claim until tested:** public Everything export provenance and the browser suite's downstream retry/mobile/no-match paths.
- **Blocked scientific comparison:** numerical replication of Siegfried et al. 2024 and direct agreement/disagreement with its future `−2.7%` result.

No production code or deployed data was changed by this review.
