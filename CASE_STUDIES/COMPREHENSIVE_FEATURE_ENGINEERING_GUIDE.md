# Comprehensive Feature Engineering for Discharge Modeling

## Overview

This document describes the comprehensive feature engineering approach for modeling discharge and predicting dry spells at regional scale across 38 gauges and HydroSHED basins.

**Total Features: 68** across 6 major categories

---

## Feature Categories

### 1. **Terrain Features (5 features)**
Static basin topographic characteristics:

| Feature | Unit | Source | Description |
|---------|------|--------|-------------|
| basin_slope | ° | CA-discharge | Average topographic slope |
| basin_aspect | ° (0-360) | CA-discharge | Mean slope aspect (direction) |
| basin_tpi | Index | CA-discharge | Topographic Position Index - elevation relative to 10km neighborhood |
| basin_tri | Index | CA-discharge | Terrain Ruggedness Index - measure of surface complexity |
| basin_roughness | m | CA-discharge | Surface roughness (DEM-derived) |

**Significance:** Control for drainage basin morphology affecting runoff routing and concentration time.

---

### 2. **Landcover Features (7 features, % cover)**
Basin-scale land use/land cover composition from ESA-CCI:

| Feature | Coverage % | Description |
|---------|-----------|-------------|
| landcover_forest_pct | 0-100 | Tree cover (>30% density) |
| landcover_grassland_pct | 0-100 | Natural grasslands & pastures |
| landcover_shrubland_pct | 0-100 | Shrub-dominated areas |
| landcover_cropland_pct | 0-100 | Agricultural/cultivated land |
| landcover_urban_pct | 0-100 | Urban/built-up areas |
| landcover_water_pct | 0-100 | Permanent water bodies |
| landcover_bare_pct | 0-100 | Bare rock/soil/sparsely vegetated |

**Significance:** Affects infiltration rates, interception, and land management impacts on streamflow. Forest increases baseflow; cropland increases runoff coefficient.

---

### 3. **Climate Forcing Features (12 features)**
Monthly basin-scale aggregated from upstream meteorological stations (27% coverage):

#### Direct Climate Forcing
| Feature | Unit | Range | Source |
|---------|------|-------|--------|
| basin_precip_mm | mm | 0-20 | Distance-weighted upstream stations |
| basin_tavg_c | °C | -15-25 | Distance-weighted upstream stations |
| basin_tmax_c* | °C | -8-32 | Estimated as tavg + 7°C (continental climate) |
| basin_tmin_c* | °C | -22-18 | Estimated as tavg - 7°C (continental climate) |
| basin_aet_est_mm* | mm | 0-12 | Estimated AET ≈ 0.7 × precip × f(temp) |

#### Lagged & Anomaly Features
| Feature | Description | Hydrological Significance |
|---------|-------------|--------------------------|
| basin_precip_lag1_mm | Previous month precipitation | Soil moisture memory |
| basin_precip_lag12_mm | Same month previous year | Annual cycle persistence |
| basin_precip_3m_mm | 3-month rolling average | Seasonal precipitation regime |
| basin_precip_ratio_annual | Monthly P / mean annual P | Normalized seasonal signal |
| basin_anom_precip | Anomaly from climatology | Wet/dry deviations from normal |

**Note:** * = Derived/Estimated; AET = Actual Evapotranspiration

**Significance:** Precipitation is primary driver of discharge in water-limited regimes. Temperature modulates ET. Lags capture soil moisture dynamics.

---

### 4. **Flow Regime Statistics (8 features)**
Basin-specific discharge quantiles and anomalies:

| Feature | Definition | Hydrological Role |
|---------|-----------|-------------------|
| discharge_q10, q25, q50, q75, q90 | Flow quantiles by gauge | Characterize flow distribution |
| discharge_baseflow_m3s | Low flow baseline (10th percentile mean) | Groundwater contribution |
| discharge_above_baseflow | Q - baseflow | Stormflow/quick runoff component |
| discharge_anomaly_std | Standardized deviation from mean | Normalized flow stress indicator |

**Significance:** Quantile-based features handle skewed discharge distributions common in arid/semi-arid regions.

---

### 5. **Seasonal Features (8 features)**
Seasonal precipitation and discharge means by gauge:

| Feature | Description |
|---------|-------------|
| season | Winter, Spring, Summer, Fall |
| precip_winter_mm, precip_spring_mm, ... | Mean seasonal precipitation |
| discharge_winter_m3s, discharge_spring_m3s, ... | Mean seasonal discharge |

