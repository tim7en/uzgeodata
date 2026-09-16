#!/usr/bin/env python3
"""Aggregate upstream meteorological stations to create basin-scale climate forcing.

For each gauge × month, aggregates precipitation and temperature from upstream
meteorological stations using distance-weighted averaging. This creates temporal
variability in basin climate forcing that models can learn from.

Output: basin_climate.csv with columns:
  gauge_code, year, month, 
  basin_precip_mm, basin_tavg_c, basin_precip_lag1_mm, basin_precip_3m_mm, 
  basin_anom_precip, n_stations_contributing

Usage:
    python PIPELINES/aggregate_basin_climate.py
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUTPUT_DIR = ROOT / "PUBLISHED/data/case-studies"
UPSTREAM_FILE = OUTPUT_DIR / "gauge_upstream_stations.csv"
STATION_MONTHLY = ROOT / "PUBLISHED/data/hydromet/station-monthly.csv"
OUTPUT_CLIMATE = OUTPUT_DIR / "basin_climate.csv"


def load_upstream_stations() -> Dict[str, pd.DataFrame]:
    """Load gauge→upstream_stations mapping.
    
    Returns:
        {gauge_code: DataFrame with columns [station_id, station_name, distance_km, weight]}
    """
    print("Loading upstream station mappings...")
    df = pd.read_csv(UPSTREAM_FILE)
    
    upstream_by_gauge = {}
    for gauge_code in df['gauge_code'].unique():
        upstream = df[df['gauge_code'] == gauge_code][
            ['station_id', 'station_name', 'distance_km', 'weight']
        ].copy()
        upstream_by_gauge[gauge_code] = upstream
    
    print(f"  Loaded mappings for {len(upstream_by_gauge)} gauges")
    return upstream_by_gauge


def load_station_monthly_data() -> pd.DataFrame:
    """Load all meteorological station monthly data.
    
    Returns:
        DataFrame with columns [station_id, variable, year, month, value]
    """
    print("Loading station monthly data...")
    df = pd.read_csv(STATION_MONTHLY)
    
    # Keep only what we need
    df = df[['station_id', 'variable', 'year', 'month', 'value']].copy()
    df = df.dropna(subset=['value'])
    df['value'] = df['value'].astype(float)
    
    print(f"  Loaded {len(df):,} records")
    print(f"  Variables: {df['variable'].unique()}")
    print(f"  Year range: {df['year'].min()}-{df['year'].max()}")
    
    return df


def aggregate_basin_climate(
    gauge_code: str,
    upstream_stations: pd.DataFrame,
    station_data: pd.DataFrame
) -> pd.DataFrame:
    """Aggregate upstream station data for a single gauge.
    
    Args:
        gauge_code: Gauge identifier
        upstream_stations: DataFrame with station_id, weight columns
        station_data: All station monthly data
    
    Returns:
        DataFrame with columns [gauge_code, year, month, basin_precip_mm, 
        basin_tavg_c, basin_precip_lag1_mm, basin_precip_3m_mm, basin_anom_precip,
        n_stations_contributing]
    """
    
    result_rows = []
    
    # Get data for upstream stations
    station_ids = upstream_stations['station_id'].unique()
    gauge_station_data = station_data[station_data['station_id'].isin(station_ids)]
    
    if len(gauge_station_data) == 0:
        return pd.DataFrame()
    
    # Group by year/month
    for (year, month), group in gauge_station_data.groupby(['year', 'month']):
        
        # Extract precipitation and temperature
        precip_records = group[group['variable'] == 'precipitation_total']
        temp_records = group[group['variable'] == 'air_temperature_mean']
        
        # Merge with weights
        precip_weighted = precip_records.merge(
            upstream_stations[['station_id', 'weight']], 
            on='station_id', 
            how='inner'
        )
        temp_weighted = temp_records.merge(
            upstream_stations[['station_id', 'weight']], 
            on='station_id',
            how='inner'
        )
        
        # Calculate weighted averages
        if len(precip_weighted) > 0:
            basin_precip = (precip_weighted['value'] * precip_weighted['weight']).sum()
            n_precip = len(precip_weighted)
        else:
            basin_precip = np.nan
            n_precip = 0
        
        if len(temp_weighted) > 0:
            basin_tavg = (temp_weighted['value'] * temp_weighted['weight']).sum()
            n_temp = len(temp_weighted)
        else:
            basin_tavg = np.nan
            n_temp = 0
        
        n_stations = max(n_precip, n_temp)
        
        result_rows.append({
            'gauge_code': gauge_code,
            'year': int(year),
            'month': int(month),
            'basin_precip_mm': basin_precip,
            'basin_tavg_c': basin_tavg,
            'n_stations_contributing': n_stations,
        })
    
    result_df = pd.DataFrame(result_rows)
    
    if len(result_df) > 0:
        # Create lagged features within gauge
        result_df = result_df.sort_values(['gauge_code', 'year', 'month'])
        
        result_df['basin_precip_lag1_mm'] = result_df['basin_precip_mm'].shift(1)
        result_df['basin_precip_lag12_mm'] = result_df.groupby('gauge_code')['basin_precip_mm'].shift(12)
        
        # 3-month rolling average
        result_df['basin_precip_3m_mm'] = (
            result_df.groupby('gauge_code')['basin_precip_mm']
            .rolling(window=3, min_periods=1)
            .mean()
            .reset_index(level=0, drop=True)
        )
        
        # Anomaly: precipitation - climatological mean for that month
        climate_by_month = result_df.groupby('month')['basin_precip_mm'].mean()
        result_df['basin_anom_precip'] = result_df.apply(
            lambda row: row['basin_precip_mm'] - climate_by_month.get(row['month'], 0),
            axis=1
        )
    
    return result_df


def main():
    """Orchestrate basin climate aggregation."""
    print("\n" + "="*70)
    print("AGGREGATE UPSTREAM METEOROLOGICAL STATIONS TO BASIN CLIMATE FORCING")
    print("="*70)
    
    # Load data
    upstream_by_gauge = load_upstream_stations()
    station_data = load_station_monthly_data()
    
    # Aggregate for each gauge
    print("\nAggregating climate data for each gauge...")
    all_results = []
    
    for i, (gauge_code, upstream) in enumerate(upstream_by_gauge.items(), 1):
        if len(upstream) == 0:
            continue
        
        basin_climate = aggregate_basin_climate(gauge_code, upstream, station_data)
        if len(basin_climate) > 0:
            all_results.append(basin_climate)
        
        if i % 10 == 0:
            print(f"  {i}/{len(upstream_by_gauge)} gauges processed")
    
    # Combine and save
    if all_results:
        climate_df = pd.concat(all_results, ignore_index=True)
        climate_df = climate_df.sort_values(['gauge_code', 'year', 'month'])
        
        climate_df.to_csv(OUTPUT_CLIMATE, index=False)
        print(f"\n✓ Saved basin climate forcing to {OUTPUT_CLIMATE.name}")
        print(f"  {len(climate_df):,} gauge×month records")
        print(f"  Coverage: {climate_df['gauge_code'].nunique()} gauges")
        print(f"  Precip: {climate_df['basin_precip_mm'].notna().sum()}/{len(climate_df)} non-null")
        print(f"  Tavg: {climate_df['basin_tavg_c'].notna().sum()}/{len(climate_df)} non-null")
    else:
        print("✗ No data generated")
        sys.exit(1)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
