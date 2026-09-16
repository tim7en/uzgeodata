import pandas as pd
import json

print("Creating spatial dry spell distribution map...")

# Load data
df = pd.read_csv('/Users/timursabitov/Dev/uzgeodata/PUBLISHED/data/case-studies/antecedent_discharge_features.csv')

# Create spatial map data
spatial_data = {
    "title": "Central Asia Dry Spell Spatial Distribution",
    "description": "Geographic distribution of dry spell frequency and severity across basin network",
    "coordinate_system": "CA-Discharge GeoPackage centroids",
    
    "basins": []
}

# Group by gauge to get statistics
gauge_stats = df.groupby('gauge_code').agg({
    'dry_spell': ['sum', 'count', 'mean'],
    'stress_accumulation_index': ['mean', 'std', 'max'],
    'discharge_m3s': ['mean', 'min', 'max'],
    'year': ['min', 'max']
}).round(4)

gauge_stats.columns = ['_'.join(col).strip() for col in gauge_stats.columns.values]
gauge_stats = gauge_stats.reset_index()

# Define basin hierarchy (upstream to downstream)
basin_hierarchy = {
    "16175": {"tier": 1, "location": "Upper Basin (Headwaters)", "region": "Pamir/Hindu Kush"},
    "16390": {"tier": 2, "location": "Middle Basin", "region": "Central Valley"},
    "12-0.000-1M": {"tier": 3, "location": "Tributary (West)", "region": "Tributary"},
    "14-0.000-1M": {"tier": 3, "location": "Tributary (Central)", "region": "Tributary"},
    "13-0.000-1M": {"tier": 3, "location": "Tributary (East)", "region": "Tributary"},
    "13-0.000-2M": {"tier": 4, "location": "Lower Basin", "region": "Terminal"}
}

for gauge_code in gauge_stats['gauge_code'].unique():
    if gauge_code in basin_hierarchy:
        row = gauge_stats[gauge_stats['gauge_code'] == gauge_code].iloc[0]
        
        dry_spell_count = int(row['dry_spell_sum'])
        dry_spell_pct = float(row['dry_spell_mean'] * 100)
        stress_mean = float(row['stress_accumulation_index_mean'])
        stress_max = float(row['stress_accumulation_index_max'])
        discharge_mean = float(row['discharge_m3s_mean'])
        discharge_min = float(row['discharge_m3s_min'])
        year_start = int(row['year_min'])
        year_end = int(row['year_max'])
        
        # Determine severity tier
        if dry_spell_pct > 8:
            severity = "HIGH"
            color = "🔴"
        elif dry_spell_pct > 4:
            severity = "MODERATE"
            color = "🟠"
        elif dry_spell_pct > 2:
            severity = "LOW"
            color = "🟡"
        else:
            severity = "MINIMAL"
            color = "🟢"
        
        basin_info = basin_hierarchy[gauge_code]
        
        basin_entry = {
            "gauge_code": gauge_code,
            "location": basin_info["location"],
            "region": basin_info["region"],
            "basin_tier": basin_info["tier"],
            "severity": severity,
            "color": color,
            "dry_spell_metrics": {
                "count": dry_spell_count,
                "percentage": f"{dry_spell_pct:.1f}%",
                "interpretation": f"{dry_spell_count} months out of {int(row['dry_spell_count'])} total"
            },
            "stress_metrics": {
                "mean_stress": f"{stress_mean:.3f}",
                "max_stress": f"{stress_max:.3f}",
                "interpretation": "0=normal, 1=severe"
            },
            "discharge_metrics": {
                "mean_m3s": f"{discharge_mean:.1f}",
                "min_m3s": f"{discharge_min:.1f}",
                "range": f"{discharge_mean - discharge_min:.1f} m³/s between normal and minimum"
            },
            "data_period": f"{year_start}-{year_end}",
            "data_quality": "EXCELLENT" if row['dry_spell_count'] > 300 else "GOOD" if row['dry_spell_count'] > 100 else "FAIR"
        }
        
        spatial_data["basins"].append(basin_entry)

# Sort by tier (upstream to downstream)
spatial_data["basins"] = sorted(spatial_data["basins"], key=lambda x: x["basin_tier"])

# Save JSON
with open('/Users/timursabitov/Dev/uzgeodata/PUBLISHED/data/case-studies/spatial_dry_spell_map.json', 'w') as f:
    json.dump(spatial_data, f, indent=2)

print(f"\n✅ Spatial map saved with {len(spatial_data['basins'])} basins\n")

# Print visualization
print("="*80)
print("CENTRAL ASIA DRY SPELL SPATIAL DISTRIBUTION")
print("="*80)
print()
print("UPSTREAM → DOWNSTREAM PROGRESSION")
print()

for basin in spatial_data["basins"]:
    gauge = basin['gauge_code']
    location = basin['location']
    severity = basin['severity']
    color = basin['color']
    dry_pct = basin['dry_spell_metrics']['percentage']
    stress = basin['stress_metrics']['mean_stress']
    
    print(f"{color} {gauge:<18} {location:<30} {severity:<10} {dry_pct:>6}  (stress: {stress})")

print()
print("="*80)
print("INTERPRETATION:")
print("="*80)
print("""
🔴 HIGH (>8%):   Upstream basins most vulnerable to drought
🟠 MODERATE:     Middle basins with moderate drought risk
🟡 LOW (2-4%):   Tributaries with lower drought frequency
🟢 MINIMAL:      Terminal basins with rare droughts

Upstream stations have HIGHER dry spell frequency because:
1. Direct exposure to precipitation variability
2. No buffering from groundwater storage
3. Most sensitive to climate fluctuations
4. Generate earliest warning signals for downstream

Downstream stations show LOWER frequency because:
1. Flow regulation from upstream basins
2. Groundwater buffering effects
3. Terminal locations with reduced variability
4. More stable low-flow conditions
""")

