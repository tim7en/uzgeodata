# Gauge-Specific Discharge Ensemble Models

## Architecture Overview

The gauge-specific approach trains a **separate ensemble for each gauge** rather than one pooled model. This enables:

1. **Per-gauge variable importance** - which predictors matter most for THIS gauge?
2. **Gauge-specific uncertainty quantification** - prediction intervals tailored to local conditions
3. **Customized model calibration** - each gauge gets its own decision boundaries
4. **Local forecasting skill** - honest assessment per location

## Workflow

### Quick Start

```bash
# Complete gauge-specific workflow (builds features, trains 38 individual models, generates report)
npm run discharge:gauge-study

# Or stage-by-stage:
npm run discharge:build              # Build feature matrix (1-2 hours)
npm run discharge:gauge-train        # Train 38 individual ensembles (2-4 hours)
npm run discharge:gauge-upstream     # Trace upstream meteorological stations (10 min)
npm run discharge:gauge-predict      # Generate quantile predictions + uncertainty (30 min)
npm run discharge:gauge-report       # Generate case study report (10 min)
```

### Individual Stages

#### Stage 1: Feature Assembly
```bash
python PIPELINES/build_regional_discharge_model.py
```
- Loads discharge data from CA-discharge GeoPackage (295 gauges)
- Filters to quality data: ≥10 years monthly, quality flag = 1 (best)
- Creates basin static features: area, elevation, slope, glacier %, etc.
- Creates temporal features: month (cyclical), year normalized
- Output: `regional_discharge_data.csv` (6,739 records × 40 features)

#### Stage 2: Gauge-Specific Ensemble Training
```bash
python PIPELINES/train_gauge_specific_ensemble.py
```
- For each of 38 qualified gauges:
  - Trains Random Forest (100 trees, max_depth=12)
  - Trains Gradient Boosting (100 estimators, learning_rate=0.1)
  - Trains Ridge meta-learner combining both
  - Trains 3 Quantile Regressors (10th, 50th, 90th percentile) for uncertainty
  - Evaluates on hold-out validation set
- Outputs:
  - `gauge_ensemble_models.pkl` (38 trained models)
  - `gauge_variable_importance.csv` (per-gauge feature rankings)
  - `gauge_uncertainty_calibration.json` (per-gauge error statistics)

#### Stage 3: Upstream Station Tracing
```bash
python PIPELINES/integrate_upstream_stations.py
```
- Traces meteorological stations upstream/near each gauge basin
- Distance-weighted aggregation: closer stations weighted higher
- Outputs:
  - `gauge_upstream_stations.csv` (station-gauge relationships)
  - `gauge_upstream_features.csv` (aggregated upstream characteristics)

**Note:** Full time series aggregation for upstream forcing is Phase 2 enhancement.

#### Stage 4: Quantile Predictions
```bash
python PIPELINES/generate_gauge_predictions.py
```
- Uses trained gauge-specific models to generate predictions for all records
- Produces three prediction quantiles per record:
  - p10: 10th percentile (conservative lower bound)
  - p50: 50th percentile (median, best estimate)
  - p90: 90th percentile (conservative upper bound)
- Evaluates prediction interval coverage (should be ~90%)
- Outputs:
  - `gauge_quantile_predictions.csv` (predictions + intervals for all records)
  - `gauge_prediction_summary.csv` (aggregated stats by gauge)
  - `gauge_uncertainty_report.json` (per-gauge uncertainty characterization)

#### Stage 5: Case Study Report
```bash
python PIPELINES/generate_gauge_case_study.py
```
- Generates comprehensive markdown report featuring:
  - Per-gauge variable importance rankings (heatmap visualization)
  - Prediction interval reliability analysis
  - Gauge-specific skill profiles
  - Uncertainty characterization tables
- Outputs:
  - `gauge_specific_case_study.md` (full report with ASCII heatmaps)
  - `gauge_profiles.json` (individual gauge metadata for UI integration)

---

## Key Results

### Example: Gauge Profiles

For each gauge, you get:

```json
{
  "gauge_code": "15-2.3L0-1A",
  "skill": {
    "mae_m3s": 12.45,
    "interval_coverage_pct": 88.5
  },
  "characteristics": {
    "median_discharge_m3s": 45.3,
    "prediction_interval_width_m3s": 28.5,
    "n_training_records": 540
  },
  "top_predictors": [
    {"feature": "basin_mean_q_m3s", "importance": 0.287},
    {"feature": "month_cos", "importance": 0.195},
    {"feature": "basin_elevation_max_m", "importance": 0.082}
  ]
}
```

### Variable Importance Heatmap

The case study includes ASCII heatmap showing which features matter for each gauge:

```
| Gauge Code | basin_mean_q_m3s | month_sin | month_cos | basin_elev | glacier_pct |
|---|---|---|---|---|---|
| 14-1.1L0-1A | ███ | ▓▓▓ | ▓▓▓ | ▒▒▒ | ░░░ |
| 14-2.0L0-1A | ███ | ▓▓▓ | ▓▓▓ | ▓▓▓ | ▒▒▒ |
| 15-1.1L0-1A | ███ | ▓▓▓ | ▓▓▓ | ░░░ | ░░░ |
```

### Uncertainty Quantification

Each gauge gets:
- **Prediction intervals** (90% confidence): [p10, p90]
- **Interval coverage %**: How often do observations fall in predicted interval?
- **Residual statistics**: Mean bias, standard deviation (calibration error)
- **Empirical calibration**: Validation-set interval coverage vs target 90%

