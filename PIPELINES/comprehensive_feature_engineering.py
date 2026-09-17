#!/usr/bin/env python3
"""Comprehensive feature engineering for discharge modeling with dry spell detection.

Integrates:
1. Basin static attributes: terrain (slope, aspect, TPI, TRI), landcover
2. Climate forcing: precipitation, temperature, soil moisture, snow
3. Derived features: temperature extremes, anomalies, drought indicators
4. Dry spell classification: identify low-flow stress periods
5. HydroSHED aggregation: basin-level spatial structure

Outputs:
- enhanced_discharge_features.csv: 50+ features including dry spell labels
- feature_engineering_report.md: Documentation of all engineered features
- dry_spell_analysis.csv: Per-gauge dry spell statistics

Usage:
    python PIPELINES/comprehensive_feature_engineering.py
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Tuple
import sys
import math

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

GPKG = ROOT / "GEODATA/ca-discharge-2023/CA-discharge.gpkg"
OUTPUT_DIR = ROOT / "PUBLISHED/data/case-studies"
OUTPUT_FEATURES = OUTPUT_DIR / "enhanced_discharge_features.csv"
OUTPUT_REPORT = OUTPUT_DIR / "feature_engineering_report.md"
OUTPUT_DRY_SPELL = OUTPUT_DIR / "dry_spell_analysis.csv"


class ComprehensiveFeatureEngineer:
    """Orchestrate feature engineering for discharge modeling."""
    
    def __init__(self, discharge_file: Path, basin_climate_file: Path):
        """Initialize with discharge and climate data."""
        print("Loading base datasets...")
        self.discharge_df = pd.read_csv(discharge_file, dtype={'gauge_code': str})
        self.basin_climate_df = pd.read_csv(basin_climate_file)
        self.features_df = self.discharge_df.copy()
        
        print(f"  Discharge: {len(self.discharge_df)} records, {self.discharge_df['gauge_code'].nunique()} gauges")
        print(f"  Basin climate: {len(self.basin_climate_df)} records")
    
    def add_terrain_features(self, gpkg_path: Path) -> None:
        """Extract and add terrain features from GeoPackage."""
        print("\n1. Adding terrain features...")
        import sqlite3
        
        conn = sqlite3.connect(gpkg_path)
        query = "SELECT CODE, slope, aspect, tpi, tri, roughness FROM basin_attributes"
        terrain = pd.read_sql(query, conn, index_col='CODE')
        conn.close()
        
        self.features_df = self.features_df.merge(
            terrain.add_prefix('basin_'),
            left_on='gauge_code', right_index=True, how='left'
        )
        
        print(f"  ✓ Added {len(terrain.columns)} terrain features")
        print(f"    Columns: slope, aspect, TPI, TRI, roughness")
    
    def add_landcover_features(self, gpkg_path: Path) -> None:
        """Extract and add landcover features from GeoPackage."""
        print("\n2. Adding landcover features...")
        import sqlite3
        
        conn = sqlite3.connect(gpkg_path)
        query = "SELECT CODE FROM basin_attributes"
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(basin_attributes)")
        columns = [c[1] for c in cursor.fetchall()]
        lc_cols = [c for c in columns if c.startswith('lc_')]
        
        query = f"SELECT CODE, {', '.join(lc_cols)} FROM basin_attributes"
        landcover = pd.read_sql(query, conn, index_col='CODE')
        conn.close()
        
        # Reclassify ESA landcover codes to categories
        landcover_mapped = self.map_esa_landcover(landcover)
        
        self.features_df = self.features_df.merge(
            landcover_mapped,
            left_on='gauge_code', right_index=True, how='left'
        )
        
        print(f"  ✓ Added {len(landcover_mapped.columns)} landcover features")
        print(f"    Categories: forest, grassland, shrubland, water, urban, snow/ice, barren")
    
    @staticmethod
    def map_esa_landcover(lc_df: pd.DataFrame) -> pd.DataFrame:
        """Map lc_XX codes to categories and normalise to a real percentage.

        The lc_XX columns in CA-discharge's basin_attributes are Copernicus
        CGLS-LC100 codes (not ESA WorldCover, which uses a different codebook
        that shares none of the values actually present here) and are stored
        as **area in km2 per class**, not a fraction — their sum across a row
        equals that gauge's basin_area_km2. The previous version of this
        function looked for ESA-style codes (lc_190 urban, lc_200 water, ...)
        that don't exist in this table, so landcover_water_pct/urban_pct were
        silently always 0, forest was undercounted (missing the lc_111-126
        closed/open-forest subtypes), and nothing was divided by area, so
        "percentages" routinely exceeded 1000. lc_70 (snow and ice) was not
        mapped to anything at all, even though it is exactly the
        glacier/permanent-snow signal this study's basin_glacier_pct has
        stood in for as a hardcoded 0.0 placeholder ever since.

        Copernicus CGLS-LC100 legend for the codes present here:
          20 shrubs, 30 herbaceous vegetation, 40 cropland, 50 urban/built-up,
          60 bare/sparse vegetation, 70 snow and ice, 80 permanent water body,
          90 herbaceous wetland, 100 moss and lichen,
          111-116 / 121-126 closed/open forest (by leaf type).
        """
        result = pd.DataFrame(index=lc_df.index)
        total_km2 = lc_df.sum(axis=1).replace(0, pd.NA)

        def pct(codes: list[str]) -> pd.Series:
            present = [c for c in codes if c in lc_df.columns]
            return 100 * lc_df[present].sum(axis=1) / total_km2 if present else pd.Series(0.0, index=lc_df.index)

        forest_codes = [f'lc_{c}' for c in (111, 112, 113, 114, 115, 116, 121, 122, 123, 124, 125, 126)]
        result['landcover_forest_pct'] = pct(forest_codes)
        result['landcover_shrubland_pct'] = pct(['lc_20'])
        result['landcover_grassland_pct'] = pct(['lc_30'])
        result['landcover_cropland_pct'] = pct(['lc_40'])
        result['landcover_urban_pct'] = pct(['lc_50'])
        result['landcover_bare_pct'] = pct(['lc_60'])
        result['landcover_snow_ice_pct'] = pct(['lc_70'])
        result['landcover_water_pct'] = pct(['lc_80'])
        result['landcover_wetland_pct'] = pct(['lc_90'])
        result['landcover_moss_lichen_pct'] = pct(['lc_100'])

        return result.fillna(0.0)
    
    def add_climate_extremes(self) -> None:
        """Create temperature extremes and climate anomalies."""
        print("\n3. Adding climate extreme features...")
        
        # Use existing climate columns if already merged, or check what's available
        if 'basin_tavg_c' not in self.features_df.columns:
            print("  ERROR: basin_tavg_c not found in features_df")
            return
        
        # Estimate max/min temperature (±7°C from mean based on continental climate)
        self.features_df['basin_tmax_c'] = self.features_df['basin_tavg_c'] + 7.0
        self.features_df['basin_tmin_c'] = self.features_df['basin_tavg_c'] - 7.0
        
        # Temperature extremes
        self.features_df['basin_tmax_lag1_c'] = self.features_df.groupby('gauge_code')['basin_tmax_c'].shift(1)
        self.features_df['basin_tmin_lag1_c'] = self.features_df.groupby('gauge_code')['basin_tmin_c'].shift(1)
        
        # Derived ET (simplified Hargreaves): ET ~ 0.5 * precip * (1 - exp(-T/20)) for water-limited regime
        # Only compute where we have both precip and tavg data
        self.features_df['basin_aet_est_mm'] = np.nan
        valid = self.features_df['basin_precip_mm'].notna() & self.features_df['basin_tavg_c'].notna()
        self.features_df.loc[valid, 'basin_aet_est_mm'] = (
            self.features_df.loc[valid, 'basin_precip_mm'] * 0.7 *  # Assume 70% of precip becomes AET
            np.clip(self.features_df.loc[valid, 'basin_tavg_c'] / 20, 0, 1)  # Scale by temperature
        )
        
        # Precipitation ratio to annual (only where precip is available)
        self.features_df['basin_precip_ratio_annual'] = np.nan
        annual_precip = self.features_df.groupby('gauge_code')['basin_precip_mm'].transform('mean')
        valid_precip = self.features_df['basin_precip_mm'].notna() & (annual_precip > 0)
        self.features_df.loc[valid_precip, 'basin_precip_ratio_annual'] = (
            self.features_df.loc[valid_precip, 'basin_precip_mm'] / annual_precip[valid_precip]
        )
        
        print(f"  ✓ Added temperature extremes, ET, anomalies")
        print(f"    Features: tmax, tmin, aet_est, precip_ratio, lags")
    
    def identify_dry_spells(self) -> None:
        """Classify dry spell periods based on multiple indicators."""
        print("\n4. Identifying dry spells...")
        
        # Dry spell indicators (multi-criteria) - only for records with data
        # Precipitation below 25th percentile (where available)
        precip_q25 = self.features_df.groupby('gauge_code')['basin_precip_mm'].transform('quantile', 0.25)
        self.features_df['dry_spell_precip'] = (
            (self.features_df['basin_precip_mm'] < precip_q25) & 
            self.features_df['basin_precip_mm'].notna()
        ).astype(int)
        
        # Discharge below 25th percentile
        discharge_q25 = self.features_df.groupby('gauge_code')['discharge_m3s'].transform('quantile', 0.25)
        self.features_df['dry_spell_discharge'] = (
            self.features_df['discharge_m3s'] < discharge_q25
        ).astype(int)
        
        # High evaporative demand (where available)
        aet_q75 = self.features_df.groupby('gauge_code')['basin_aet_est_mm'].transform('quantile', 0.75)
        self.features_df['dry_spell_aet_high'] = (
            (self.features_df['basin_aet_est_mm'] > aet_q75) & 
            self.features_df['basin_aet_est_mm'].notna()
        ).astype(int)
        
        # Composite dry spell: 2+ indicators active
        dry_indicators = self.features_df[[
            'dry_spell_precip', 'dry_spell_discharge', 'dry_spell_aet_high'
        ]].sum(axis=1)
        
        self.features_df['dry_spell'] = (dry_indicators >= 2).astype(int)
        
        # Classify severity
        self.features_df['dry_spell_severity'] = 'none'
        self.features_df.loc[self.features_df['dry_spell_discharge'] == 1, 'dry_spell_severity'] = 'low_flow'
        self.features_df.loc[
            (self.features_df['dry_spell_discharge'] == 1) & 
            (self.features_df['dry_spell_precip'] == 1), 
            'dry_spell_severity'
        ] = 'drought'
        
        dry_count = self.features_df['dry_spell'].sum()
        print(f"  ✓ Identified {dry_count} dry spell periods ({100*dry_count/len(self.features_df):.1f}%)")
        print(f"    Severity distribution:")
        print(self.features_df['dry_spell_severity'].value_counts().to_string())
    
    def add_flow_statistics(self) -> None:
        """Add flow regime statistics."""
        print("\n5. Adding flow regime features...")
        
        # Flow quantiles for each gauge
        for q in [0.1, 0.25, 0.5, 0.75, 0.9]:
            col_name = f'discharge_q{int(q*100)}'
            self.features_df[col_name] = self.features_df.groupby('gauge_code')['discharge_m3s'].transform('quantile', q)
        
        # Normalized discharge anomaly
        mean_q = self.features_df.groupby('gauge_code')['discharge_m3s'].transform('mean')
        std_q = self.features_df.groupby('gauge_code')['discharge_m3s'].transform('std')
        self.features_df['discharge_anomaly_std'] = (self.features_df['discharge_m3s'] - mean_q) / (std_q + 1e-6)
        
        # Base flow (low 10% mean for each gauge)
        base_flow = self.features_df.groupby('gauge_code')['discharge_m3s'].transform(
            lambda x: x.nsmallest(int(0.1*len(x))).mean()
        )
        self.features_df['discharge_baseflow_m3s'] = base_flow
        self.features_df['discharge_above_baseflow'] = (self.features_df['discharge_m3s'] - base_flow).clip(lower=0)
        
        print(f"  ✓ Added flow quantiles, anomalies, baseflow")
    
    def add_seasonal_features(self) -> None:
        """Add season-specific features."""
        print("\n6. Adding seasonal features...")
        
        # Season classification
        season_map = {1: 'winter', 2: 'winter', 3: 'spring', 4: 'spring', 5: 'spring',
                     6: 'summer', 7: 'summer', 8: 'summer', 9: 'fall', 10: 'fall', 11: 'fall', 12: 'winter'}
        self.features_df['season'] = self.features_df['month'].map(season_map)
        
        # Season-specific discharge/precip
        for season in ['winter', 'spring', 'summer', 'fall']:
            season_precip = self.features_df[self.features_df['season'] == season].groupby('gauge_code')['basin_precip_mm'].transform('mean')
            season_q = self.features_df[self.features_df['season'] == season].groupby('gauge_code')['discharge_m3s'].transform('mean')
            
            # Only set where we have data in that season for that gauge
            mask = self.features_df['season'] == season
            self.features_df.loc[mask, f'precip_{season}_mm'] = season_precip[mask]
            self.features_df.loc[mask, f'discharge_{season}_m3s'] = season_q[mask]
        
        # Fill NaN for seasons without data
        for season in ['winter', 'spring', 'summer', 'fall']:
            self.features_df[f'precip_{season}_mm'] = self.features_df.groupby('gauge_code')[f'precip_{season}_mm'].transform('bfill')
            self.features_df[f'discharge_{season}_m3s'] = self.features_df.groupby('gauge_code')[f'discharge_{season}_m3s'].transform('bfill')
        
        print(f"  ✓ Added seasonal features")
    
    def save_features(self) -> None:
        """Save engineered features to CSV."""
        print(f"\n7. Saving engineered features...")
        
        self.features_df.to_csv(OUTPUT_FEATURES, index=False)
        print(f"  ✓ Saved {len(self.features_df)} records to {OUTPUT_FEATURES.name}")
        print(f"  ✓ {len(self.features_df.columns)} total features")
    
    def generate_report(self) -> None:
        """Generate feature engineering documentation."""
        print(f"\n8. Generating documentation...")
        
        lines = [
            "# Comprehensive Feature Engineering Report\n",
            "## Overview\n",
            f"Total records: {len(self.features_df):,}\n",
            f"Total gauges: {self.features_df['gauge_code'].nunique()}\n",
            f"Time span: {self.features_df['year'].min()}-{self.features_df['year'].max()}\n",
            f"Total engineered features: {len(self.features_df.columns)}\n",
            "\n## Feature Categories\n",
            "### 1. Terrain Features (5 features)\n",
            "- basin_slope: Topographic slope (°)\n",
            "- basin_aspect: Slope aspect (°, 0-360)\n",
            "- basin_tpi: Topographic Position Index (elevation relative to neighbors)\n",
            "- basin_tri: Terrain Ruggedness Index (measure of terrain complexity)\n",
            "- basin_roughness: Surface roughness\n",
            "\n### 2. Landcover Features (10 features, % of basin area)\n",
            "- landcover_forest_pct: Closed + open forest, all leaf types (Copernicus CGLS-LC100 111-126)\n",
            "- landcover_shrubland_pct: Shrubs (lc_20)\n",
            "- landcover_grassland_pct: Herbaceous vegetation (lc_30)\n",
            "- landcover_cropland_pct: Cultivated/agricultural land (lc_40)\n",
            "- landcover_urban_pct: Urban/built-up area (lc_50)\n",
            "- landcover_bare_pct: Bare/sparse vegetation (lc_60)\n",
            "- landcover_snow_ice_pct: Permanent snow and ice (lc_70) — the real glacier/snowpack signal basin_glacier_pct never had\n",
            "- landcover_water_pct: Permanent water bodies (lc_80)\n",
            "- landcover_wetland_pct: Herbaceous wetland (lc_90)\n",
            "- landcover_moss_lichen_pct: Moss and lichen (lc_100)\n",
            "\n### 3. Climate Forcing Features (12+ features)\n",
            "- basin_precip_mm: Monthly precipitation (mm)\n",
            "- basin_tavg_c: Average temperature (°C)\n",
            "- basin_tmax_c: Estimated max temperature (°C)\n",
            "- basin_tmin_c: Estimated min temperature (°C)\n",
            "- basin_precip_lag1_mm: Previous month precipitation\n",
            "- basin_precip_lag12_mm: Same month previous year\n",
            "- basin_precip_3m_mm: 3-month rolling average\n",
            "- basin_anom_precip: Precipitation anomaly from climatology\n",
            "- basin_aet_est_mm: Estimated actual evapotranspiration\n",
            "- basin_precip_ratio_annual: Monthly precip as ratio of annual mean\n",
            "\n### 4. Flow Statistics Features (6+ features)\n",
            "- discharge_q10, q25, q50, q75, q90: Flow quantiles by gauge\n",
            "- discharge_baseflow_m3s: Base flow (low 10% mean)\n",
            "- discharge_above_baseflow: Excess flow above base\n",
            "- discharge_anomaly_std: Standardized flow anomaly\n",
            "\n### 5. Seasonal Features (8 features)\n",
            "- season: Winter, Spring, Summer, Fall\n",
            "- precip_[season]_mm: Mean seasonal precipitation\n",
            "- discharge_[season]_m3s: Mean seasonal discharge\n",
            "\n### 6. Dry Spell Classification Features (4 features)\n",
            "- dry_spell_precip: Binary indicator (low precip)\n",
            "- dry_spell_discharge: Binary indicator (low flow)\n",
            "- dry_spell_aet_high: Binary indicator (high evaporative demand)\n",
            "- dry_spell: Composite indicator (2+ active)\n",
            "- dry_spell_severity: Classification (none, low_flow, drought)\n",
            "\n## Dry Spell Definition\n",
            "A dry spell is identified when ≥2 of the following occur:\n",
            "1. Precipitation < 25th percentile for that gauge\n",
            "2. Discharge < 25th percentile for that gauge\n",
            "3. Evaporative demand > 75th percentile for that gauge\n",
            "\n## Data Coverage\n",
        ]
        
        # Add coverage statistics
        lines.append(f"- Non-null discharge: {self.features_df['discharge_m3s'].notna().sum()} / {len(self.features_df)} ({100*self.features_df['discharge_m3s'].notna().sum()/len(self.features_df):.1f}%)\n")
        lines.append(f"- Non-null basin_precip_mm: {self.features_df['basin_precip_mm'].notna().sum()} / {len(self.features_df)} ({100*self.features_df['basin_precip_mm'].notna().sum()/len(self.features_df):.1f}%)\n")
        lines.append(f"- Non-null basin_tavg_c: {self.features_df['basin_tavg_c'].notna().sum()} / {len(self.features_df)} ({100*self.features_df['basin_tavg_c'].notna().sum()/len(self.features_df):.1f}%)\n")
        lines.append(f"- Dry spells identified: {(self.features_df['dry_spell']==1).sum()} ({100*(self.features_df['dry_spell']==1).sum()/len(self.features_df):.1f}%)\n")
        lines.append(f"  - Drought (low flow + low precip): {(self.features_df['dry_spell_severity']=='drought').sum()}\n")
        lines.append(f"  - Low flow: {(self.features_df['dry_spell_severity']=='low_flow').sum()}\n")
        
        with open(OUTPUT_REPORT, 'w') as f:
            f.writelines(lines)
        
        print(f"  ✓ Saved report to {OUTPUT_REPORT.name}")
    
    def save_dry_spell_analysis(self) -> None:
        """Save per-gauge dry spell statistics."""
        print(f"\n9. Saving dry spell analysis...")
        
        analysis = self.features_df.groupby('gauge_code').agg({
            'discharge_m3s': ['mean', 'std', 'min', 'max'],
            'basin_precip_mm': ['mean', 'std'],
            'basin_tavg_c': ['mean'],
            'dry_spell': 'sum',
            'dry_spell_precip': 'sum',
            'dry_spell_discharge': 'sum',
            'dry_spell_aet_high': 'sum',
        }).round(2)
        
        analysis.columns = ['_'.join(col).strip() for col in analysis.columns.values]
        analysis.to_csv(OUTPUT_DRY_SPELL)
        
        print(f"  ✓ Saved dry spell analysis for {len(analysis)} gauges")


def main():
    """Orchestrate comprehensive feature engineering."""
    print("\n" + "="*70)
    print("COMPREHENSIVE FEATURE ENGINEERING FOR DISCHARGE MODELING")
    print("="*70)
    
    discharge_file = OUTPUT_DIR / "regional_discharge_data.csv"
    basin_climate_file = OUTPUT_DIR / "basin_climate.csv"
    
    if not discharge_file.exists():
        print(f"ERROR: {discharge_file.name} not found")
        return 1
    
    if not basin_climate_file.exists():
        print(f"ERROR: {basin_climate_file.name} not found")
        return 1
    
    engineer = ComprehensiveFeatureEngineer(discharge_file, basin_climate_file)
    
    engineer.add_terrain_features(GPKG)
    engineer.add_landcover_features(GPKG)
    engineer.add_climate_extremes()
    engineer.identify_dry_spells()
    engineer.add_flow_statistics()
    engineer.add_seasonal_features()
    
    engineer.save_features()
    engineer.generate_report()
    engineer.save_dry_spell_analysis()
    
    print("\n" + "="*70)
    print("✓ Feature engineering complete!")
    print("="*70)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
