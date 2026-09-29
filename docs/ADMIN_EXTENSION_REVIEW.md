# Admin and module-extension review (2026-09-29)

The user requested an endpoint and extensibility review; a broader admin rebuild is deferred. This is an inspection of the current code, not a claim that every route has been security-tested.

| Surface | Current behavior | Extension implication |
| --- | --- | --- |
| Public Cloudflare Worker | `worker.js` serves `/data/*` as read-only R2 objects and pages as static assets. | It cannot execute Python QA or acquisition. Publish a reviewed status JSON and keep rerun APIs on the local server. |
| Local inventory | `GET /api/admin/variables` returns the saved variable inventory plus local update operations. `/admin.html` falls back to static `data/variable-inventory.json` in the public build. | New product metadata should enter the registry and inventory builder first, then be exposed by the existing page. |
| Local updates | `POST /api/admin/variables/update` and `PUT /api/admin/variables/schedule` accept an allowlisted group ID. `SERVER/dataUpdates.mjs` persists queued/running/finished jobs and uses a single worker lock. | A new module requires a reviewed group definition, preflight inputs/dependencies, an executable recipe, QA gate, and a publication step. A browser-entered command or arbitrary module name must not be executable. |
| Uploads | Login, session, dataset list/upload/delete/download and request list are under `/api/admin/*`; uploads need the configured admin credentials. | Uploaded datasets are repository items, not automatically validated atlas modules. They need schema, licence, provenance and geometry checks before scientific publication. |
| Validation agents | `GET /api/agents` and `POST /api/agents/:id/run` exist only on the localhost server. The public page reads `data/agent-status.json`. | Reruns are independent checks; the status snapshot changes only after review and deployment. |

`ATLAS_MODULES/README.md` already defines a thematic module contract: `module.json`, source references, recipes, validation rules, and shared observation/revision semantics. `ATLAS_MODULES/update-groups.json` is a separate operations registry. Adding a module through admin should be a **reviewed proposal workflow**, not immediate execution: submit metadata and inputs, validate the contract and licences, run a bounded sample and reproducibility checks, then approve the registry/code change and publish a versioned release. The current admin UI does not yet implement that workflow.

Before an admin module builder is implemented, resolve two existing boundaries: a successful local append refresh may leave climatologies and release metadata at their previous state, and the public atlas release pointer currently disagrees with the served cube index. An admin success badge should therefore identify exactly which products were refreshed and which release they belong to.
