#!/usr/bin/env python3
"""Trace upstream meteorological stations for each gauge basin.

For each CA-discharge gauge:
1. Load gauge location and basin info
2. Identify all meteorological stations within basin boundary or upstream
3. Create distance-weighted upstream forcing features
4. Save features for each gauge

Outputs:
- gauge_upstream_stations.csv (which stations influence each gauge)
- gauge_upstream_features.csv (aggregated upstream forcing by gauge)

Usage:
    python PIPELINES/integrate_upstream_stations.py
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd
from datetime import datetime
from math import radians, cos, sin, asin, sqrt


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "PUBLISHED/data"
GEODATA_DIR = ROOT / "GEODATA"
GPKG = GEODATA_DIR / "ca-discharge-2023/CA-discharge.gpkg"


def haversine(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Calculate great circle distance between two points (km)."""
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371  # Earth radius in km
    return c * r


def load_gauges(gpkg: Path) -> pd.DataFrame:
    """Load gauge locations from CA-discharge GeoPackage."""
    print("Loading gauge locations from CA-discharge...")
    
    conn = sqlite3.connect(gpkg)
    
    query = """
    SELECT CODE, LON, LAT, BASIN, REGION
    FROM basin_attributes
    WHERE CODE IN (SELECT DISTINCT CODE FROM gauges)
    """
    
    gauges = pd.read_sql(query, conn)
    conn.close()
    
    print(f"  Loaded {len(gauges)} gauges with coordinates")
    return gauges


def load_meteorological_stations() -> pd.DataFrame:
    """Load meteorological station locations."""
    print("Loading meteorological stations...")
    
    meteo_file = DATA_DIR / "hydroclimate/meteo-stations.geojson"
    
    if not meteo_file.exists():
        print(f"  ⚠ File not found: {meteo_file}")
        print(f"    Using placeholder data (no upstream integration)")
        return pd.DataFrame({
            'id': [],
            'longitude': [],
            'latitude': [],
            'elevation': [],
            'name': []
        })
    
    import json
    with meteo_file.open() as f:
        data = json.load(f)
    
    stations = []
    for feature in data['features']:
        props = feature['properties']
        coords = feature['geometry']['coordinates']
        stations.append({
            'id': props.get('id') or props.get('station_id'),
            'longitude': coords[0],
            'latitude': coords[1],
            'elevation': props.get('elevation', 0),
            'name': props.get('name', ''),
        })
    
    stations_df = pd.DataFrame(stations)
    print(f"  Loaded {len(stations_df)} meteorological stations")
    
    return stations_df


def find_upstream_stations(gauge_row: pd.Series, stations_df: pd.DataFrame, 
                          max_distance_km: float = 100) -> pd.DataFrame:
    """Find upstream stations for a gauge using distance criterion.
    
    Note: Simplified approach using distance only.
    Full implementation would use:
    - Basin boundary polygon clipping
    - Flow direction rasters
    - Upstream contributing area calculation
    """
    
    gauge_lon, gauge_lat = gauge_row['LON'], gauge_row['LAT']
    
    # Calculate distances to all stations
    distances = []
    for _, station in stations_df.iterrows():
        dist = haversine(gauge_lon, gauge_lat, 
                        station['longitude'], station['latitude'])
        distances.append(dist)
    
    stations_df = stations_df.copy()
    stations_df['distance_km'] = distances
    
    # Filter to nearby stations
    upstream = stations_df[stations_df['distance_km'] <= max_distance_km].copy()
    upstream = upstream.sort_values('distance_km')
    
    # Weight by inverse distance (closer = higher weight)
    if len(upstream) > 0:
        upstream['weight'] = 1.0 / (1.0 + upstream['distance_km'])
        upstream['weight'] /= upstream['weight'].sum()  # Normalize to sum to 1
    
    return upstream


