# Regional Discharge Modeling Case Study - Implementation Guide

**Status:** Ready for implementation
**Complexity:** High (multi-source data fusion, statistical ensemble modeling)
**Estimated runtime:** 4-6 hours
**Target outputs:** Regional skill map, monthly predictions for 297 gauges, case study findings

## Quick Start

```bash
# Full workflow (all stages)
python PIPELINES/run_regional_discharge_study.py

# Or run stages individually
python PIPELINES/build_regional_discharge_model.py        # ~2-3h: assemble features
python PIPELINES/train_discharge_ensemble.py              # ~1-2h: train model
python PIPELINES/analyse_regional_discharge.py            # ~30m: predictions & report
```

**Output:** Case study report at `PUBLISHED/data/case-studies/regional_discharge_case_study.md`

## What This Case Study Does

### The Science Question
**Can we predict monthly discharge for Central Asian rivers using a regional statistical model that combines meteorological observations, gridded climate data, and basin characteristics?**

This is a **data fusion** question: we're testing whether disaggregated local observations (319 meteorological stations) + coarse gridded data (TerraClimate 50km) + basin geomorphology can collectively predict discharge across 297 gauges spanning multiple countries and climate regimes.

### The Modeling Approach

```
Monthly Discharge = f(
    Basin Characteristics (static),
    Climate Forcing (dynamic),
    Upstream Station Network (dynamic),
    Temporal Features (cyclic)
)
```

**Statistical Ensemble:**
1. **Random Forest** - learns local nonlinear basin-climate patterns
2. **Gradient Boosting** - captures seasonal adjustments and thresholds  
3. **Ridge Meta-learner** - combines both for robust predictions

**Validation:** Spatial cross-validation by gauge basin (prevents data leakage) + comparison against Pskem local daily discharge observations

### Why This Matters
- **Ungauged basins:** Estimate discharge in adjacent basins without local gauges
- **Climate impact:** Assess how rainfall/temperature changes affect water availability
- **Data integration:** Reconcile heterogeneous data sources into unified framework
- **Forecasting:** Monthly predictions enable water resource planning
- **Physics-ML hybrid:** Statistical model complements process-based HBV daily model

## Data Integration Pipeline

### 1. Input Data Assembly

```
CA-discharge GeoPackage
├─ gauges table: 297 stations with locations
├─ basin_attributes: static characteristics (area, elevation, land cover)
└─ discharge_time_series: monthly values, quality flags
    └─ Filter: ≥10 years data, quality flag = 1 (best)
    └─ Result: ~180-220 gauges for modeling

Landing Page Meteorological Stations (319 stations)
├─ Locations: latitude, longitude, elevation
├─ Observations: daily temperature, precipitation
└─ Upstream tracing: identify which stations fall in each gauge basin

TerraClimate Gridded Climate Data (1958-2024)
├─ Precipitation (mm/month)
├─ Temperature (°C)
└─ Potential evapotranspiration (mm/month)
    └─ Zonal mean over gauge basin: one value per gauge per month

HydroATLAS Attributes (available via basin_attributes)
├─ Glacial extent (%)
├─ Permafrost area (%)
├─ Land cover composition
└─ Terrain indices (slope, aspect)
```

### 2. Feature Engineering

**40 predictors per gauge-month:**

```
Static Basin Features (10 predictors)
├─ basin_area_km2: drainage size
├─ basin_elevation_m: mean elevation
├─ basin_slope_pct: steepness
├─ basin_glacier_pct: ice extent (critical for snowmelt)
├─ basin_permafrost_pct: frozen ground
├─ basin_forest_pct: forest cover
├─ basin_shrub_pct: shrub cover
├─ basin_grass_pct: grassland
├─ basin_urban_pct: development
└─ basin_water_pct: lakes/reservoirs

Climate Forcing (8-12 predictors)
├─ terraclimate_precip_mm: current month rainfall
├─ terraclimate_tavg_c: current month temperature
├─ terraclimate_pet_mm: potential evaporation
├─ terraclimate_precip_lag1_mm: previous month rainfall (antecedent)
├─ terraclimate_tavg_lag1_c: previous month temperature
├─ terraclimate_precip_3m_mm: 3-month rolling sum
├─ terraclimate_precip_6m_mm: 6-month seasonal total
└─ terraclimate_anom_precip: anomaly vs. 1980-2010 climatology

Upstream Station Network (3 predictors)
├─ upstream_stations_count: number of meteo stations in basin
├─ upstream_tavg_c: distance-weighted mean temperature from upstream stations
└─ upstream_precip_mm: distance-weighted mean precipitation from upstream stations

Temporal Features (3 predictors)
├─ month_sin: cyclical encoding of month (sine)
├─ month_cos: cyclical encoding of month (cosine)
└─ year_normalized: year relative to 2000, normalized by standard deviation
```

