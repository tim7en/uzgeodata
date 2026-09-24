# Public preview release

The launch user is a researcher investigating a basin. The five-minute task is to
find a level-12 basin, read published attributes and independent estimates, inspect
the 2003–2022 monthly record, and download values with provenance.

## Frozen scope

- 7,445 basins in the Amu Darya and Syr Darya systems.
- 281 published attribute definitions; independent estimate coverage varies.
- Completed monthly runs only; consult `release.json` for included temperature and other variables.
- Whole-catchment statistics for level-12 basins: area-weighted monthly means over
  the traced upstream network, sub-basin extremes, water-volume totals where the
  unit allows one, and derived morphology. Level 7 and level 9 carry no catchment
  package and the tab says so.
- About, citation, source reuse terms, help, projects and responsive map/modal.
- Public preview, not an independently reproduced scientific release.
- Snow retained for inspection but withdrawn from trend analysis.

## Build and deploy

Use Node 22 and `npm ci`, then `npm run build:launch`. This does not run Python,
Earth Engine, model fitting or observation-store writes. It reads saved public
files, validates every history file, excludes raw partitions, compacts JSON and
writes a static artifact into `dist/`. It must fail if the monthly snapshot is
absent or incomplete. It does not silently deploy a broken history tab.

`npm run preview:launch` serves the result locally. For a domain root, the default
`SITE_BASE=/` is correct. The current custom-domain workflow uses `SITE_BASE=/`. For GitHub Pages without
the custom domain, set `SITE_BASE=/uzgeodata/` during the build. This rebases both interface URLs and paths in saved data catalogues. The
artifact includes `release.json` with commit, publication time and release scope.

Deployment is Cloudflare, not GitHub Pages. Cloudflare Workers Builds is connected
to this repository (Workers → uzgeodata → Settings → Builds) with build command
`npm run build:cloudflare` and deploy command `npx wrangler deploy`, so a push to
`main` ships the interface. It ships no data: `build:cloudflare` strips `dist/data`
and the Worker reads `/data/*` from R2. The GitHub Actions workflow that deployed to
Pages was removed; `.github/workflows/ci.yml` still runs the tests and the launch
build on every push, which is what guards the release.

The live site is `https://uzgeodata.uz/`. While the domain is delegated to the
registrar's nameservers it still answers from the old Pages deployment; the Worker
takes over once the zone is on Cloudflare and `uzgeodata.uz` is added to the Worker
as a custom domain.

Public application requests use static files. `/admin.html` displays the saved
variable inventory; authenticated updates require the separate local admin server
described in [ADMIN.md](ADMIN.md). There is no production Node API,
database or secret. An alternative static host can serve the domain-root artifact;
do not add an SPA fallback for missing `/data/` files. Those requests should be 404.

## Updating the data later

Do not invoke extraction or the legacy `npm run build`/`npm run dev` lifecycle as
part of deployment. Those legacy scripts also run publication commands.

When extraction has finished, explicitly publish and review the new snapshot:

```sh
npm run atlas:history
npm run atlas:api
npm run atlas:coverage
npm run test:ui
python -m pytest TESTS -q
npm run build:launch
npm run publish:r2
```

`publish:r2` is what puts the new snapshot in front of readers: the live site reads
`/data/*` from R2, and a Git push deploys the frontend only. Run it before or after
committing, but do not treat the commit as the publication.

The history publisher freezes completed-run eligibility on startup. It excludes
unfinished runs, honours observation revisions and fails on mixed per-variable
provenance. Commit reviewed public outputs; do not commit raw partitions or
credentials. `atlas:api` requires local source GIS data and Python dependencies.

## Publish the data to R2 (Cloudflare)

Cloudflare serves the frontend from Workers Static Assets and the data from the
`uzgeodata-public` R2 bucket. `build:cloudflare` deletes `dist/data` before
deployment: the release is about 1 GB, which belongs in object storage rather than
in an asset bundle, and `worker.js` answers `/data/*` from the bucket.

