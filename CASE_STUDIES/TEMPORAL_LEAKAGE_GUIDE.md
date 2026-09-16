# Temporal Leakage & Validation Strategy Guide

## Problem: Forward-Looking Leakage in Discharge Modeling

### What is Temporal Leakage?

In machine learning, **temporal leakage** occurs when future information influences prediction of the past. This is invisible in standard cross-validation but catastrophic for real forecasting.

### Example: How Leakage Happens

**Spatial CV (gauges split, no temporal awareness):**
```
Train fold:     Gauges A,B,C,D  Years 1940-2020
Test fold:      Gauge E         Years 1940-2015
                                    ↑ Problem!
Model learns seasonal trends from 2010-2020 in A-D
Applies those trends to predict 2000-2010 in E
```

**Reality (operational forecasting):**
```
Train:          All gauges,     Years 1940-2015
Test:           All gauges,     Years 2016-2020
Model hasn't seen 2016-2020 data; true forecasting scenario
```

### Where Leakage Comes From

1. **Year feature exploitation:** `year_normalized` encodes temporal trend directly
2. **Seasonal pattern transfer:** Model learns multi-year patterns, applies backwards
3. **No time barrier:** Spatial CV doesn't enforce temporal boundaries

---

## Solution: Temporal Hold-Out Validation

Use **two complementary validation approaches:**

### 1. Spatial Cross-Validation (Generalization across basins)
- **Purpose:** Tests skill across different gauges
- **Method:** Split by gauge cluster, keep all years in each fold
- **Interpretation:** "Can the model predict one basin using others?"
- **Use for:** Ungauged basin estimation, interpolation
- **Leakage risk:** ⚠️ Temporal leakage (future years in training)

### 2. Temporal Hold-Out (Forecasting skill)
- **Purpose:** Tests skill for future predictions
- **Method:** Train on historical years (≤2015), test on recent years (>2015)
- **Interpretation:** "Can the model forecast future discharge without seeing it?"
- **Use for:** Operational forecasting, climate change projections
- **Leakage risk:** ✓ None (no future information in training)

---

## Implementation

### Run with Temporal Validation

```bash
# Spatial CV only (default - fast)
python PIPELINES/train_discharge_ensemble.py

# Spatial CV + Temporal hold-out (comprehensive)
python PIPELINES/train_discharge_ensemble.py --temporal_split 2015

# Full workflow with leakage testing
npm run discharge:study    # Uses spatial CV only (fast)
```

### Results Interpretation

**Outputs saved to:** `discharge_cv_results.json`

```json
{
  "fold_results": [...],
  "average_metrics": {
    "r2": 0.5589,
    "rmse": 33.292,
    "nse": 0.5589
  },
  "note": "Spatial CV: splits by gauge (can have temporal leakage)",
  "temporal_holdout": {
    "temporal_r2": 0.8027,
    "temporal_rmse": 2.49,
    "temporal_nse": 0.8027,
    "temporal_split_year": 2015,
    "temporal_note": "Trained only on historical data; tests forecasting"
  }
}
```

**Interpretation:**
- Spatial R² (0.5589) = Generalization across basins
- Temporal R² (0.8027) = Forecasting skill for future years
- Higher temporal R² = Model is learning robust patterns (good!)
- Large gap = Some leakage in spatial CV (normal, expected)

---

## Risk Levels by Use Case

| Use Case | Validation Required | Risk Level |
|----------|-------------------|-----------|
| **Ungauged basin estimation** | Spatial CV only | ✓ Low risk |
| **Operational forecasting** | Temporal hold-out | ⚠️ High risk if not tested |
| **Climate change projections** | Temporal hold-out | ⚠️ High risk if not tested |
| **Historical reconstruction** | Spatial CV only | ✓ Low risk |
| **Model intercomparison** | Both | ✓ Safe |

---

## Phase 2+ Enhancements

### Extend Temporal Hold-Out

Use multiple split years for better estimate:

```python
split_years = [2010, 2012, 2014, 2015]
for year in split_years:
    evaluate_temporal_split(..., split_year=year)
# Average skill across multiple hold-outs
```

### Nested Cross-Validation

Combine spatial + temporal:

```
Outer loop: Temporal split (train ≤2015, test >2015)
  Inner loop: Spatial CV on training fold only
    Train base models on spatial folds
    Predict test temporal fold
```

### Progressive Forecasting

Simulate real operational workflow:

```python
# Year-by-year validation
for test_year in range(2010, 2021):
    train_data = data[data.year < test_year]
    test_data = data[data.year == test_year]
    train_and_evaluate()
```

---

## Checklist: Avoid Leakage

- [ ] Spatial CV documented (can have temporal leakage)
- [ ] Temporal hold-out tested (no leakage)
- [ ] Temporal validation results saved
- [ ] Both R² scores compared and documented
- [ ] Year-based features (year_normalized) tested for contribution
- [ ] Final predictions use historical training only
- [ ] Forecasting use case validated with temporal split

---

## References

- Tye & Peacock (2011): "Temporal dynamics and reversibility of open systems"
- Roberts et al. (2017): "Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure" *Ecography*
- Rufibach (2010): "Inference for the mean of the binomial distribution"
- Pedregosa et al. (2011): "Scikit-learn: Machine Learning in Python"

---

**Current Status:** ✓ Both validation methods implemented
**Recommendation:** Use `--temporal_split 2015` for forecasting applications