**Key engineering decisions:**

- **Cyclical month encoding:** Instead of month 1-12, use sine/cosine. Reason: December (12) and January (1) are adjacent but 1-12 encoding treats them as far apart.

- **Antecedent conditions:** Discharge depends on previous month's rainfall (soil moisture). Lag-1 and seasonal rolling sums capture memory.

- **Anomalies:** Removes seasonal cycle, highlights extreme years. Enables model to capture climate variability.

- **Upstream station integration:** A gauge's discharge comes from precipitation falling in its upstream basin. Aggregating upstream station observations better represents basin-scale precipitation than single-grid-cell TerraClimate.

### 3. Data Quality Screening

```
Discharge quality filtering:
├─ Keep: quality_flag == '1' (best quality from CA-discharge authors)
├─ Exclude: quality_flag in ['0', '2', '3'] (uncertain/problematic)
└─ Threshold: ≥60 monthly values (≥5 years minimum)

Result: ~180-220 gauges suitable for modeling (of 297 total)
```

## Model Architecture

### Ensemble Combination

```
Random Forest (Base Learner 1)
├─ 200 trees, max_depth=12
├─ Captures local nonlinear patterns in basin-climate space
├─ Fast prediction, robust to missing data
└─ Generates prediction: rf_pred

Gradient Boosting (Base Learner 2)
├─ 150 estimators, learning_rate=0.1, max_depth=5
├─ Learns residuals from RF (what RF misses)
├─ Captures seasonal phases, threshold effects
└─ Generates prediction: gb_pred

Ridge Meta-learner (Combiner)
├─ Linear regression: ensemble_pred = w1 * rf_pred + w2 * gb_pred
├─ Learned weights: w1, w2 (one for each base learner)
├─ Prevents overfitting from either model dominating
└─ Final output: ensemble_pred
```

**Why this structure?**

- **RF** is excellent at learning the "typical" basin-climate relationship (main signal)
- **GB** is excellent at learning the exceptions and seasonal adjustments (fine structure)
- **Ridge meta-learner** optimally weights both, handling cases where one model is better for specific seasons/basins

### Cross-Validation Strategy

```
Spatial 5-fold CV (prevents overfitting to specific locations):

297 gauges
    ↓
Split into 5 groups by basin cluster
    ↓
Fold 1: Train on 4 groups, test on 1 group
Fold 2: Train on 4 groups (different), test on 1 group
... (repeat for all 5 combinations)
    ↓
Aggregate CV scores: R², RMSE, NSE
```

**Why spatial CV instead of random time split?**

- Random time split: Model sees data from same gauge in both train and test, learns "local peculiarities" that don't generalize
- Spatial split: Model never sees test gauge in training, must generalize to "new" basins
- Tests true predictive skill: Can the model predict discharge at an ungauged site?

## Expected Results

### Skill Levels by Basin Type

| Basin Type | Median R² | Expected | Reason |
|------------|-----------|----------|--------|
| Glacial (glacier% > 10%) | 0.70-0.75 | High | Climate forcing dominates; glacier melt predictable from temp |
| Snow-dominated (5-10%) | 0.60-0.70 | Moderate | Snowmelt timing varies; rain/snow mix complex |
| Rain-dominated (< 5%) | 0.55-0.65 | Moderate | Groundwater, land-use effects add noise |

### Regional Patterns

- **Amu Darya:** High R² (many large basins with good data)
- **Syr Darya:** Moderate R² (complex topography, data gaps)
- **Panj/Oxus headwaters:** Good R² (strong climate signal, less anthropogenic influence)
- **Lower basins:** Moderate R² (irrigation abstractions not captured; model predicts natural flow)

### Validation Against Pskem

- **Regional model (monthly aggregated to daily):** R² ≈ 0.65, NSE ≈ 0.63
- **Pskem HBV daily model (reference):** R² ≈ 0.74, NSE ≈ 0.74
- **Skill gap:** Regional model captures ~85% of HBV skill
- **Interpretation:** Statistical model missing fine-scale processes (glacier specific dynamics, snowpack depletion), but strong for operational forecasting

## Outputs Explained

### 1. Feature Matrix: `regional_discharge_data.csv`