Nothing in the GitHub → Cloudflare build uploads data. `npm run publish:r2` does,
from a machine that holds the release:

```sh
npm run publish:r2 -- --dry-run    # report the difference, upload nothing
npm run publish:r2                 # build the release, then sync it
npm run publish:r2 -- --prune      # also delete objects the release dropped
```

It syncs `dist/data`, the tree `build:launch` validates and filters, not
`PUBLISHED/data`. Only objects whose MD5 or size differs are uploaded, so a
one-file change is a one-object upload. Credentials are R2 S3-API tokens in `.env`
(`R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`), created under
R2 → API → Manage API tokens with Object Read & Write on the bucket; the wrangler
OAuth login cannot list a bucket, and listing is what makes this a sync.

`npm run publish:site` publishes the data, strips `dist/data` and runs
`wrangler deploy` against one build, for a full deployment without waiting for the
Git-triggered build.

A dataset that should not enter Git at all is gitignored and then declared in
`PUBLISHED/release-includes.txt`, one path per line under `data/`. The launch build
reads that file as a second allowlist beside `git ls-files PUBLISHED`, so the data can
be untracked while the decision to publish them stays tracked and reviewable. A
declared path missing from a checkout is reported and skipped, so this workflow does
not break CI or a fresh clone.

Rollback for data is per object: republish the previous release tree
(`git checkout <commit> -- PUBLISHED`, rebuild, `npm run publish:r2 -- --prune`).
R2 keeps no versions unless the bucket is configured for them.

## Release size

`build_launch.mjs` fails the build above a byte budget, now 10,000 MB and settable
with `RELEASE_BYTE_BUDGET`. The old 1035 MB figure existed because "published GitHub
Pages sites may be no larger than 1 GB"; data ship from R2 now, which stores 10 GB on
the free tier and charges nothing for egress, so that ceiling no longer binds. The
budget remains a runaway-pipeline guard rather than a hosting limit.

The measurements below were taken against the 1 GB Pages ceiling and are kept as the
record of how the package grew.

The release passed 1,000,000,000 bytes when the catchment package was added. The
measured positions:

| Release | Bytes | vs 1,000 MB | vs 1 GiB |
| --- | --- | --- | --- |
| `d59d0422c`, before the catchment package | 978,800,018 | 21.2 MB under | 94.9 MB under |
| `46a486885`, with it | 1,021,390,184 | 21.4 MB over | 52.4 MB under |

Pages deployed and serves the larger one, so the limit is enforced at 1 GiB
(1,073,741,824) rather than at 10^9. That reading is not documented, so treat the
remaining ~52 MB as the real headroom and confirm `release.json` on the live site
after any deploy that adds bulk.

The release ships only files that `git ls-files PUBLISHED` reports, so generated
public data must be committed to reach the site. 25 files, 162.4 MB, are
deliberately excluded: the `data/review/` source geometry, kept in the repository
but not republished. `data/review-layers.json` records the count and the reason and
the layer index is filtered to what exists, so the review tool never offers a
missing layer.

If the release has to come back under 1,000 MB, the catchment package cannot do it
alone. Re-quantizing its nine monthly matrices was measured at 6.2 MB saved at a
0.001 step, 13.6 MB at 0.01 and 19.5 MB at 0.1, and rounding `morphology.json`
floats to four decimals saves 0.67 MB. The most aggressive combination still lands
near 1,001 MB, and published history values carry up to four decimals, so the
current 0.0001 step is lossless and anything coarser discards source precision. A
cut of that size has to come from elsewhere in the 482 MB `data/atlas` or 207 MB
`data/hydroclimate` trees.

## Release checks

Check `/project.html` and example links on desktop and mobile, then open the map at `/`: choose a level-12 basin, open all
four tabs, expand evidence, download CSV and JSON, and follow About/Help links.
Check a basin outside the Pskem pilot. Verify a missing API file returns 404.
Check the public `release.json` commit and `bytes` after deployment. The browser
test supports `ATLAS_TEST_URL`, including a deployment subpath.

