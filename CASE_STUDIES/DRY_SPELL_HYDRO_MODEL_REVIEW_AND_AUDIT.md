# Dry-Spell and Hydrologic Modelling Review and Audit

**Review date:** 2026-09-16  
**Scope:** Gauge discharge modelling, dry-spell detection, antecedent conditions, and transfer to BasinATLAS basins  
**Status:** Audit baseline after corrected validation rerun

## 1. Purpose

This document records the scientific and implementation review of the dry-spell and hydrologic modelling work. It is intended to answer four questions:

1. What is currently supported by the available data and basin attributes?
2. Which modelling results are reproducible and honestly validated?
3. Where can existing static basin attributes improve hydrologic interpretation or transfer?
4. What work is required before issuing basin-scale early-warning claims?

The review separates:

- **Observed or source-derived facts:** measured discharge, station climate inputs, basin geometry, terrain, land cover, and routing metadata.
- **Derived diagnostics:** lags, anomalies, stress indices, dry-spell labels, baseflow proxies, and basin zonal statistics.
- **Predictive claims:** forecasts or classifications evaluated against observations on a time period unavailable to model fitting.

A derived diagnostic is not automatically a validated forecast. The distinction is important for dry spells, where seasonality can produce apparently strong results without providing useful anomaly warning.

## 2. Current Executive Assessment

The project has a strong foundation for a gauge-anchored basin study:

- 38 gauges and 6,739 monthly records are available in the current discharge feature table.
- Static basin attributes and land-cover features are broadly complete for the current gauge set.
- Climate forcing is available for only six gauges in the current station-derived table, covering 1,832 of 6,739 records, or about 27.2%.
- BasinATLAS provides complete basin geometry, hierarchy, routing, and attributes for levels 01-12, with 3,981 level-12 features and 13,916 terminal/endorheic sinks reported in the package documentation.
- The corrected all-gauge baseline now uses chronological validation, a shared feature set with at least 90% network-wide coverage, and held-out scoring only.
- The all-gauge rerun trained 38/38 gauges, produced 1,363 held-out predictions, and achieved 79.6% overall p10-p90 interval coverage.
- Climate-enhanced features remain a separate six-gauge experiment because station-derived climate coverage is not network-wide.

The all-gauge baseline had positive held-out R2 for 17 of 38 gauges. The strongest current values were:

| Gauge | Held-out R2 | Interpretation |
|---|---:|---|
| 14-1.R00-2A | 0.854 | Strongest current result; requires stability and baseline comparison |
| 15-0.000-1M | 0.844 | Strong current result; absolute errors remain scale-dependent |
| 14-0.000-1M | 0.836 | Strong current result; requires regime and outlier review |
| 16390 | 0.785 | Strong current result; interval coverage remains imperfect |
| 16175 | 0.116 | Weak skill despite a long record |
| 13-0.000-1M | -1.337 | No usable skill under this split |

These values supersede earlier random-split results. They describe a common static/temporal baseline, not a climate-forced basin model, and do not establish basin-wide or 1-3 month dry-spell forecasting skill.

## 3. Audit Findings

### 3.1 Corrected findings

The following implementation issues were corrected in the current pipeline:

- Random within-series validation was replaced by a chronological 80/20 holdout.
- Prediction generation was restricted to the validation dates stored with each model.
- Published profile `r2` values now come from calibration R2 rather than RMSE.
- Antecedent rolling windows now reset within each gauge after explicit gauge/date sorting.
- Current discharge was removed from depletion, runoff-coefficient, and baseflow-ratio calculations used as antecedent features.
- Precursor analysis now computes the previous row in the sorted gauge series rather than relying on integer index arithmetic.
- The trainer now selects shared features by network-wide coverage, allowing all 38 gauges to run without imputing absent climate forcing.
- Verified CA-discharge station coordinates are used for the all-gauge error map; exact duplicate station rows are removed and recorded rather than silently plotted twice.

### 3.2 Remaining scientific risks

