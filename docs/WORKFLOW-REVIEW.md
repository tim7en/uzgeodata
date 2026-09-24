# Workflow review: three-action budget

The design constraint is a completed user task in at most three actions. This is
an internal acceptance criterion, not website copy or a requirement to show
exactly three buttons. A chart must already be drawn at the end of a viewing
task; an extraction must actually deliver a file.

Count entering one search field, activating a result/control, selecting a value,
or dragging an area as one action each. Do not count individual keystrokes or
automatic loading. Do count required navigation, opening hidden panels,
confirmation screens, and manual movement needed to reach the result. Start at
the loaded explorer with no saved selection. User-chosen refinements are new
tasks, but must not be required to obtain a usable initial result.

## Findings and implemented changes

| Previous friction | Change |
| --- | --- |
| Header and basin panel hidden until hover or activation | Keep primary controls visible; remove hidden-panel prerequisites. |
| Search limited to the zoom-dependent map level | Search every level-12 basin by HYBAS/PFAF identifier at any zoom. Fetch search geometry on demand; show local error/retry and empty states. |
| Search only selected a basin; users then opened the table and monthly tab | Search results open charts, attributes or estimates directly. Level-12 map clicks open monthly charts. |
| Downloads spread across data tabs | Keep basin attributes/estimates JSON and monthly values/metadata JSON available above the tabs. |
| Explanations pushed the chart and CSV below the phone viewport | Put the CSV action, variable choices and chart first. Keep provenance, missingness and snow restrictions. |
| Area drawing required individual vertices and a finish action | Draw a rectangle in one mouse/touch drag. Automatically complete the selection. On phones, bring the map into view when drawing starts and the results into view when it ends. |
| Mobile search followed the map and header | Put the finder before the map and keep search within the initial phone viewport. |

## Primary task budgets

| Outcome | Path from the loaded explorer | Actions |
| --- | --- | ---: |
| View a basin monthly chart | Enter identifier → choose basin result | 2 |
| View a specific monthly variable | Enter identifier → choose basin result → choose variable | 3 |
| Extract all basin monthly variables as CSV | Enter identifier → choose basin result → download CSV | 3 |
| Extract monthly values with provenance | Enter identifier → choose basin result → monthly data and metadata JSON | 3 |
| View published attributes | Enter identifier → Attributes on the result | 2 |
| Filter published attributes | Enter identifier → Attributes → enter attribute filter | 3 |
| View independent estimates | Enter identifier → Estimates on the result | 2 |
| Read an estimate's evidence | Enter identifier → Estimates → expand the estimate | 3 |
| Extract basin attributes and estimates | Enter identifier → any result view → attributes and estimates JSON | 3 |
| Extract a spatial basin list or the area outline | Draw area → drag rectangle → download | 3 |
| Extract area attributes, monthly records or the complete JSON | Draw area → drag rectangle → choose the corresponding download | 3 |
| Colour the map using a featured attribute | Choose Colour basins by | 1 selection |

The area workflow uses the existing intersection rule and published simplified
geometry. Data exports retain the existing 1,000-basin fetch limit; the basin list
does not fetch individual records. Areas exceeding that limit need another task
to narrow the selection. This is a remaining limitation, not a successful
three-action data extraction. Downloads preserve published missing values.

## Remaining project-wide gaps

This change verifies the main explorer, not universal compliance across every
research, administrative and legacy explorer page.

- Geographic discovery without a known identifier still depends on map navigation.
  Add a named-basin/place index with direct result actions before claiming that
  every discovery task fits the budget.
- Arbitrary polygon boundaries have been replaced by the standard rectangle
  workflow. Exact custom boundaries would need a direct geometry import action;
  they should not return as a mandatory vertex-by-vertex wizard.
- Custom area inclusion rules require another choice. Expose preset task actions
  for alternative rules if those become primary workflows.
- Large spatial exports need a server-side or prebuilt download product to avoid
  the existing per-file fetch cap.
- Legacy land-cover/climate explorers have independent variable, period, geography
  and view controls. Named analysis presets and direct export actions are needed
  for tasks that require several of those controls. Their end-to-end budgets have
  not been certified by this browser test.
- Research case studies and local maintenance are separate workflows. Inventory
  concrete tasks and test from their entry points before claiming compliance.

For future changes, specify the desired output and default geography/period,
write the actual action sequence, and reject required detours beyond the budget.
Do not hide necessary choices inside a nominal single “configure” step.

## Verification

`python TESTS/test_workflow_browser.py` runs against a Vite server on port 5175
(`TEST_BASE_URL` can override it). It exercises real search, chart rendering,
CSV/JSON downloads and file contents, direct attribute/estimate views, rectangle
selection, failed-search retry, no matches, and mobile controls. It also checks
touch rectangle selection and browser runtime errors.

The history, landing and area model suites cover missing values, basin joins,
spatial selection and export content. Build the interface without running data
acquisition using `LAUNCH_BUILD=1 npx vite build` (set the environment variable
using the syntax of your shell).
