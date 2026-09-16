# Regional CA-Discharge Monthly Modeling Case Study

**Objective:** Develop a data-driven regional discharge model for all CA-discharge gauges, demonstrating data fusion of meteorological stations, gridded climate data, and basin characteristics to predict monthly discharge across Central Asia.

**Narrative:** Reconcile heterogeneous discharge observations (CA-discharge), local meteorological stations (Pskem/Chirchik), and regional climate forcing (TerraClimate/ERA5) into a unified predictive framework. Assess regional model skill and identify local vs. basin-scale drivers.

**Scope:** 297 CA-discharge gauges across Central Asia, monthly timescale, with selected daily sites as phase-2 expansion.

## Data Sources & Integration

### 1. Target Variable: Monthly Discharge
- **Source:** CA-discharge GeoPackage (`discharge_time_series` table)
- **Coverage:** CODE identifier, date (monthly), value (m³/s)
- **Quality filter:** Gauges with ≥10 years monthly data, quality_flag='1'
- **Expected:** ~180-220 gauges with sufficient temporal coverage
- **Validation set:** Pskem/Chirchik local daily discharge records (phase-1 validation)

### 2. Basin Characteristics (Static Predictors)
- **Source:** CA-discharge `basin_attributes` table + HydroATLAS

**Key attributes:**
- Area (km²) - drainage basin size
- Elevation (m) - mean, min, max
- Slope (%) - basin gradient
- Glacial extent (%) - fraction ice-covered (critical for spring snowmelt)
- Permafrost area (%) - frozen ground regions
- Land cover (%) - forest, shrub, grass, urban, water, ice
- Precipitation regime (monthly mean climatology)
- Temperature regime (monthly mean climatology)

**Processing:**
- Query basin_attributes for each gauge
- Normalize by basin area
- Compute seasonal indices (monsoon vs. monsoon-less)
- Flag high-altitude/glacial vs. low-altitude/pluvial regimes

### 3. Climate Forcing (Dynamic Predictors)
- **Primary:** TerraClimate monthly (1958-2024)
  - Precipitation (mm)
  - Temperature (°C) - mean, min, max
  - PET (mm) - potential evapotranspiration
- **Backup/validation:** ERA5 monthly reanalysis
- **Lead times:** 0-lag (concurrent month), 1-month lag (antecedent conditions)

**Processing:**
- Extract zonal statistics over gauge basin
- Compute anomalies relative to 1980-2010 climatology
- Create cumulative features (3-month, 6-month seasonal totals)
- Compute soil moisture proxy: precipitation - PET

### 4. Upstream Station Network
- **Meteorological stations:** 319 stations from integrated landing page layer
- **Tracing:** Identify all meteo stations within basin or contributing upstream
- **Features from upstream stations:**
  - Air temperature (mean daily, min, max)
  - Precipitation (daily total, rain/snow fraction)
  - Snowfall depth (if available)
  - Number of upstream stations contributing to each gauge

**Processing:**
- For each gauge, query HydroSHEDS network to identify upstream terrain
- Intersect meteorological station locations with upstream basin
- Average upstream station data weighted by distance-to-gauge
- Handle missing data by falling back to gridded TerraClimate

## Predictive Model Architecture

### Statistical Ensemble Approach

**Primary Model:** Random Forest + Gradient Boosting on basin characteristics + climate

**Model structure:**

```
Monthly Discharge = f(Basin Characteristics, Climate, Upstream Data, Time)

Features (30-40 predictors):
├─ Static Basin Features (12-15)
│  ├─ Area, elevation, slope, glacier%, permafrost%
│  ├─ Land cover fractions
│  └─ Basin shape indices
├─ Climate Forcing (12-18)
│  ├─ Current month: precip, temp, PET
│  ├─ Previous 1-3 months: accumulated precip, mean temp
│  ├─ 6-month season: accumulated precip
│  └─ Anomalies relative to climatology
├─ Upstream Observations (4-6)
│  ├─ Upstream station mean temp
│  ├─ Upstream station total precip
│  ├─ Snowfall fraction (if available)
│  └─ Number of upstream stations
└─ Temporal Features (2-4)
   ├─ Month-of-year (cyclical encoding)
   ├─ Climate phase (El Niño / La Niña if available)
   └─ Trend (year, normalized)
```

