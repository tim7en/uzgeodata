# Functional QA first pass — 2026-09-29

Target: local Vite at `http://127.0.0.1:5175/`; Python Playwright 1.58.0, installed Chromium, 1440 × 900 viewport. Browser requests were limited to one small AOI and its 23 per-basin export files. This is a functional consistency check, not independent scientific validation.

## Reproduce

From repository root, start `node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5175 --strictPort`, then run `python qa/functional/check_first_pass.py`. The script writes [results.json](results.json), [basin-list.csv](basin-list.csv), [area-export.json](area-export.json), and [selection.png](selection.png). The exit code is 1 while the release metadata failure remains. No production service was contacted.

| Scenario | Status | Evidence |
| --- | --- | --- |
| Draw rectangle and select level-12 basins | PASS | 23 selected; screenshot and results JSON |
| CSV identifier and system preservation | PASS | 23 distinct IDs; each matched `/data/atlas/basins/index.json` system |
| JSON identifiers and AOI geometry | PASS | Same 23 IDs as CSV; polygon present in `area_of_interest.geometry` |
| JSON attribute and release metadata | FAIL | `attribute_meta` exists, but top-level `release` is `null` |
| Invalid coordinate input | NOT TESTED | AOI is pointer driven; upload validation was not exercised |
| Browser JavaScript errors | PASS | No page errors captured during this path |
| Other basins, variables, charts, PDF, network failures, mobile | NOT TESTED | Outside this first bounded pass |

## Failure reproduction and scope

1. Open the local homepage at 1440 × 900, choose **Draw area**, and drag a 24 × 24 pixel rectangle near 60% of the map width and 48% of its height.
2. Download **Everything** (JSON). Inspect top-level `release`: it is `null` while `attribute_meta` and the selected basin IDs are present.
3. `AoiTool.jsx` requests `/release.json` and converts any fetch error to `null`. This local Vite target has no `PUBLISHED/release.json`; a request to `/release.json` is not a JSON release document. Whether a deployed build supplies one is **not tested**. The user-facing export therefore lacks an explicit release identifier in this local path. No selected variable applies to this failure.

The screenshot shows the selection. The downloaded JSON is the response-derived export and contains no credentials. Data agreement across the interface, index and exports establishes path consistency only; all use published project artifacts.