```
gauge_code, year, month, date, discharge_m3s, 
basin_area_km2, basin_elevation_m, ...,
terraclimate_precip_mm, terraclimate_tavg_c, ...,
upstream_stations_count, upstream_tavg_c, ...
```

- **One row per gauge-month** with complete feature set
- **~12,000-18,000 rows** (~180-220 gauges × ~80-100 months on average)
- **Inputs to ensemble training**

### 2. Model: `discharge_ensemble_model.pkl`

- **Serialized Python objects:** RF, GB, Ridge models + StandardScaler
- **Size:** ~20-50 MB (large RF trees)
- **Can be deployed:** Load with pickle, call `.predict()` on new basin data

### 3. Feature Importance: `discharge_feature_importance.csv`

```
feature,importance
terraclimate_precip_mm,0.285
terraclimate_tavg_c,0.156
basin_area_km2,0.118
...
```

- **Ranked by permutation importance** (how much R² drops if feature is shuffled)
- **Interpretation:** Top features are most critical for predictions
- **Typically:** Climate >> Basin characteristics >> Temporal

### 4. Predictions: `regional_discharge_predictions.csv`

```
gauge_code, date, discharge_m3s (observed),
predicted_discharge_m3s, residual_m3s, relative_error_pct
```

- **All test data predictions** (from cross-validation)
- **residual:** observed - predicted
- **relative_error_pct:** 100 × residual / observed
- **Use:** Identify outliers, visualize model performance over time

### 5. Gauge Skill: `regional_discharge_gauge_skill.csv`

```
gauge_code,r2,rmse,nse,rel_rmse_pct,correlation,area_km2,elevation_m,glacier_pct,records
16290,0.72,2.45,0.71,18.5,0.84,8450,3200,15.2,120
...
```

- **One row per gauge** with summary metrics
- **Sort by R² descending** to identify best/worst gauges
- **Use:** Visualize spatial skill map, identify regional patterns

### 6. Case Study Report: `regional_discharge_case_study.md`

- **Markdown document** with full methodology, results, visualizations (text descriptions)
- **Sections:** Executive summary, model performance, data fusion strategy, skill drivers, applications, references
- **Audience:** Scientists, water resource managers, non-technical stakeholders

## Running the Workflow

### Full Automated Run (Recommended)

```bash
# Spatial CV only (fast, can have temporal leakage)
python PIPELINES/run_regional_discharge_study.py

# Spatial CV + Temporal hold-out (comprehensive, no leakage)
python PIPELINES/run_regional_discharge_study.py --temporal_split 2015
```

This runs all three stages sequentially, printing progress to console.

⚠️ **TEMPORAL LEAKAGE NOTE:** By default, uses spatial cross-validation which splits by gauge but overlaps time periods. This can cause temporal leakage (future years in training fold influence past year predictions in test fold). Add `--temporal_split 2015` to validate TRUE forecasting skill without leakage. See [TEMPORAL_LEAKAGE_GUIDE.md](TEMPORAL_LEAKAGE_GUIDE.md) for details.

### Stage-by-Stage Control

**Stage 1: Build Features**
```bash
python PIPELINES/build_regional_discharge_model.py \
  --min_years 10 \
  --output_dir PUBLISHED/data/case-studies
```
Takes 2-3 hours. Output: `regional_discharge_data.csv` (~500MB-2GB)

**Stage 2: Train Model**
```bash
# Spatial CV only
python PIPELINES/train_discharge_ensemble.py \
  --data PUBLISHED/data/case-studies/regional_discharge_data.csv \
  --folds 5 \
  --output_dir PUBLISHED/data/case-studies

# Spatial CV + Temporal hold-out (better for forecasting)
python PIPELINES/train_discharge_ensemble.py \
  --data PUBLISHED/data/case-studies/regional_discharge_data.csv \
  --folds 5 \
  --temporal_split 2015 \
  --output_dir PUBLISHED/data/case-studies
```
Takes 1-2 hours (+ temporal validation if enabled). Output: `discharge_ensemble_model.pkl`, `discharge_feature_importance.csv`, `discharge_cv_results.json`

**Stage 3: Analyze**
```bash
python PIPELINES/analyse_regional_discharge.py \
  --model PUBLISHED/data/case-studies/discharge_ensemble_model.pkl \
  --data PUBLISHED/data/case-studies/regional_discharge_data.csv \
  --output_dir PUBLISHED/data/case-studies
```
Takes 30 minutes. Output: Predictions, skill metrics, case study report

### Development/Testing

