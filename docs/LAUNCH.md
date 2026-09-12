# Public preview release

The launch user is a researcher investigating a basin. The five-minute task is to
find a level-12 basin, read published attributes and independent estimates, inspect
the 2003–2022 monthly record, and download values with provenance.

## Frozen scope

- 7,445 basins in the Amu Darya and Syr Darya systems.
- 281 published attribute definitions; independent estimate coverage varies.
- Completed monthly runs only. Temperature extraction continues independently.
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
`SITE_BASE=/` is correct. For GitHub Pages, set `SITE_BASE=/uzgeodata/` during the
build. This rebases both interface URLs and paths in saved data catalogues. The
artifact includes `release.json` with commit, publication time and release scope.

The Public preview workflow builds pushes to `main` (or a manual dispatch)
and deploys through GitHub Pages. In repository Settings → Pages, select GitHub
Actions as the publishing source. The `github-pages` environment must permit the
launch branch. The site is expected at `https://tim7en.github.io/uzgeodata/` once
the deployment succeeds. See [GitHub's workflow requirements](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

All application requests use static files. There is no production Node API,
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
```

The history publisher freezes completed-run eligibility on startup. It excludes
unfinished runs, honours observation revisions and fails on mixed per-variable
provenance. Commit reviewed public outputs; do not commit raw partitions or
credentials. `atlas:api` requires local source GIS data and Python dependencies.

## Release checks

Check the built artifact on desktop and mobile: choose a level-12 basin, open all
three tabs, expand evidence, download CSV and JSON, and follow About/Help links.
Check a basin outside the Pskem pilot. Verify a missing API file returns 404.
Check the public `release.json` commit after deployment. The browser test supports
`ATLAS_TEST_URL`, including a deployment subpath.

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

## Deferred work

Independent scientific reproduction, explanation of snow null drift, temperature
publication, more attribute families, national-atlas reimplementation and the
monitoring ontology are follow-up work. Do not advertise them as completed.
