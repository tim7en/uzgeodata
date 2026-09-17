# Comprehensive Feature Engineering Report
## Overview
Total records: 59,516
Total gauges: 114
Time span: 1910-2021
Total engineered features: 71

## Feature Categories
### 1. Terrain Features (5 features)
- basin_slope: Topographic slope (°)
- basin_aspect: Slope aspect (°, 0-360)
- basin_tpi: Topographic Position Index (elevation relative to neighbors)
- basin_tri: Terrain Ruggedness Index (measure of terrain complexity)
- basin_roughness: Surface roughness

### 2. Landcover Features (10 features, % of basin area)
- landcover_forest_pct: Closed + open forest, all leaf types (Copernicus CGLS-LC100 111-126)
- landcover_shrubland_pct: Shrubs (lc_20)
- landcover_grassland_pct: Herbaceous vegetation (lc_30)
- landcover_cropland_pct: Cultivated/agricultural land (lc_40)
- landcover_urban_pct: Urban/built-up area (lc_50)
- landcover_bare_pct: Bare/sparse vegetation (lc_60)
- landcover_snow_ice_pct: Permanent snow and ice (lc_70) — the real glacier/snowpack signal basin_glacier_pct never had
- landcover_water_pct: Permanent water bodies (lc_80)
- landcover_wetland_pct: Herbaceous wetland (lc_90)
- landcover_moss_lichen_pct: Moss and lichen (lc_100)

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
- Non-null discharge: 59516 / 59516 (100.0%)
- Non-null basin_precip_mm: 41735 / 59516 (70.1%)
- Non-null basin_tavg_c: 41735 / 59516 (70.1%)
- Dry spells identified: 3579 (6.0%)
  - Drought (low flow + low precip): 1993
  - Low flow: 12737
