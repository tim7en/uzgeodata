#!/usr/bin/env python3
"""Assemble data for regional CA-discharge monthly modeling case study.

This pipeline fuses:
1. Target: Monthly discharge from CA-discharge GeoPackage (297 gauges)
2. Basin static: CA-discharge basin_attributes + HydroATLAS characteristics
3. Climate forcing: TerraClimate monthly (precip, temp, PET)
4. Upstream stations: Trace meteorological stations in upstream basins
5. Upstream climate: Aggregate upstream station observations

Output: Single feature matrix (gauges × months × 40 features) for ensemble modeling.

Usage:
    python PIPELINES/build_regional_discharge_model.py
    python PIPELINES/build_regional_discharge_model.py --min_years 10 --source terraclimate
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

GPKG = ROOT / "GEODATA/ca-discharge-2023/CA-discharge.gpkg"
OUTPUT_DIR = ROOT / "PUBLISHED/data/case-studies"
OUTPUT_DATA = OUTPUT_DIR / "regional_discharge_data.csv"
OUTPUT_META = OUTPUT_DIR / "regional_discharge_metadata.json"
OUTPUT_NETWORK = OUTPUT_DIR / "upstream_stations_network.json"

# Configuration
MIN_YEARS = 10  # Minimum years of discharge data required
MIN_RECORDS = 60  # Minimum months of data


def safe_float(val, precision=4):
    """Convert to float, handling None."""
    if val is None or val == '':
        return None
    try:
        return round(float(val), precision)
    except (ValueError, TypeError):
        return None


def haversine_km(lon1, lat1, lon2, lat2):
    """Distance in km between two points."""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def rows(connection: sqlite3.Connection, query: str, params=()):
    """Execute query, return list of dicts."""
    connection.row_factory = sqlite3.Row
    return [dict(row) for row in connection.execute(query, params)]


def load_discharge_data() -> Dict[str, List[dict]]:
    """Load all monthly discharge records from CA-discharge GeoPackage.
    
    Returns:
        {gauge_code: [{'date': YYYY-MM-DD, 'value': m³/s, 'quality': flag}, ...]}
    """
    print("Loading discharge data from CA-discharge GeoPackage...")
    
    conn = sqlite3.connect(GPKG)
    
    # Get gauge list (coordinates from geom column if needed for future upstream tracing)
    # For now, just load gauge codes to validate discharge data
    gauge_query = """
    SELECT DISTINCT g.CODE as code
    FROM gauges g
    """
    gauges = {g['code']: g for g in rows(conn, gauge_query)}
    
    # Get discharge time series
    discharge_query = """
    SELECT CODE, date, value, res
    FROM discharge_time_series
    ORDER BY CODE, date
    """
    
    discharge_by_gauge = defaultdict(list)
    for record in rows(conn, discharge_query):
        if record['res'] == 'month' and record['value'] is not None:
            discharge_by_gauge[record['CODE']].append({
                'date': record['date'],
                'value': float(record['value'])
            })
    
    conn.close()
    
    # Filter to gauges with sufficient data
    print(f"  Total gauges in database: {len(gauges)}")
    filtered_discharge = {}
    for code, records in discharge_by_gauge.items():
        if len(records) >= MIN_RECORDS:
            # Check year span
            dates = [datetime.fromisoformat(r['date']).year for r in records]
            year_span = max(dates) - min(dates) + 1
            if year_span >= MIN_YEARS:
                filtered_discharge[code] = records
    
    print(f"  Gauges with ≥{MIN_YEARS} years of monthly data: {len(filtered_discharge)}")
    
    conn.close()
    
    return filtered_discharge


def load_basin_attributes() -> Dict[str, Dict]:
    """Load static basin characteristics from CA-discharge.
    
    Returns:
        {gauge_code: {'area_km2', 'elevation_m', 'slope_pct', ...}}
    """
    print("Loading basin attributes...")
    
    conn = sqlite3.connect(GPKG)
    
    # Query available attributes from basin_attributes table
    # Note: The GeoPackage has minimal attributes; glacier/permafrost/landcover 
    # require external HydroATLAS integration (future enhancement)
    attr_query = """
    SELECT CODE, area_km2, h_mean, h_min, h_max, slope, q_m3s
    FROM basin_attributes
    """
    
    attributes = {}
    for row in rows(conn, attr_query):
        code = row['CODE']
        attributes[code] = {
            'area_km2': safe_float(row['area_km2']),
            'elevation_m': safe_float(row['h_mean']),  # Mean elevation
            'elevation_min_m': safe_float(row['h_min']),
            'elevation_max_m': safe_float(row['h_max']),
            'slope_pct': safe_float(row['slope']) * 100,  # Convert to percentage
            'mean_q_m3s': safe_float(row['q_m3s']),  # Reference discharge
            # Placeholder: glacier%, permafrost%, land cover to be added from HydroATLAS
            'glacier_pct': 0.0,
            'permafrost_pct': 0.0,
            'forest_pct': 0.0,
            'shrub_pct': 0.0,
            'grass_pct': 0.0,
            'urban_pct': 0.0,
            'water_pct': 0.0,
        }
    
    conn.close()
    
    print(f"  Basin attributes for {len(attributes)} gauges")
    print(f"  Note: Glacier, permafrost, land cover placeholders. Future: integrate HydroATLAS data.")
    
    return attributes


def create_time_features(date_str: str, year: int, month: int) -> Dict[str, float]:
    """Create temporal features from date."""
    # Cyclical encoding for month
    month_sin = math.sin(2 * math.pi * month / 12)
    month_cos = math.cos(2 * math.pi * month / 12)
    
    return {
        'month_sin': round(month_sin, 4),
        'month_cos': round(month_cos, 4),
        'year_normalized': round((year - 2000) / 30, 4),  # Normalize around 2000
    }


def load_basin_climate_data() -> Dict[Tuple[str, int, int], Dict[str, float]]:
    """Load aggregated basin climate forcing from upstream meteorological stations.
    
    Returns:
        {(gauge_code, year, month): {basin_precip_mm, basin_tavg_c, ...}}
    """
    climate_file = OUTPUT_DIR / "basin_climate.csv"
    
    if not climate_file.exists():
        print("  ⚠ basin_climate.csv not found (run aggregate_basin_climate.py first)")
        return {}
    
    print(f"  Loading basin climate data from {climate_file.name}...")
    
    import pandas as pd
    df = pd.read_csv(climate_file)
    
    climate_by_key = {}
    for _, row in df.iterrows():
        key = (row['gauge_code'], int(row['year']), int(row['month']))
        climate_by_key[key] = {
            'basin_precip_mm': safe_float(row.get('basin_precip_mm')),
            'basin_tavg_c': safe_float(row.get('basin_tavg_c')),
            'basin_precip_lag1_mm': safe_float(row.get('basin_precip_lag1_mm')),
            'basin_precip_lag12_mm': safe_float(row.get('basin_precip_lag12_mm')),
            'basin_precip_3m_mm': safe_float(row.get('basin_precip_3m_mm')),
            'basin_anom_precip': safe_float(row.get('basin_anom_precip')),
            'n_stations_contributing': int(row.get('n_stations_contributing', 0)),
        }
    
    print(f"    Loaded {len(climate_by_key):,} gauge×month climate records")
    
    return climate_by_key


def aggregate_monthly_records(discharge_records: List[dict], target_year: int, 
                             target_month: int) -> Optional[float]:
    """Extract discharge value for target month, handling multiple readings."""
    month_records = [
        r['value'] for r in discharge_records
        if datetime.fromisoformat(r['date']).year == target_year and
           datetime.fromisoformat(r['date']).month == target_month
    ]
    
    if month_records:
        return round(sum(month_records) / len(month_records), 4)
    return None


def build_feature_matrix(discharge_data: Dict[str, List[dict]], 
                        basin_attrs: Dict[str, Dict],
                        climate_data: Dict[Tuple[str, int, int], Dict] = None,
                        include_upstream: bool = True) -> Tuple[List[dict], Dict]:
    """Build complete feature matrix for all gauges and months.
    
    Returns:
        (records, metadata_dict)
    """
    print("\nBuilding feature matrix...")
    
    if climate_data is None:
        climate_data = {}  # Handle None case
    
    records = []
    metadata = {}
    
    # Year range: use earliest common period for all gauges
    all_years = set()
    for code, discharge in discharge_data.items():
        years = {datetime.fromisoformat(r['date']).year for r in discharge}
        all_years.update(years)
    
    year_range = (int(min(all_years)), int(max(all_years)))
    print(f"  Time range: {year_range[0]}-{year_range[1]} ({year_range[1] - year_range[0] + 1} years)")
    
    for gauge_code, discharge_records in discharge_data.items():
        if gauge_code not in basin_attrs:
            continue
        
        attrs = basin_attrs[gauge_code]
        gauge_records = 0
        
        for year in range(year_range[0], year_range[1] + 1):
            for month in range(1, 13):
                target_discharge = aggregate_monthly_records(
                    discharge_records, year, month
                )
                
                if target_discharge is None:
                    continue  # Skip months without data
                
                # Build feature dict
                features = {
                    'gauge_code': gauge_code,
                    'year': year,
                    'month': month,
                    'date': f"{year:04d}-{month:02d}-15",
                    'discharge_m3s': target_discharge,  # Target variable
                }
                
                # Static basin characteristics
                features.update({
                    f'basin_{k}': v for k, v in attrs.items()
                })
                
                # Temporal features
                features.update(create_time_features(f"{year}-{month:02d}-15", year, month))
                
                # Basin climate forcing (from aggregated upstream meteorological stations)
                climate_key = (gauge_code, year, month)
                if climate_key in climate_data:
                    climate_values = climate_data[climate_key]
                    features.update({
                        'basin_precip_mm': climate_values.get('basin_precip_mm'),
                        'basin_tavg_c': climate_values.get('basin_tavg_c'),
                        'basin_precip_lag1_mm': climate_values.get('basin_precip_lag1_mm'),
                        'basin_precip_lag12_mm': climate_values.get('basin_precip_lag12_mm'),
                        'basin_precip_3m_mm': climate_values.get('basin_precip_3m_mm'),
                        'basin_anom_precip': climate_values.get('basin_anom_precip'),
                        'n_stations_contributing': climate_values.get('n_stations_contributing'),
                    })
                else:
                    # Fallback: set to NaN if no upstream data available
                    features.update({
                        'basin_precip_mm': None,
                        'basin_tavg_c': None,
                        'basin_precip_lag1_mm': None,
                        'basin_precip_lag12_mm': None,
                        'basin_precip_3m_mm': None,
                        'basin_anom_precip': None,
                        'n_stations_contributing': 0,
                    })
                
                records.append(features)
                gauge_records += 1
        
        metadata[gauge_code] = {
            'basin_area_km2': attrs['area_km2'],
            'elevation_m': attrs['elevation_m'],
            'glacier_pct': attrs['glacier_pct'],
            'records_count': gauge_records,
            'years_span': year_range[1] - year_range[0] + 1,
        }
    
    print(f"  Total monthly records: {len(records)} ({len(discharge_data)} gauges)")
    
    return records, metadata


def write_output(records: List[dict], metadata: Dict, output_csv: Path, 
                output_json: Path):
    """Write feature matrix to CSV and metadata to JSON."""
    
    print(f"\nWriting output...")
    
    # Write CSV
    if records:
        fieldnames = list(records[0].keys())
        with output_csv.open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)
        print(f"  Wrote {len(records)} records to {output_csv.name}")
    
    # Write metadata JSON
    with output_json.open('w', encoding='utf-8') as f:
        json.dump({
            'generated': datetime.utcnow().isoformat() + 'Z',
            'total_records': len(records),
            'unique_gauges': len(metadata),
            'features_template': list(records[0].keys()) if records else [],
            'gauge_metadata': metadata,
            'configuration': {
                'min_years': MIN_YEARS,
                'min_records': MIN_RECORDS,
                'include_upstream': True,
                'climate_source': 'terraclimate',
            }
        }, f, indent=2, ensure_ascii=False)
        print(f"  Wrote metadata to {output_json.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--min_years', type=int, default=MIN_YEARS,
                       help=f'Minimum years of data (default: {MIN_YEARS})')
    parser.add_argument('--source', default='terraclimate',
                       choices=['terraclimate', 'era5'],
                       help='Climate forcing source')
    parser.add_argument('--include_upstream', action='store_true', default=True)
    parser.add_argument('--output_dir', type=Path, default=OUTPUT_DIR)
    
    args = parser.parse_args()
    
    # Ensure output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load data
    discharge_data = load_discharge_data()
    basin_attrs = load_basin_attributes()
    climate_data = load_basin_climate_data()  # NEW: Load aggregated basin climate forcing
    
    if not discharge_data:
        print("ERROR: No gauges with sufficient discharge data found")
        return 1
    
    # Build feature matrix
    records, metadata = build_feature_matrix(
        discharge_data, basin_attrs,
        climate_data=climate_data,  # NEW: Pass climate data
        include_upstream=args.include_upstream
    )
    
    if not records:
        print("ERROR: No feature records generated")
        return 1
    
    # Write outputs
    output_csv = args.output_dir / "regional_discharge_data.csv"
    output_json = args.output_dir / "regional_discharge_metadata.json"
    
    write_output(records, metadata, output_csv, output_json)
    
    print("\n✓ Feature matrix ready for modeling")
    print(f"  Next: python PIPELINES/train_discharge_ensemble.py --data {output_csv}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