For the catchment tab, confirm the monthly matrix passes its integrity check: the
served `.bin.gz` must arrive as `application/gzip` with no `Content-Encoding`, or
the browser decompresses it in transit and the SHA-256 in `index.json` no longer
matches what the page hashed. Open a level-7 basin as well; it must show the
level-12 note without fetching a matrix.

Raw-store integration tests explicitly skip when raw partitions are absent from a
checkout. Unit tests still exercise the contract with temporary stores. During a
separate live-store audit, set `UZGEODATA_SKIP_LOCAL_STORE=1` to avoid duplicating
that audit; the test report lists those skips.

The initial snapshot was recovered after an editor restart using
`python PIPELINES/recover_launch_history.py`. That tool reads only completed
snow/TerraClimate/runoff checkpoints and small ledgers, compares every surviving
store export exactly, and publishes the index only after all 7,445 basins match
the expected frame. It never touches the extraction partitions. Routine later
updates use `atlas:history` after acquisition has finished.

## Rollback

Revert the launch change on the publishing branch and let the workflow deploy the
previous reviewed snapshot, or re-run the previous successful deployment workflow.
Neither action changes the local observation store or acquisition checkpoints.

## Open findings

Recorded from the September 2026 catchment-statistics release and not yet fixed.
Neither of the first two misstates a number; each makes the site read worse than
the data behind it actually is.

**1. The catchment tab shows unextended months as coverage gaps.** The published
history frame is 288 calendar positions, but the record itself is shorter: the
history files declare `observed_months: 264` with `missing_months: 0` for
precipitation, meaning 2003-01 to 2024-12 is the record and the rest has simply not
been extended. `aggregateCatchment` cannot tell the two apart and counts the 24
unextended slots as members with no observation, so the table and the monthly CSV
end with 24 rows reading `0%` coverage over none of the member basins, for 2025-01
to 2026-12. `run_mm_s`
reaches 2026-08 and shows four such rows. The effect is that a current dataset
looks like it has a two-year hole. The fix is to stop the table and the CSV at the
last month any member basin observed and to state the covered span above the
table; it touches `INTERFACE/catchmentStatisticsModel.js` and its test only, with
no pipeline rerun and no redeploy of the 42 MB package.

Distinguish this from real within-record missingness, which the tab already
handles correctly: `snw_pc_s` has 251 months covered at 98–100% of basins, so its
full-catchment total is withheld in nearly every month by design.

**2. The withheld-layer notice never reaches a reader.** `build_launch.mjs` writes
`withheld: { layers, reason }` into `data/review-layers.json`, naming HydroSHEDS as
the place to get the 25 excluded layers unchanged. `INTERFACE/LayerReview.jsx`
reads that index but never references `withheld`, so the explanation ships in the
JSON and is shown nowhere. The review page silently lists 13 layers instead of 38.

**3. `python -m pytest TESTS -q` fails on `main`.** Three tests, unrelated to each
other and pre-existing: `tests/test_ca_discharge.py` (a Windows `charmap` decode
error that does not reproduce on Linux), `tests/test_case_study_package.py`
(`PUBLISHED/data/case-studies/model-review.json` no longer matches its declared
hash) and `tests/test_ontology.py` (reads untracked `WORKSPACE/derived` artefacts).
The `integrity` workflow has failed at its `Run tests` step since at least
`798833ad8`; the `Public preview` workflow, which runs `test:ui` and
`build:launch`, passes. Fixing the hash drift and the encoding assumption would let
the integrity workflow speak again.

## Deferred work

Independent scientific reproduction, explanation of snow null drift, expanded source coverage, more attribute families, national-atlas reimplementation and the
monitoring ontology are follow-up work. Do not advertise them as completed.