These risks are not reasons to discard the work; they define the next audit boundary.

1. **Single chronological holdout.** One endpoint split can be sensitive to the last years, regime shifts, missing records, and unusual extremes. It is a useful first gate, not a complete uncertainty estimate.
2. **Small event sample.** Dry-spell labels are rare relative to normal months. Accuracy will be misleading; precision, recall, PR-AUC, event recall, false-alarm rate, and lead-time distributions are required.
3. **Station-climate selection bias.** The six climate-enabled gauges are not necessarily representative of all 38 gauges. A model trained on station-rich gauges cannot be assumed to transfer to ungauged basins.
4. **Static attribute interpretation.** Area, elevation, terrain, land cover, glacier fraction, and basin morphology explain regime differences but do not supply time-varying water forcing by themselves.
5. **Regulated-flow confounding.** Reservoir operations, diversions, withdrawals, and return flows may break a simple precipitation-to-discharge relationship. These effects should be flagged where observations or metadata permit.
6. **Target definition sensitivity.** A Q25 threshold describes relative low flow at a gauge. It is not automatically equivalent to drought impact, ecological low flow, water-supply shortage, or a basin-wide dry spell.
7. **Quantile calibration.** The current all-gauge p10-p90 intervals cover about 79.6% of held-out records. They should not be described as calibrated 90% intervals until recalibration and out-of-sample coverage checks succeed.

## 4. Data and Evidence Inventory

### 4.1 Time-varying observations and derived features

| Dataset or feature group | Current availability | Audit use | Main limitation |
|---|---:|---|---|
| Monthly discharge | 6,739 records / 38 gauges | Primary response and hydrologic benchmark | Record length and completeness vary by gauge |
| Station-derived precipitation and temperature | 1,832 records / 6 gauges | Climate forcing and antecedent water input | Sparse spatial coverage |
| Core engineered features | 68 columns | Regime, seasonal, climate, terrain, land cover, dry-spell labels | Some values are estimated or placeholders |
| All-gauge model baseline | 17 shared features | Comparable modelling across all 38 gauges | Excludes sparse climate predictors |
| Antecedent features | 92 columns after regeneration | Prior discharge/precipitation state and stress diagnostics | Must remain target-safe and split-aware |
| Upstream station contributions | Available through integration pipeline | Spatial forcing and station influence audit | Need coverage and representativeness review |
| Dry-spell labels | Derived monthly classification | Classification target and event analysis | Thresholds need sensitivity and impact validation |

### 4.2 Static basin attributes

The current feature engineering includes or can join:

- Drainage area, mean/minimum/maximum elevation, slope, aspect, TPI, TRI, and roughness.
- Land-cover fractions including forest, grassland, shrubland, cropland, urban, water, and bare surfaces.
- Glacier and permafrost fields, which are currently documented as placeholders in the feature guide and must not be interpreted as measured coverage until sourced and validated.
- Basin mean flow and flow-regime quantiles, which are useful for normalization but can leak information if calculated using the entire observation period before a temporal split.

### 4.3 BasinATLAS and routing evidence

`GEODATA/uzbekistan_basinatlas_v10` provides:

- Levels 01-12 of complete basin geometries intersecting Uzbekistan.
- PFAF hierarchy and adjacent-level feature links.
- Downstream links, terminal sinks, and outside-selection routing targets.
- `UZB_KM2` and `UZB_PCT` area fields derived using EPSG:6933.
- 299-column attribute tables, with reduced shapefile subsets for format compatibility.

The BasinATLAS documentation reports complete national tiling at every level and strict parent-child nesting in the standard format. It also shows that transboundary and endorheic routing is common. Basin-scale analysis must therefore retain `NEXT_DOWN`, `ENDO`, `COAST`, `MAIN_BAS`, and outside-selection routing flags rather than assuming every basin drains through a national outlet.

## 5. Proposed Scientific Analysis Design

### Track A: Gauge hydrology benchmark

