# SR-02 and workflow follow-up (2026-09-29)

## Result

The local development server does not supply the frontend release metadata needed by the area-of-interest **Everything** export. `GET /release.json` returned `200 text/html` through Vite's HTML fallback, which `readJson` rejects. `AoiTool.jsx` catches that error and passes `null` to `exportDocument`; the latter serializes `release: null`. This confirms the cause of the first-pass local export failure. The existing production-style frontend build supplies `/release.json`, and the public site serves it, but this follow-up did **not** execute a public AOI export. Public export success is therefore unverified.

The release object produced by `PIPELINES/build_launch.mjs` contains the frontend Git commit, generated time, coverage summary and file totals. It is **not** the atlas scientific release ID. The public `/release.json` reports frontend commit `b51a06b32cd54995b62309f730cca1b489c10782`; public `/data/atlas/latest.json` points to atlas release `uz-20260924T150158900Z`. Putting the former in an export's `release` field does not pin the latter's data or resolve the SR-01 cube index mismatch.

## Scenario matrix

The machine-readable matrix is [scenarios.json](scenarios.json). It separates local dev, local preview, and public endpoints; `PASS` here describes only the exact probe cited in each row.

| Scenario | Environment | Status | Evidence |
| --- | --- | --- | --- |
| `/release.json` | Vite dev | FAIL | `200 text/html`; rejected by `readJson` |
| Browser workflow suite | Vite dev | FAIL | Exit 1 at first finder visibility assertion after 5 s; browser showed Russian UI after 12 s |
| Everything export | Vite dev | FAIL | First-pass saved JSON had `release:null`; source and endpoint explain it |
| `/release.json` | Existing `dist` preview | PASS | `200 application/json` |
| Everything export | Existing `dist` preview | NOT TESTED | `dist` is frontend-only; `/data/atlas/basins/index.json` fell back to HTML |
| `/release.json`, catalogue, latest pointer | Public site | PASS | Three bounded, verified-TLS JSON GETs |
| Everything export | Public site | NOT TESTED | No public browser export performed |
| Empty state, retry, mobile | Vite dev | NOT TESTED | Browser suite stopped before these steps |

The browser suite failure should not be read as proof those downstream workflows are broken. Its first assertion requires the English accessible label; a separate browser inspection showed Russian interface text after 12 seconds despite the suite's `locale="en-US"` and `localStorage` setup. The language state deserves a focused test if this suite is to be a release gate. No optional retry was attempted after that failure.

## Code path and recommendation

`INTERFACE/AoiTool.jsx` `readJson` validates JSON content type; its Everything task reads catalogue, basin records, histories, then `/release.json` with `.catch(() => null)`. `INTERFACE/aoiModel.js` writes the provided value into the top-level `release` field. `vite.config.mjs` exposes `PUBLISHED/` in development; `PUBLISHED/release.json` is absent. `PIPELINES/build_launch.mjs` writes `dist/release.json` after the Vite build, and the deployed static site serves that file.

**Verified recommendation:** define one explicit export provenance contract containing both `frontend_build` and `atlas_release_id`, fetched from the same published data snapshot as the records. Make a missing or inconsistent atlas release visible and block the claim that an Everything export has complete provenance. Add an AOI browser assertion for those exact fields against a release-backed fixture or complete local publication build. The public endpoint checks support this design, but the behavior of public AOI export remains an inference until exercised.

The present AOI `release` field is ambiguous and may mislead users into treating a Git commit as a scientific data release. The existing 1,000-basin per-file cap and simplified geometry warning remain documented workflow limits. Broader mobile, retry and empty-state compliance is not established by this run.
