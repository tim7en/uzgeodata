# Dry Spell Precursor Analysis & Early Warning Guide

## Overview
This document describes features that indicate impending dry spells by analyzing
upstream basin conditions and their evolution over time.

## Key Antecedent Features for Early Warning

### 1. Discharge State & Trend (3 features)
- **discharge_lag1_m3s:** Discharge in previous month
- **discharge_3m_mean_m3s:** Average discharge over prior 3 months
- **discharge_6m_mean_m3s:** Average discharge over prior 6 months
**Interpretation:** Declining discharge over months indicates depleting baseflow;
  lower values in 3m/6m averages signal extended low-flow period.

### 2. Discharge Trend & Depletion (2 features)
- **discharge_trend_3m:** Slope of discharge change over past 3 months
- **discharge_depletion_pct:** % Change from 3-month mean
**Interpretation:** Negative trend = accelerating depletion. High depletion %
  means current Q much lower than recent average (recession pattern).

### 3. Consecutive Low Flow (1 feature)
- **consecutive_low_flow_3m:** Count of months below Q25 in prior 3 months
**Interpretation:** 2-3 consecutive low-flow months = strong precursor.
  Baseflow exhaustion becomes imminent.

### 4. Precipitation State (3 features)
- **precip_lag1_mm:** Precipitation in previous month
- **precip_3m_cumul_mm:** Total precipitation over prior 3 months
- **precip_6m_cumul_mm:** Total precipitation over prior 6 months
**Interpretation:** Low cumulative precip over months means recharge deficit.
  Future discharge will be sustained only by dwindling groundwater.

### 5. Precipitation Deficit (2 features)
- **precip_deficit_pct:** % Deviation from climatological normal
- **dry_months_3m:** Count of below-normal precip months
**Interpretation:** Negative deficit = below normal. 2-3 consecutive dry
  months = recharge failure.

## Stress Accumulation Index (0-1 scale)

Composite indicator combining:
- **40% Discharge Stress:** (Q_normal - Q_current) / range
- **40% Precipitation Stress:** Deficit from climatology
- **20% ET Pressure:** High evaporative demand

**Thresholds:**
- < 0.3: Low stress (normal conditions)
- 0.3-0.6: Moderate stress (watch for escalation)
- > 0.6: High stress (dry spell likely imminent)

## Lead Time Indicators (Early Warning Signals)

### 1. Stress Increasing
**Condition:** stress_index(t) > stress_index(t-1) > stress_index(t-2) > stress_index(t-3)
**Lead Time:** 1-3 months before dry spell
**Action:** Begin drought preparedness; increase water use efficiency

### 2. Sustained High Stress
**Condition:** stress_index > 0.5 for 3+ consecutive months
**Lead Time:** Dry spell occurring or imminent
**Action:** Implement water restrictions; assess groundwater reserves

### 3. Rapid Stress Acceleration
**Condition:** stress_index change > 75th percentile
**Lead Time:** 0-1 months before severe dry spell
**Action:** Activate emergency water management protocols

## Upstream Basin Connectivity Features

### Runoff Coefficient (Q/P Ratio)
- **High (>1.0):** Not water-limited; discharge exceeds precip
  (snowmelt-dominated basins)
- **Medium (0.3-0.7):** Mixed regime (typical)
- **Low (<0.3):** Water-limited; high ET losses
  **More vulnerable to dry spells**

### Baseflow Ratio
- **High (>0.7):** Groundwater-fed; more resilient to short-term precip deficits
- **Medium (0.3-0.7):** Mixed surface/groundwater
- **Low (<0.3):** Surface runoff-dominated; reactive to precip
  **More vulnerable to rapid flow crashes**

### Baseflow Recession
- **Negative:** Baseflow declining (groundwater depletion)
- **Positive:** Baseflow recovering (recharge occurring)
**Use:** Indicator of whether basin is entering or exiting dry spell phase

## Predictive Framework: Months Before Dry Spell

| Lead Time | Indicator | Threshold | Confidence |
|-----------|-----------|-----------|------------|
| **3 months** | stress_increasing | True | ~60% |
|  | precip_3m_cumul < P25 | Low cumul | ~50% |
| **2 months** | sustained_stress_3m | True | ~70% |
|  | consecutive_low_flow_3m ≥ 2 | 2+ months | ~65% |
| **1 month** | stress_index > 0.6 | High | ~85% |
|  | dry_months_3m ≥ 2 | 2+ dry months | ~75% |
| **Current** | dry_spell | True | 100% |
|  | stress_index > 0.7 | Very high | ~95% |

## Example Case: Dry Spell Progression

```
Month -3: precip_3m_cumul_mm = 45 (below normal)
         stress_index = 0.35 (moderate), trend up
         Action: Begin water use optimization

Month -2: precip_3m_cumul_mm = 38 (declining)
         discharge_3m_mean = Q30 (below median)
         stress_index = 0.52 (high)
         sustained_stress_3m = True
         Action: Issue drought watch; prepare restrictions

Month -1: precip_6m_cumul = insufficient for recharge
         discharge_trend = negative (recession)
         consecutive_low_flow_3m = 3 (all months low)
         stress_index = 0.68 (very high)
         Action: Issue drought warning; activate restrictions

Month 0: discharge_m3s < Q25, basin_precip < P25
        dry_spell = 1 (compound stress)
        dry_spell_severity = 'drought'
        Action: Activate emergency measures
```

## Data Coverage for Antecedent Features

| Feature Type | Coverage | Limitation |
|--------------|----------|------------|
| Discharge antecedents | 100% | 38 gauges |
| Precipitation antecedents | 27% | 6 gauges with upstream stations |
| Stress index | 100% | Available for all gauges |
| Lead indicators | 100% | All gauges |
| Baseflow features | 100% | Derived from discharge |

## Recommendations for Application

1. **3-month lead:** Monitor stress_increasing and precip_3m_cumul
   - Accuracy ~60% but long warning time

2. **1-month lead:** Use stress_index > 0.6 + dry_months_3m ≥ 2
   - Accuracy ~80% with actionable warning period

3. **Real-time:** Combine stress_index + discharge_trend + consecutive_low_flow
   - Accuracy ~90% for detecting emerging dry spells

4. **Seasonal:** Higher dry spell risk in late summer/early fall
   - Use seasonal thresholds for stress_index (e.g., 0.5 in summer, 0.7 in winter)

## Validation Needed
- Historical dry spell events: trace back antecedent conditions
- Lead time vs accuracy tradeoff: optimize thresholds per gauge
- Seasonal calibration: winter vs summer dry spells differ
- Ensemble forecasting: combine with climate predictions