The gauge benchmark should be the reference experiment for every later basin-scale model.

#### Targets

Evaluate separately:

- Continuous next-month discharge: `Q(t+1)`.
- Continuous one- to three-month lead discharge: `Q(t+h)` for `h` in `{1, 2, 3}`.
- Binary dry spell at lead `h`.
- Severity class at lead `h`, only if each class has adequate event counts.

Do not combine current-month classification with future-month warning in one metric.

#### Baselines

Every candidate model should be compared with:

1. Seasonal climatology by gauge and calendar month.
2. Persistence: `Q(t)` or the most recent valid flow.
3. Prior-3-month mean.
4. Seasonal climatology plus antecedent anomaly.
5. A regularized linear model.
6. A tree ensemble only after the baselines are recorded.

A model is useful only when it improves over a relevant baseline on the same held-out dates.

#### Validation

Use rolling-origin evaluation with a final untouched test period. For each fold:

- Fit scalers, quantiles, climatologies, feature selectors, and models on training dates only.
- Apply the fitted transformations to the validation dates.
- Keep all horizons and gauges grouped by date and gauge.
- Report the number of events and non-events in every fold.
- Use blocked gaps where a feature window or operational data latency requires one.

The current chronological 80/20 split remains a minimum regression check, not the final evaluation protocol.

### Track B: Dry-spell event and early-warning audit

For each gauge and lead time, report:

- Event count and event rate.
- Recall/sensitivity for dry-spell months.
- Precision and false-alarm rate.
- PR-AUC and ROC-AUC, with PR-AUC treated as primary for rare events.
- Brier score and reliability curve for probabilities.
- Event-based recall: fraction of distinct dry-spell episodes detected at least once.
- Median warning lead, earliest warning, and missed-event rate.
- Performance by season and by severity.

Use an event definition that prevents every low-flow month in a long episode from being counted as a separate success. Define episode separation and minimum duration before scoring.

Threshold sensitivity should compare, at minimum:

- Q10, Q20, Q25, and Q30 discharge thresholds.
- P10, P20, P25, and P30 precipitation thresholds.
- Compound conditions versus single-indicator conditions.
- Gauge-relative thresholds versus regionally standardized thresholds.

### Track C: Basin-attribute hydrologic regime analysis

Use static attributes first for interpretation, clustering, and transfer stratification, not as a substitute for forcing data.

Recommended regime groups:

- Snowmelt/glacier influenced versus rain dominated.
- High versus low elevation.
- Large versus small drainage area.
- High versus low baseflow persistence.
- Endorheic versus externally draining basins.
- High versus low terrain ruggedness/slope.
- Land-cover and human-influence classes where evidence exists.

For each group, compare:

- Seasonal hydrograph shape.
- Flow duration curve and low-flow quantiles.
- Recession slope and recovery time.
- Dry-spell frequency, duration, and severity.
- Climate sensitivity and model residuals.
- Coverage and calibration of prediction intervals.

Use the basin attributes to explain heterogeneity in model skill. Avoid presenting feature importance as causal attribution.

### Track D: Basin-scale transfer and ungauged basins

The recommended transfer sequence is:

1. Join each gauge to its contributing BasinATLAS basin using a documented spatial and hydrologic rule.
2. Verify gauge location, outlet placement, drainage area, `HYBAS_ID`, level, and downstream link.
3. Build basin static-attribute tables at one selected level, retaining parent and routing identifiers.
4. Aggregate available climate products over the same basin geometry and area convention.
5. Train a pooled or hierarchical model using gauge observations and static basin attributes.
6. Validate by holding out gauges or basin groups, not only random rows.
7. Report transfer skill separately from within-gauge temporal skill.
8. Produce predictions only for basins with documented forcing coverage and a stated uncertainty category.

A level-12 basin is not automatically the correct hydrologic response unit. Select the working level based on gauge drainage area, forcing resolution, routing use, and intended decision scale. Preserve cross-level links so the analysis can be aggregated without retracing geometry.