**Significance:** Central Asia exhibits strong seasonality (snow melt in spring, low flows in late summer). Seasonal indicators help models learn hydrological regimes.

---

### 6. **Dry Spell Classification Features (5 features)**

#### Definition
A **dry spell** occurs when ≥2 of these conditions are met:
1. **Low Precipitation:** basin_precip_mm < 25th percentile for that gauge
2. **Low Discharge:** discharge_m3s < 25th percentile for that gauge  
3. **High Evaporative Demand:** basin_aet_est_mm > 75th percentile

#### Features
| Feature | Type | Values | Significance |
|---------|------|--------|--------------|
| dry_spell_precip | Binary | 0/1 | Precipitation deficit indicator |
| dry_spell_discharge | Binary | 0/1 | Flow stress indicator |
| dry_spell_aet_high | Binary | 0/1 | Evaporative pressure indicator |
| dry_spell | Binary (Composite) | 0/1 | Multi-criteria dry period |
| dry_spell_severity | Categorical | none / low_flow / drought | Severity classification |

#### Severity Classes
- **none:** Normal conditions (< 2 indicators active)
- **low_flow:** Low discharge alone (Q < Q25, but adequate precipitation)
- **drought:** Compound stress (Q < Q25 AND P < P25) - water-limited regime

#### Observed Statistics
- **Total dry spells identified:** 113 periods (1.7% of monthly records)
  - Drought (compound): 42 events (0.6%)
  - Low flow (discharge stress): 1,599 events (23.7%)
  - Normal: 5,098 events (75.6%)

**Significance:** Binary/categorical target enables classification models for dry spell prediction and forecasting water availability stress.

---

### 7. **Temporal Features (3 features)**
Cyclical encoding of seasonal patterns:

| Feature | Encoding | Period | Range |
|---------|----------|--------|-------|
| month_sin | sin(2π × month/12) | Annual | [-1, 1] |
| month_cos | cos(2π × month/12) | Annual | [-1, 1] |
| year_normalized | (year - min_year) / (max_year - min_year) | Full span | [0, 1] |

**Significance:** Sine/cosine prevent artificial discontinuity at month 12→1. Captures seasonality without directional bias.

---

### 8. **Basin Static Attributes (18 features)**
Existing basin characteristics from CA-discharge GeoPackage:

| Feature | Unit | Description |
|---------|------|-------------|
| basin_area_km2 | km² | Drainage area |
| basin_elevation_m | m | Mean elevation |
| basin_elevation_min_m, _max_m | m | Elevation range |
| basin_slope_pct | % | Mean slope |
| basin_mean_q_m3s | m³/s | Climatological mean discharge |
| basin_glacier_pct | % | Glacier cover (placeholder) |
| basin_permafrost_pct | % | Permafrost extent (placeholder) |
| basin_forest_pct, basin_shrub_pct, ... | % | Landcover by type (original) |
| basin_urban_pct, basin_water_pct | % | Urban/water cover (original) |

**Note:** Static attributes do not vary temporally; glacier and permafrost are placeholders for Phase 2 (HydroATLAS).

---

## Data Coverage & Quality

### Coverage Summary
| Variable | Non-Null | Coverage % | Notes |
|----------|----------|------------|-------|
| discharge_m3s | 6,739 / 6,739 | 100.0% | All gauges have complete discharge records |
| basin_precip_mm | 1,832 / 6,739 | 27.2% | Limited by upstream station availability |
| basin_tavg_c | 1,832 / 6,739 | 27.2% | Same as precipitation |
| Terrain features | 6,739 / 6,739 | 100.0% | Complete basin attribute coverage |
| Landcover | 6,739 / 6,739 | 100.0% | Complete ESA-CCI coverage |

### Geographic Coverage
- **6 gauges** with upstream meteorological station data (climate features available)
- **32 gauges** without direct upstream stations (climate features NaN)
- **38 gauges total** with terrain/landcover/discharge

---

## Feature Importance & Interpretation

### From Current Models (38 gauges with 27% climate coverage):
```
Top 10 Most Important Features:
1. month_cos                    0.2813 (temporal)
2. basin_tavg_c                 0.1325 (climate) ← NEW!
3. basin_precip_3m_mm           0.1244 (climate) ← NEW!
4. year_normalized              0.1152 (temporal)
5. basin_precip_lag1_mm         0.0953 (climate) ← NEW!
6. month_sin                    0.0773 (temporal)
7. basin_precip_mm              0.0671 (climate) ← NEW!
8. basin_precip_lag12_mm        0.0592 (climate) ← NEW!
9. basin_anom_precip            0.0475 (climate) ← NEW!
10. n_stations_contributing     0.0002 (metadata)
```

