# Comprehensive Feature Engineering Report
## Overview
Total records: 6,739
Total gauges: 38
Time span: 1948-2020
Total engineered features: 68

## Feature Categories
### 1. Terrain Features (5 features)
- basin_slope: Topographic slope (°)
- basin_aspect: Slope aspect (°, 0-360)
- basin_tpi: Topographic Position Index (elevation relative to neighbors)
- basin_tri: Terrain Ruggedness Index (measure of terrain complexity)
- basin_roughness: Surface roughness

### 2. Landcover Features (7 features, %)
- landcover_forest_pct: Forest cover percentage
- landcover_grassland_pct: Grassland cover
- landcover_shrubland_pct: Shrubland cover
- landcover_water_pct: Water body percentage
- landcover_urban_pct: Urban/built-up area
- landcover_cropland_pct: Agricultural land
- landcover_bare_pct: Bare rock/soil

### 3. Climate Forcing Features (12+ features)
- basin_precip_mm: Monthly precipitation (mm)
- basin_tavg_c: Average temperature (°C)
- basin_tmax_c: Estimated max temperature (°C)
- basin_tmin_c: Estimated min temperature (°C)
- basin_precip_lag1_mm: Previous month precipitation
- basin_precip_lag12_mm: Same month previous year
- basin_precip_3m_mm: 3-month rolling average
- basin_anom_precip: Precipitation anomaly from climatology
- basin_aet_est_mm: Estimated actual evapotranspiration
- basin_precip_ratio_annual: Monthly precip as ratio of annual mean

### 4. Flow Statistics Features (6+ features)
- discharge_q10, q25, q50, q75, q90: Flow quantiles by gauge
- discharge_baseflow_m3s: Base flow (low 10% mean)
- discharge_above_baseflow: Excess flow above base
- discharge_anomaly_std: Standardized flow anomaly

### 5. Seasonal Features (8 features)
- season: Winter, Spring, Summer, Fall
- precip_[season]_mm: Mean seasonal precipitation
- discharge_[season]_m3s: Mean seasonal discharge

### 6. Dry Spell Classification Features (4 features)
- dry_spell_precip: Binary indicator (low precip)
- dry_spell_discharge: Binary indicator (low flow)
- dry_spell_aet_high: Binary indicator (high evaporative demand)
- dry_spell: Composite indicator (2+ active)
- dry_spell_severity: Classification (none, low_flow, drought)

## Dry Spell Definition
A dry spell is identified when ≥2 of the following occur:
1. Precipitation < 25th percentile for that gauge
2. Discharge < 25th percentile for that gauge
3. Evaporative demand > 75th percentile for that gauge

## Data Coverage
- Non-null discharge: 6739 / 6739 (100.0%)
- Non-null basin_precip_mm: 1832 / 6739 (27.2%)
- Non-null basin_tavg_c: 1832 / 6739 (27.2%)
- Dry spells identified: 113 (1.7%)
  - Drought (low flow + low precip): 42
  - Low flow: 1599