## 6. Feature Governance and Leakage Controls

Every feature should have a machine-readable or documented classification:

| Class | Examples | Permitted use |
|---|---|---|
| Static known before modelling | Area, elevation, terrain, land cover | Train and transfer, with source date recorded |
| Historical observed | Prior Q, prior P, prior temperature | Only values available before forecast issue time |
| Current observed | Current-month Q or P | Only when the forecast is explicitly issued after current observation |
| Future-derived | Target-month Q, future dry-spell flag, full-period quantile | Never as a predictor |
| Full-period statistic | All-history Q25, all-history climatology | Replace with training-period fit for predictive evaluation |
| Estimated/placeholder | Proxy AET, placeholder glacier/permafrost | Keep labelled; test sensitivity and exclude when unsupported |

Required checks:

- Feature timestamp is earlier than the target timestamp for every forecast horizon.
- Rolling features reset by gauge and are calculated after gauge/date sorting.
- Training-only statistics are persisted with the model.
- No target or target-derived field enters `X`.
- Missingness is reported by gauge, date, feature, and forecast horizon.
- Static joins preserve one row per basin and one documented gauge-to-basin relation.
- Duplicate gauge/date and basin/time records fail validation.

## 7. Hydrologic Diagnostics Required Before Prediction Claims

### Water balance and forcing checks

Where forcing is available, compare precipitation, temperature, AET, runoff products, and discharge using matched basin geometry and common periods. Report:

- Unit conversion and area convention.
- Complete-year and complete-month counts.
- Precipitation and runoff bias.
- Seasonal volume bias.
- Correlation and lagged correlation.
- Snowmelt timing error where temperature/elevation data support it.
- Flow volume bias and runoff ratio.

TerraClimate or ERA5-Land runoff should be treated as a forcing or diagnostic product, not as routed observed discharge. Product agreement alone does not validate either product.

### Flow regime checks

For each gauge and basin group:

- Plot monthly hydrographs and annual flow volume.
- Calculate flow duration curves.
- Estimate recession constants using only valid recession segments.
- Compare Q10/Q25/Q50/Q75/Q90 by period.
- Check for change points, regulation periods, and suspicious abrupt shifts.
- Separate missing observations from true zero flow.

### Dry-spell checks

For every labelled event:

- Retain the component indicators that caused the label.
- Record the local threshold and reference period.
- Distinguish isolated months from episodes.
- Compare the label with observed discharge anomaly and climate anomaly.
- Test label stability under threshold perturbations.
- Avoid using the label components as contemporaneous predictors of the same label.

## 8. Deliverables and Acceptance Criteria

### Review deliverables

1. Data inventory with source, units, period, coverage, and missingness.
2. Gauge-to-basin crosswalk with spatial and hydrologic checks.
3. Feature dictionary with availability time and leakage class.
4. Gauge benchmark report with chronological and rolling-origin results.
5. Dry-spell event report with episode-based metrics.
6. Basin-regime report using BasinATLAS attributes.
7. Transfer-validation report for held-out gauges or basin groups.
8. Model artifact manifest containing feature list, training period, validation periods, source hashes, and calibration results.
9. Reproducible pipeline commands and regression tests.

### Minimum acceptance criteria

A model may be described as a validated forecast only when:

- It beats persistence and seasonal climatology on the untouched test period.
- The test period is chronologically after training for forecasting claims.
- Dry-spell results include PR-AUC, precision, recall, false alarms, and episode recall.
- Interval coverage is reported on held-out data and is recalibrated if materially below nominal coverage.
- Performance is reported by gauge, season, lead time, and basin regime.
- No target-derived or future-derived predictor is present.
- Missing climate coverage and transfer limits are visible in the published result.
- The claim is narrowed when results vary materially across gauges.

## 9. Execution Plan

### Phase 1: Reproducible gauge benchmark

