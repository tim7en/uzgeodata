# Admin data freshness and updates

Open `/admin.html` to search the complete registered variable/product inventory,
filter by the four layers, inspect freshness and coverage dates, and open product
metadata. The static public site displays the saved inventory. It cannot run
updates; credentials must never be placed in a public page or GitHub Pages build.

## Start the admin server

Use Node 22 and an existing checkout:

```sh
npm ci
python -m venv .venv
.venv/bin/python -m pip install -r requirements-pipelines.txt
```

In a local `.env` file (ignored by Git), set:

```dotenv
UZGEODATA_PYTHON=/absolute/path/to/uzgeodata/.venv/bin/python
```

Then run:

```sh
npm run admin
```

Open **http://localhost:5173/admin.html**. Update controls need no sign-in for
now: the server binds to localhost, rejects cross-origin requests and only runs
allowlisted update groups. (The dataset upload API still requires
`ADMIN_USERNAME` and `ADMIN_PASSWORD`.) This command starts the
existing server directly and avoids the acquisition/publication hooks of
`npm run dev`. Use `PORT` to choose another local port. The server binds to
localhost. `COOKIE_SECURE=true` is required when operating behind HTTPS.

The inventory snapshot is already included. Regenerate it after adding a product
or changing registry metadata with `npm run data:inventory`; this command reads
local metadata and tables and does not acquire imagery.

## Enable an update group

Choose **Manage update groups**. A row's **Update group** action updates all
products in that source group; it never secretly launches one job per attribute.
The panel shows required local inputs.

Regional atlas updates (TerraClimate, ERA5-Land, MODIS snow) run in one of two modes:

- **Full refresh**, when the observation store partitions
  (`PUBLISHED/data/atlas/observations/time_kind=*`) and the BasinATLAS geodatabase
  are present. New months go into the store and every product is rebuilt from it.
- **Append to the published record** (temporary), on an ordinary Git checkout. The
  last published month is read from `PUBLISHED/data/atlas/cube/`, only newer months
  are extracted into a scratch store under `WORKSPACE/data-updates/stores/`, and they
  are appended to `history/` and `cube/`. Basin outlines come from the tracked
  `GEODATA/transboundary_basins_v2/hydroatlas-level12-full-basins.geojson`, which
  yields the same geometry version (`reg-166479294ef8`) and identical values.
  Climatologies, the basin API, the coverage ledger and the release are not rebuilt;
  each updated index lists the run under `appended`. Once the store is restored,
  the full refresh supersedes this.

Do not recreate provenance by treating the public cube as the raw record.

Authenticate Earth Engine in the configured Python environment and verify the
project access used by `PIPELINES/extract_dated_snow.py`. The worker checks this
before acquisition. It does not install dependencies or request credentials from
the browser. Other groups use their existing pipelines and may also require
local geospatial inputs.

Jobs show queued, running, succeeded, failed or interrupted states and a separate
execution progress bar. Detailed logs remain in `WORKSPACE/data-updates/logs/`.
Failed jobs retain their error, and source freshness is not advanced for them.
Review interrupted extraction checkpoints before retrying. Avoid running manual
extraction commands against the same files while the admin worker is active.

Enable **Keep updated** per group: daily, weekly or every 30 days. A saved schedule
does not keep the computer awake or start a stopped server. Run this server under
your operating system's service manager if continuous operation is required.
The next scheduled time and any scheduling error appear in the group panel.
Switching a schedule off stops future runs; it does not cancel an active job.

## Publish reviewed results

The worker updates this workstation's `PUBLISHED/` outputs, not the live website.
After checking the new observations, quality flags and logs:

```sh
npm run data:inventory
python -m pytest TESTS -q
npm run test:ui
npm run build:launch
```

Review and commit only intended public outputs and source changes, then deploy
through the normal GitHub workflow. Keep `.env`, `WORKSPACE/`, bulk evidence
partitions and large geodatabases out of the commit. Existing release hashes and
mutable release paths need the remediation described in
[the architecture document](ARCHITECTURE.md#deployment-and-integrity-boundaries)
before claiming immutable scientific reproduction.

## Add an updateable variable

1. Register its scientific identity, unit, support, period and preferred source in
   the appropriate atlas/ontology registry. Canonical monthly basin variables
   also belong in `ATLAS_MODULES/core/variables.py`.
2. Implement and test the ingestion recipe, missing-value rules and provenance.
3. Add a reviewed group to `ATLAS_MODULES/update-groups.json`, with a stable ID,
   explicit prerequisites and fixed command arrays. Never accept command text
   from an HTTP request. Map the product to that group in the inventory builder.
4. Rebuild the inventory and run inventory-coverage and update tests. Missing
   products and unimplemented recipes must remain visible as such.

For fixed reference editions, review/import a new source version rather than
automatically recalculating the historical reference. For on-demand products,
update the underlying observations and select the intended release in the query.