**Example:**
- Gauge 14-1.1L0-1A: 87% coverage, ±12.5 m³/s typical error
- Gauge 15-2.3L0-1A: 92% coverage, ±8.2 m³/s typical error

---

## Comparison: Pooled vs Gauge-Specific

| Aspect | Pooled Regional Model | Gauge-Specific Models |
|--------|----------------------|----------------------|
| **Training data** | All gauges together (6,739 records) | Each gauge separately (80-200 records) |
| **Model count** | 1 ensemble | 38 individual ensembles |
| **Variable importance** | Global average | Per-gauge ranking |
| **Calibration** | One size fits all | Tailored to each gauge's error pattern |
| **Uncertainty** | Single error distribution | Per-gauge uncertainty |
| **Computational cost** | ~2 hours training | ~4 hours training |
| **Use case** | Ungauged basin estimation | Operational forecasting per gauge |
| **Interpretability** | "What matters on average?" | "What matters at THIS gauge?" |

---

## Advanced Analysis

### Which Features Matter Most?

Use `gauge_variable_importance.csv` to identify predictors by gauge type:

```python
import pandas as pd

importance = pd.read_csv("gauge_variable_importance.csv")

# High-altitude glacial gauges?
glacial = ['14-1.1L0-1A', '14-2.0L0-1A', ...]  # Gauge codes with glacier > 20%
glacial_importance = importance[importance['gauge_code'].isin(glacial)]
print(glacial_importance.groupby('feature')['importance'].mean().nlargest(10))

# Result shows glacier_pct and elevation matter more for glacial gauges
```

### Uncertainty by Gauge Type

```python
import json

with open("gauge_uncertainty_report.json") as f:
    uncertainty = json.load(f)

# Find gauges with best interval calibration
for gauge_code, stats in uncertainty['gauges'].items():
    coverage = stats['empirical_interval_coverage_pct']
    if 88 < coverage < 92:  # Well-calibrated
        print(f"{gauge_code}: {coverage:.1f}% (✓ well-calibrated)")
```

### Rank Gauges by Forecasting Skill

```python
summary = pd.read_csv("gauge_prediction_summary.csv")
best_skill = summary.nlargest(10, 'interval_coverage_pct')[['gauge_code', 'mae_m3s', 'interval_coverage_pct']]
print(best_skill)
```

---

## Integration with Landing Page

The gauge profiles can be integrated into the landing page gauge modal:

```javascript
// Load gauge profile
const profile = await fetch('/data/case-studies/gauge_profiles.json')
  .then(r => r.json())
  .then(profiles => profiles['14-1.1L0-1A'])

// Show top predictors in modal
profile.top_predictors.forEach(pred => {
  console.log(`${pred.feature}: ${(pred.importance*100).toFixed(1)}%`)
})

// Display prediction interval
const median_pred = 45.3  // m3/s
const interval_width = profile.characteristics.prediction_interval_width_m3s
console.log(`Forecast: ${median_pred.toFixed(1)} ± ${interval_width.toFixed(1)} m³/s`)
```

---

## Phase 2 Enhancements

### 1. Upstream Meteorological Station Integration
- Aggregate time series from upstream stations (not just static features)
- Distance-weighted monthly precipitation and temperature forcing
- Expected impact: 5-10% skill improvement for headwater basins

### 2. Nested Cross-Validation
```
Outer loop: Temporal hold-out (2016-2020)
  Inner loop: Spatial CV on training gauges only
    Generate meta-features
    Train Ridge on meta-features
  Final prediction on held-out temporal fold
```
- Provides more robust uncertainty estimates
- Prevents any temporal leakage

### 3. Hierarchical Modeling
```
Regional level:  Global patterns learned from all gauges
Gauge-specific:  Local adjustments (residuals)
Combined:        Regional prior + gauge-specific posterior
```
- Better uncertainty propagation
- Useful for gauges with limited data

### 4. Seasonal Model Stacking
- Separate ensembles for high-flow season (May-August) vs low-flow season
- Different predictor importance by season
- Expected impact: 10-15% skill improvement

### 5. Operational Dashboard Integration
- Real-time predictions + 90% intervals for each gauge
- Residual monitoring for model drift detection
- Flagging when observations exceed prediction intervals

---

## Troubleshooting

### "Model training for gauge X failed"
- Check if gauge has sufficient training data (typically need ≥50 records)
- See gauge_ensemble_models.pkl keys to identify which gauges trained successfully
- Filter to `--min_years 5` during feature build for more gauges

### "Interval coverage is only 70%"
- Intervals are too narrow - model is overconfident
- Check residual_std in uncertainty_calibration.json
- Consider wider quantiles (0.05/0.50/0.95) instead of 0.10/0.50/0.90

### "Top predictors are all temporal features"
- Indicates limited basin-scale variability - model captures mostly seasonality
- Check if gauge is influenced by upstream reservoirs (breaks rainfall-runoff relationship)
- Consider adding remote sensing features (snow cover, vegetation)

---

## References

- Hastie et al. (2009): "Elements of Statistical Learning" - stacking ensembles
- Koenker & Bassett (1978): "Regression quantiles" - quantile regression for uncertainty
- Roberts et al. (2017): "Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure" - CV methodology

---

**Documentation generated:** 2026-09-16  
**Status:** Production ready for Phase 1; Phase 2 enhancements planned