- Freeze current source and output hashes.
- Add rolling-origin folds and a final test period.
- Recompute baselines and candidate models at 1-, 2-, and 3-month leads.
- Run threshold sensitivity for dry-spell labels.
- Recalibrate intervals using training-only residuals or conformal calibration.

### Phase 2: Gauge-to-basin and regime audit

- Build and validate the gauge-to-BasinATLAS crosswalk.
- Select working basin levels by outlet and drainage-area agreement.
- Join static attributes and routing metadata.
- Produce regime clusters and skill stratification.

### Phase 3: Climate expansion

- Add gridded precipitation and temperature for all gauge basins.
- Add snow, glacier, soil-moisture, evapotranspiration, and runoff diagnostics where available.
- Preserve product identity and common-period masks.
- Compare products before selecting a forcing set.

### Phase 4: Transfer to available basins

- Train pooled or hierarchical models with gauge holdouts.
- Evaluate spatial transfer separately from temporal forecasting.
- Assign uncertainty tiers based on forcing coverage, attribute similarity, gauge distance, and regime membership.
- Publish only basin predictions with traceable geometry, forcing, model version, and uncertainty.

## 10. Current Reproducibility Commands

The corrected gauge workflow is:

```sh
python PIPELINES/train_gauge_specific_ensemble.py
python PIPELINES/generate_gauge_predictions.py
python PIPELINES/generate_gauge_case_study.py
python PIPELINES/antecedent_dry_spell_analysis.py
```

The current generated artefacts are under `PUBLISHED/data/case-studies/`:

- `gauge_ensemble_models.pkl`
- `gauge_quantile_predictions.csv`
- `gauge_prediction_summary.csv`
- `gauge_uncertainty_report.json`
- `gauge_profiles.json`
- `antecedent_discharge_features.csv`
- `dry_spell_precursor_analysis.csv`
- `dry_spell_prediction_guide.md`
- `dry_spell_error_report.md`
- `dry_spell_error_atlas.png`
- `dry_spell_gauge_error_map.png`
- `dry_spell_basin_context_map.png`

These commands reproduce the corrected baseline. They do not yet implement the full rolling-origin benchmark, basin crosswalk audit, or spatial transfer experiment described above.

## 11. Bottom Line

The project is ready for a rigorous gauge-anchored hydrologic study and a structured basin-transfer programme. It is not yet ready to claim operational dry-spell forecasting across all available basins.

The next scientifically decisive step is not adding more model complexity. It is establishing a leakage-controlled benchmark with explicit baselines, multiple forecast horizons, episode-based dry-spell metrics, calibrated uncertainty, and a validated gauge-to-basin crosswalk. Basin attributes can then explain regime differences and support spatial transfer, while time-varying climate and hydrologic forcings provide the information required for actual early warning.

## 6. Post-review corrections (2026-09-17)

Recorded during the repository review of this work:

- **Climate gap-filling is station-based, not WorldClim/EClim.** The missing-observation
  estimates in the current feature table come from aggregating upstream meteorological
  stations (`aggregate_basin_climate.py`, distance-weighted), covering 6 of 38 gauges
  (27.2% of records). WorldClim/EClim *grids* are not used by these pipelines; WorldClim
  appears elsewhere in the project only as frozen climatological normals. Any claim that
  missing forcing was filled from WorldClim/EClim grids must wait until that extraction
  is actually implemented.
- **`basin_mean_q_m3s` is a gauge fingerprint under spatial CV.** The gauge-level
  chronological holdouts are clean, but the spatial cross-validation (splits by gauge)
  reports `basin_mean_q_m3s` as the top feature. A per-gauge long-term mean identifies
  the gauge rather than explaining discharge; its 0.38 importance in
  `discharge_cv_results.json` should be read as a limitation of that spatial experiment,
  not as a physical driver. The JSON carries the same caveat in its `note` field.
- **Fitted model binaries are not committed.** The `.pkl` artefacts are reproducible from
  `npm run discharge:*` pipelines; only recipes, metrics (JSON) and tabular results are
  tracked.