**Training:**
- Random Forest: 200-500 trees, max_depth=12, min_samples_leaf=5
- Gradient Boosting: 100-200 estimators, learning_rate=0.1, max_depth=4-6
- Stacking ensemble: Linear meta-learner combining both models
- Cross-validation: 5-fold spatial (group by basin, not by date)

**Hyperparameter tuning:**
- Grid search on training subset (80% data)
- Validation on holdout (20% data, recent years)
- Monitor: R², RMSE, NSE (Nash-Sutcliffe Efficiency)

### Uncertainty Quantification
- Prediction intervals via quantile regression forests
- Separate models for 10th, 50th (median), 90th percentiles
- Bootstrap resampling to assess parameter uncertainty

## Case Study Workflow

### Phase 1: Regional Monthly Model (Primary)

**1. Data Assembly**
```python
python PIPELINES/build_regional_discharge_model.py \
  --gauges all \
  --min_years 10 \
  --climate_source terraclimate \
  --include_upstream_stations true
```

Outputs:
- `regional_discharge_data.csv` - 40 features × 10,000-15,000 records (all gauges, monthly)
- `gauge_metadata.json` - basin characteristics, data availability, quality flags
- `upstream_stations_network.json` - mapping of upstream meteo stations to each gauge

**2. Model Training & Validation**
```python
python PIPELINES/train_discharge_ensemble.py \
  --data regional_discharge_data.csv \
  --test_size 0.2 \
  --folds 5 \
  --optimize_hyperparameters true
```

Outputs:
- `discharge_ensemble_model.pkl` - trained stacking ensemble
- `feature_importance.csv` - ranked predictors by permutation importance
- `cross_validation_scores.json` - R², RMSE, NSE by gauge and fold
- `hyperparameters.json` - optimal model configuration

**3. Regional Prediction & Analysis**
```python
python PIPELINES/analyse_regional_discharge.py \
  --model discharge_ensemble_model.pkl \
  --gauges all \
  --output regional-discharge-study
```

Outputs:
- `monthly_predictions_all_gauges.csv` - predicted vs. observed discharge
- `regional_skill_map.geojson` - model R² and RMSE by gauge location
- `feature_attribution.json` - regional climate vs. basin vs. upstream importance
- `case_study_findings.md` - narrative, visualizations, and conclusions

### Phase 2: Local Deep Dives (Pskem/Chirchik Validation)

**Objective:** Cross-validate regional model against high-quality local daily observations

**Comparison:**
1. Aggregate regional model monthly predictions to daily via disaggregation
2. Compare against Pskem/Chirchik daily discharge observations (2001-2017 validation period)
3. Benchmark against existing Pskem HBV-family daily model
4. Identify if regional statistical model captures local physics

**Output:**
- `pskem_chirchik_validation_comparison.json` - skill metrics comparing models

### Phase 3: Daily Discharge Expansion (Future)

Once monthly model is validated, extend to daily discharge for selected high-data-quality gauges:
- Calibrate daily temperature-index model on basin characteristics
- Use regional monthly model as seasonal constraint
- Focus on snow-dominated basins with glacial extent > 5%

## Expected Outputs

### Scientific Artifacts
- `PUBLISHED/data/case-studies/regional-discharge-case-study.md` - full scientific report
- `PUBLISHED/data/case-studies/regional-discharge-analysis.json` - results JSON
- `PUBLISHED/data/case-studies/regional_skill_map.geojson` - spatial skill map
- Figures: Feature importance, regional skill distribution, validation comparison

### Data Products
- CSV exports: Predictions, residuals, feature values for all gauges
- Model: Serialized ensemble for production deployment
- Notebook: Jupyter reproducibility document with step-by-step analysis