def extract_upstream_features(gauge_code: str, upstream: pd.DataFrame, 
                              discharge_df: pd.DataFrame) -> Dict:
    """Extract aggregated upstream features for a gauge.
    
    For each upstream station, aggregate its meteorological data
    weighted by distance to the gauge.
    """
    
    # This is a placeholder - in full implementation:
    # - Load time series for each upstream station
    # - Aggregate precipitation/temperature by distance-weighting
    # - Calculate upstream mean forcing
    # - Create features: upstream_precip_mm, upstream_temp_c, etc.
    
    if len(upstream) == 0:
        return {
            'n_upstream_stations': 0,
            'upstream_precip_mm': 0.0,
            'upstream_temp_c': 0.0,
            'upstream_mean_distance_km': 0.0,
        }
    
    # Extract station names - handle different possible column names
    station_names = []
    if 'station_name' in upstream.columns:
        station_names = upstream['station_name'].tolist()
    elif 'name' in upstream.columns:
        station_names = upstream['name'].tolist()
    else:
        station_names = ['station_' + str(i) for i in range(len(upstream))]
    
    return {
        'n_upstream_stations': len(upstream),
        'upstream_precip_mm': 0.0,  # Placeholder: aggregate from stations
        'upstream_temp_c': 0.0,      # Placeholder: aggregate from stations
        'upstream_mean_distance_km': float((upstream['distance_km'] * upstream['weight']).sum()),
        'upstream_stations': station_names,
        'upstream_weights': upstream['weight'].tolist(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gpkg', type=Path, default=GPKG,
                       help='CA-discharge GeoPackage path')
    parser.add_argument('--output_dir', type=Path, default=DATA_DIR / "case-studies",
                       help='Output directory')
    
    args = parser.parse_args()
    
    if not args.gpkg.exists():
        print(f"ERROR: GeoPackage not found: {args.gpkg}")
        return 1
    
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load data
    gauges = load_gauges(args.gpkg)
    stations = load_meteorological_stations()
    
    if len(stations) == 0:
        print("\n⚠ No meteorological stations loaded.")
        print("  Upstream integration currently limited to placeholder features.")
        print("  Next: python PIPELINES/generate_gauge_predictions.py")
        return 0
    
    # Find upstream stations for each gauge
    print("\nTracing upstream meteorological stations for each gauge...")
    
    upstream_records = []
    for _, gauge_row in gauges.iterrows():
        gauge_code = gauge_row['CODE']
        upstream = find_upstream_stations(gauge_row, stations, max_distance_km=100)
        
        for _, station in upstream.iterrows():
            upstream_records.append({
                'gauge_code': gauge_code,
                'station_id': station['id'],
                'station_name': station['name'],
                'station_elevation_m': station['elevation'],
                'distance_km': station['distance_km'],
                'weight': station['weight'],
            })
    
    upstream_df = pd.DataFrame(upstream_records)
    
    if len(upstream_df) > 0:
        upstream_file = args.output_dir / "gauge_upstream_stations.csv"
        upstream_df.to_csv(upstream_file, index=False)
        print(f"  Found {len(upstream_df)} gauge-station pairs")
        print(f"  Saved to {upstream_file.name}")
    
    # Extract upstream features (placeholder - full implementation in Phase 2)
    print("\nExtracting upstream forcing features...")
    
    upstream_features = []
    for gauge_code in gauges['CODE'].unique():
        gauge_upstream = upstream_df[upstream_df['gauge_code'] == gauge_code]
        features = extract_upstream_features(gauge_code, gauge_upstream, None)
        features['gauge_code'] = gauge_code
        upstream_features.append(features)
    
    upstream_features_df = pd.DataFrame(upstream_features)
    
    features_file = args.output_dir / "gauge_upstream_features.csv"
    upstream_features_df.to_csv(features_file, index=False)
    print(f"  Saved upstream features to {features_file.name}")
    
    print(f"\n✓ Upstream station tracing complete")
    print(f"  Note: Full aggregation of upstream time series data is Phase 2 enhancement")
    print(f"  Next: python PIPELINES/generate_gauge_predictions.py")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