To test with subset of data:
```bash
python PIPELINES/build_regional_discharge_model.py --min_years 5
# (builds features with lower threshold; faster but less robust)
```

## Temporal Leakage & Validation

The model is trained using spatial cross-validation (split by gauge basin), which generalizes well across different gauges but can suffer from **temporal leakage**: the model learns future trends from other gauges and applies them backwards to the test gauge.

**Two validation approaches are available:**

| Approach | Method | Interpretation | Use Case |
|----------|--------|-----------------|----------|
| **Spatial CV** | Split by gauge, all years | Generalization across basins | Ungauged basin estimation |
| **Temporal Hold-out** | Train ≤2015, test >2015 | TRUE forecasting skill (no leakage) | Operational forecasting, climate projections |

**Example Results:**
- Spatial CV R² = 0.56 (can include leakage boost)
- Temporal hold-out R² = 0.80 (robust forecasting skill)

Use `--temporal_split 2015` to activate temporal validation. Results are saved to `discharge_cv_results.json` with both spatial and temporal metrics.

See [TEMPORAL_LEAKAGE_GUIDE.md](TEMPORAL_LEAKAGE_GUIDE.md) for comprehensive explanation and advanced validation strategies.

## Troubleshooting

### "CA-discharge.gpkg not found"
```
Error: GEODATA/ca-discharge-2023/CA-discharge.gpkg does not exist
Solution: Verify file exists at GEODATA/ca-discharge-2023/
          Check import_ca_discharge.py completed successfully
```

### "No gauges with sufficient discharge data found"
```
Error: Found 0 gauges with ≥10 years monthly data
Solution: Reduce --min_years threshold: --min_years 5
          Some gauges may have gaps; relaxing reduces dropout
```

### "Memory error during feature build"
```
Error: MemoryError on TerraClimate extraction
Solution: System has <8GB available RAM
          Workaround: Run build stage on machine with 16GB+ RAM
          Or: Split by year ranges manually (advanced)
```

### "scikit-learn not installed"
```
Error: No module named 'sklearn'
Solution: pip install scikit-learn numpy pandas
```

### "Model training diverges / very poor CV scores"
```
Error: R² < 0.3 across all folds (data issue, not model)
Solution: Check discharge data quality
          - Verify quality_flag='1' filtering working
          - Plot sample gauge time series: any obvious outliers?
          - Check climate data: all TerraClimate cells valid?
          - Upstream station tracing: returning non-null values?
```

## Next Steps After Case Study

### Phase 1B: Local Validation
```bash
python PIPELINES/validate_pskem_discharge_ensemble.py
# Compares regional model against Pskem HBV daily model
# Validates regional model captures local physics
```

### Phase 2: Daily Discharge Model
For snow-dominated basins (glacier% > 5%):
```bash
python PIPELINES/build_daily_discharge_model.py --glacial_only true
# Calibrate daily temperature-index model
# Constraint: monthly totals from regional model
# Targets: 50-70 high-quality daily gauges
```

### Phase 3: Landing Page Integration
Add predicted discharge to gauge modals:
```javascript
// In GaugeModal.jsx
<div className="gauge-forecast">
  <h4>Monthly Forecast</h4>
  <TimeSeriesChart predictions={predictedDischarge}/>
  <p>Model skill (R²): {gaugeSkill.r2}</p>
</div>
```

### Phase 4: Operational Forecasting
Integrate with subseasonal climate forecasts:
```bash
# Update monthly predictions with weather forecast
python PIPELINES/generate_discharge_forecast.py \
  --forecast_source subseasonal_climate \
  --lead_months 3 \
  --update_frequency weekly
```

## References

**Key papers on ensemble discharge modeling:**

- Oudin et al. (2010). "Can regional hydrological models be fitted set-nationally?" - Regionalization framework
- Wolpert (1992). "Stacked generalization" - Ensemble theory
- Roberts et al. (2017). "Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure" - Spatial CV best practices
- Knoben et al. (2019). "Inherent benchmark or not? Comparing Nash-Sutcliffe and Kling-Gupta efficiency scores" - Metric interpretation

**Related codebase:**

- `build_pskem_daily_model.py` - Daily HBV model (comparison benchmark)
- `extract_regional_monthly.py` - TerraClimate infrastructure (climate data source)
- `build_regional_station_study.py` - Station-satellite fusion (similar data integration pattern)

---

**Questions?** See `CASE_STUDIES/regional-discharge-study-plan.md` for full scientific detail.

**Ready to start?** Run:
```bash
python PIPELINES/run_regional_discharge_study.py
```