### Integration
- Landing page enhancement: Display predicted monthly discharge on gauge modals
- Data lineage: Track upstream stations and gridded data feeding each gauge prediction
- API endpoint: Serve discharge forecasts and historical predictions

## Validation Strategy

### Temporal Holdout
- Train on 1990-2015 (if available)
- Validate on 2016-2023 (recent, independent period)
- Assess if model generalizes to future climate

### Spatial Cross-Validation
- 5-fold grouping by basin cluster (not random split)
- Ensures model sees diverse basin types in training
- Tests regional transferability

### Benchmark Comparisons
1. **Persistence baseline:** Discharge(t) = Discharge(t-12)
2. **Climatology baseline:** Monthly mean for each gauge
3. **Simple regression:** Linear model on TerraClimate precip/temp
4. **Pskem HBV model:** For overlap region, compare R² and NSE

### Pskem Local Validation
- Use Pskem local daily discharge (2001-2017) as ground truth
- Aggregate regional predictions to daily via cubic spline interpolation
- Compare NSE scores: expect regional model NSE ≈ 0.65-0.75, HBV model NSE ≈ 0.74
- Analyze residual patterns to identify what physical processes the statistical model misses

## Technical Implementation

### Dependencies
- Python 3.10+
- pandas, numpy, scipy for data manipulation
- scikit-learn for ensemble models
- xarray, rasterio for spatial data
- sqlite3 for CA-discharge GeoPackage access
- matplotlib, seaborn for visualization

### File Structure
```
PIPELINES/
├── build_regional_discharge_model.py       # Data assembly & feature engineering
├── train_discharge_ensemble.py              # Model training & cross-validation
├── analyse_regional_discharge.py            # Prediction & analysis
├── validate_pskem_discharge_ensemble.py     # Daily validation vs. HBV model
└── discharge_model_utils.py                 # Shared utilities (feature scaling, etc.)

PUBLISHED/data/case-studies/
├── regional-discharge-case-study.md         # Main report
├── regional-discharge-analysis.json         # Results & scores
├── regional_skill_map.geojson              # Skill by gauge
├── discharge_feature_importance.csv         # Predictor rankings
└── regional-discharge-predictions-all-gauges.csv  # Full data export
```

### Computation
- Feature assembly: ~2-3 hours (extract all basin attributes, climate, upstream data)
- Model training: ~1-2 hours (hyperparameter tuning on 15k records)
- Prediction & analysis: ~30 minutes
- Total runtime: ~4-6 hours, can be parallelized by basin cluster

## Success Criteria

- ✓ Regional model R² ≥ 0.65 median across all gauges
- ✓ RMSE relative error ≤ 40% for 80% of gauges (avoid high-error outliers)
- ✓ Feature importance confirms climate forcing > basin characteristics for monthly discharge
- ✓ Upstream station network improves R² by ≥ 5% vs. gridded-only model
- ✓ Cross-validation shows no significant bias by basin type or country
- ✓ Pskem validation R² ≥ 0.60 when aggregated to daily (demonstrates regional model captures local basin behavior)

## References

**Theoretical foundations:**
- Oudin et al. (2010): "Can regional hydrological models be fitted set-nationally?" - comparative regionalization
- Mezentsev (1955), Budyko (1974): Water-energy balance frameworks informing ensemble structure

**Related implementations in this codebase:**
- `build_pskem_daily_model.py` - Daily HBV model (Pskem comparison)
- `extract_regional_monthly.py` - TerraClimate extraction infrastructure
- `build_regional_station_study.py` - Station-satellite fusion methodology
- `model_station_ensemble.py` - Historical ensemble model reference

## Timeline

**Week 1:** Data assembly (features, upstream network, quality screening)
**Week 2:** Model development, hyperparameter tuning, cross-validation
**Week 3:** Regional analysis, skill mapping, Pskem validation
**Week 4:** Documentation, figure generation, integration with landing page

---

Next: Proceed with `build_regional_discharge_model.py` implementation
