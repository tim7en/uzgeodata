# Chirchik–Charvak case studies

The page now separates Chirchik/Pskem from the implemented
[regional station–satellite study](regional-station-environment.md), using 86
station locations, QA-screened historical Earth Engine data, terrain/soil
context, calendar audits, regression charts and CSV/JSON downloads.

The [2026-09-09 Pskem model review](pskem-model-review-20260909.md) replaces the
mixed headline gallery with a new chronological evaluation. The previous
stratified fit remains a reference; improved monthly timing does not establish
seasonal water-volume forecast skill.

Open `/case-studies.html` in the running application. It contains historical
station validation, MODSNOW-style snow monitoring, elevation and land-cover
profiles, surface-energy comparisons, physical / random-forest / Bayesian
models, Charvak water extent and an evidence-readiness bar.

The linked `sabitov-2018-review.md` now audits the full local thesis and documents
four executed daily adaptations, dimensional corrections, held-out results and
missing physical evidence. The “Sabitov methodology” section includes model
comparisons, runoff pathways, flow duration, satellite checks and climate stress
tests. These are transparent adaptations, not numerical replication.

`npm run cases:sabitov:inputs` retrieves daily ERA5 forcing for 2000–2017 and
Pskem-specific GLIMS outlines. `npm run cases:sabitov` rebuilds the four models,
six-page PDF atlas, result workbook and full review offline. Extend forcing with
`python PIPELINES/extract_sabitov_inputs.py --end YEAR`; this daily experiment
defaults to the historical validation period, separately from latest-month updates.

Independent land-cover samples belong in `landcover-reference-labels.csv`. Its
empty starting state means no accuracy claim is available. Use unique sample IDs,
dated independent sources and aligned mapped/reference class definitions.
Sample accuracy is not an area-adjusted estimate for a stratified survey.

Earth Engine authentication was completed and read access verified with project
`ee-sabitovty`. Credentials remain in the local Earth Engine credential store.
For another machine/account, run `python -m ee.cli.eecli authenticate --auth_mode=localhost`
and use an Earth Engine-enabled project. Never commit credentials.

## Reproduce or refresh

```bash
# Recompute downloaded evidence, figures and reports without network requests
python PIPELINES/update_chirchik_studies.py --offline

# Refresh available remote inputs, then rebuild all analyses
npm run cases:update

# Scientific guards and application build
npm run test:cases
npm run test:sabitov
npm run build
```

The refresh command uses the current year for combined snow and energy retrieval,
keeps yearly request caches, and refreshes the latest partial source year. It
writes `pipeline-status.json` with completed stages and any failure. Cache files
live under ignored `WORKSPACE/derived/chirchik-cache/`. This implementation targets
Pskem. Expansion needs a verified catchment, its own observations and adapted
identifiers/configuration. Large domains should use Earth Engine batch exports.

Individual commands include `cases:forcing`, `cases:profiles`, `cases:energy`,
`cases:analyse`, `cases:models`, `cases:build`, `cases:figures` and
`cases:figures:validation`. Python dependencies: Earth Engine API, requests,
NumPy, SciPy, scikit-learn, Shapely, pyproj, matplotlib and openpyxl. Tests use
pytest. The web build needs Node >=20.19.

## Delivered artifacts

Generated evidence is under `PUBLISHED/data/case-studies/`:

- `chirchik-deep-study.md`: historical climate, snow, seasonal-flow and reservoir
  verification with primary-source citations and all tested specifications.
- `chirchik-environment-study.md`: terrain, energy, physical/ML/Bayesian methods,
  actual results, readiness and prioritised professional extensions.
- `chirchik-scientific-atlas.pdf`: ten scientific figures, including the study map;
  corresponding PNGs are adjacent.
- `chirchik-analysis.xlsx`: supporting chart data, model scores and sources.
- `sabitov-2018-review.md`: full-thesis audit, implemented methods and caveats.
- `sabitov-methods.json`: daily scores, parameters, glacier depletion, sensitivity,
  satellite checks, scenarios, gap matrix and source hashes.
- `sabitov-methods-atlas.pdf` and `sabitov-methods-analysis.xlsx`: six additional
  scientific figures and daily/summary chart data.
- `advanced-validation.json`: corrections, uncertainty, paired records, strict
  seasonal-flow experiments and reservoir sensor checks.
- `environment-modelling.json`: profiles, model results, predictive intervals,
  importance, surface summaries, freshness, readiness and input hashes.
- `chirchik.json` and `chirchik-report.md`: observation audit and six study
  protocols authored in `CASE_STUDIES/chirchik-portfolio.json`.
- CSVs preserve station products, daily satellite snow, monthly surface energy,
  land-cover areas, quality audits, model predictions and source image IDs.
- Manifests preserve hashes, product definitions, coverage and processing rules.

## Evidence and limitations

ERA5 monthly forcing reaches July 2026; combined MODIS snow reaches September
2026 (partial month). Esri/Impact Observatory 10 m land cover covers 2017–2025.
LST and albedo reach August 2026; gap-filled MOD16 ET reaches the last 2025
composite. Historical JRC water history ends in 2021 and is cross-checked against
Sentinel-2 for 2018–2021. Check manifests for exact dates.

Pskem discharge remains 2001–2017. Monthly model training uses 2001–2010, with
2000 physical warm-up, and testing uses 84 months in 2011–2017. Forest RMSE is
23.58 m³/s versus the seasonal baseline's 26.09; the bucket and Bayesian model
have higher RMSE. The strict snow experiment has six training and four test
years, and the chosen snow predictor worsens seasonal-volume prediction.
Results after 2017 are unverified continuation.

One impossible source date (2015-02-29) is quarantined and three source-flagged
values are screened. Monthly means need 90% valid days; observed volumes need
every day. Missing-day volumes are not extrapolated.

Overall readiness is **red**: the gauge coordinate lies near a small tributary,
about 700 m from plausible Pskem main-stem reaches. No coordinate was changed.
The candidate is a full-unit reverse level-12 trace, not a verified partial-outlet
delineation. Every scientific check must be green for release; fresh inputs
alone cannot turn the status green.

Copernicus 30 m is a new terrain reference, not sub-30 m information. ERA5 values
by 250 m elevation band remain coarse-grid information. Accumulated runoff is
summed modelled generation, not routed measured discharge. MODIS LST is surface
temperature; MOD16 represents a restricted terrestrial footprint; land-cover
accuracy has not been established locally. Same-day Terra/Aqua combination does
not reproduce the full MODSNOW temporal cloud-removal algorithm.

The six protocols retain further work where observations are insufficient:
verified station elevations/product independence, recent discharge, independent
land-cover labels, glacier mass balance, and reservoir levels/bathymetry.