**Key Insight:** With real basin climate forcing, precipitation & temperature features now account for ~54% of importance in top 9 features, properly reflecting their hydrological significance.

---

## Phase 2 Enhancements: HydroSHED Basin-Level Aggregation

### Objective
Expand modeling from 38 point gauges to comprehensive HydroSHED basin coverage (1,000s of basins) by:
1. Aggregating features to standardized basin units (Pfafstetter levels 7/10)
2. Integrating gridded climate data (TerraClimate, ERA5) for all basins
3. Creating basin-level discharge predictions via spatial interpolation

### HydroSHED Hierarchy
- **Level 7 (Pfafstetter):** 1,000-3,000 km² basins (regional analysis)
- **Level 10:** 100-300 km² basins (local watersheds)
- **Level 12:** 10-100 km² basins (hillslope-scale)

Available GeoJSON files:
- `transboundary_basins_v2/hydroatlas-level07-full-basins.geojson`
- `transboundary_basins_v2/hydroatlas-level10-full-basins.geojson`
- `transboundary_basins_v2/hydroatlas-level12-full-basins.geojson`

### Implementation Steps (Phase 2)
1. **Map gauges to HydroSHED basins** (spatial join)
2. **Aggregate gridded climate data** (TerraClimate: 1980-2024)
   - Precipitation, temperature, actual ET
   - Soil moisture (multiple layers)
   - Palmer Drought Severity Index (PDSI)
3. **Integrate additional basin attributes** (HydroATLAS)
   - Glacier/permafrost extent
   - Slope, aspect distributions
   - Runoff coefficients
4. **Train basin-level models** with 1,000+ records per HydroSHED unit
5. **Spatial interpolation** of discharge to ungauged basins

---

## Implementation

### Run Feature Engineering
```bash
npm run discharge:features
# or directly:
python PIPELINES/comprehensive_feature_engineering.py
```

### Include in Full Workflow
```bash
npm run discharge:feature-study
# Runs: build → features → gauge-train → gauge-predict → gauge-report
```

### Output Files
1. **enhanced_discharge_features.csv** (6,739 records × 68 columns)
   - All engineered features + dry spell labels
   - Ready for model training

2. **feature_engineering_report.md**
   - Complete feature documentation
   - Data coverage statistics
   - Dry spell methodology

3. **dry_spell_analysis.csv**
   - Per-gauge dry spell frequencies
   - Flow quantiles & extremes
   - Seasonal statistics

---

## References & Methodological Notes

### Temperature Extremes Estimation
- Tmax = Tavg + 7°C, Tmin = Tavg - 7°C
- Based on continental climate regime (Central Asia typical: ~14°C range)
- More precise: use ERA5-Land min/max (requires gridded data integration)

### Actual Evapotranspiration Estimation
- Simplified: AET ≈ 0.7 × P × min(Tavg/20, 1)
- Assumes water-limited regime where AET increases with temperature but capped by precipitation
- More precise: Penman-Monteith or Hargreaves equation (requires wind, radiation)

### Dry Spell Definition
- Multi-criteria: avoids false positives from single metric fluctuations
- Quantile thresholds (P25, Q25, AET75) are gauge-specific for adaptation to local regimes
- Severity classification enables risk-stratified forecasting

### Landcover-Discharge Relationship
- **Forest:** ↑ baseflow, ↓ peak flow (interception, infiltration)
- **Grassland:** Medium infiltration, moderate baseflow
- **Urban:** ↑ peak flow, ↓ baseflow (impervious surfaces)
- **Cropland:** Highly managed; depends on irrigation & extraction

---

## Next Steps

1. ✅ Generate enhanced features (68 features)
2. ✅ Identify dry spells (1.7% of records)
3. ⏳ Retrain gauge-specific models with new features
4. ⏳ Evaluate feature importance for arid hydroclimate
5. 📋 Phase 2: Integrate gridded climate (TerraClimate, ERA5)
6. 📋 Phase 2: HydroSHED basin aggregation & spatial predictions
7. 📋 Phase 2: Combine with Sentinel/MODIS for soil moisture calibration

