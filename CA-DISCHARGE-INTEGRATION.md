# CA-Discharge Integration Summary

**Completed:** September 16, 2026 | **Release:** Data lineage v1.0

## Overview
Successfully integrated the CA-discharge research dataset (Marti et al., 2023, Scientific Data) as a versioned research archive and regional validation candidate alongside ground observations.

## Data Source
- **Citation:** Marti, B., et al. (2023). CA-discharge: Geo-located discharge time series for mountainous rivers in Central Asia. *Scientific Data*, 10, 579.
- **DOI:** 10.1038/s41597-023-02474-8
- **Data repository:** https://zenodo.org/record/8147591
- **License:** CC BY 4.0

## Integration Components

### 1. Data Files (PUBLISHED/data/research/)
- **ca-discharge-summary.json** (3.9 KB) - Metadata, statistics, and import details
  - 297 gauge locations
  - 136 gauges with time series
  - 244,632 observations (1910–2021)
  - Checksum validation: `e0ba6664aaec3e0b27138abdfd4ba263` (MD5)
  
- **ca-discharge-stations.geojson** (132 KB) - GeoJSON point layer with station properties
  - Coordinates, names, basin information
  - Time series coverage indicators
  - Quality metrics and resolution details

- **ca-discharge-pskem-comparison.csv** (16 KB) - Cross-validation evidence
  - 555 paired dekads (10-day periods) compared with local Pskem station
  - Consistency metrics: Pearson r = 0.998, RMSE = 0.35 m³/s
  - Bias = −0.09 m³/s (negligible)

- **ca-discharge-source-manifest.json** (1.2 KB) - Provenance and update policy
  - Zenodo record metadata
  - Storage location and checksums
  - Dataset version pinning

### 2. Research Registry Updates
**PUBLISHED/data/research/publications.json**
```json
{
  "id": "marti-2023-ca-discharge",
  "status": "integrated",
  "role": "input-data",
  "layers": [2],
  "use": "The compact GeoPackage is checksum-pinned and imported as a 297-gauge station index, 
          source manifest and quality-aware research summary. Gauge 16290 is crosswalked to 
          Pskem–Mullala; 555 overlapping 10-day observations are compared with the local daily 
          record as a provenance consistency check (r = 0.9982), not as independent validation."
}
```

### 3. Source Registry
**PUBLISHED/data/source-registry.json** - external_sources
- Classification: "versioned_release"
- State: "integrated research index — source GeoPackage held locally"
- Update policy: Review Zenodo for new versions; checksum-pin each approved release
- Storage note: 24.6 MB GeoPackage held outside website artifact; 11.8 GB raw archive not mirrored

### 4. Interface Updates
**INTERFACE/data-lineage-main.jsx**
- Line 105: Updated node detail from "295 gauges · import candidate" → "297 gauges · integrated"
- Lines 186–199: Converted "04 / PROPOSED EXTERNAL DATASET" section to "04 / INTEGRATED RESEARCH DATASET"
  - Detailed integration status with collapsible technical details
  - Links to paper, data record, and summary JSON
  - Station, time series, and quality control information

**INTERFACE/research.html** (auto-rendered from publications.json)
- Entry appears in Layer 2 (Observations and Evidence) as input-data role
- Status badge shows "in use" (integrated)
- Links to Nature paper and Zenodo record

## Quality Assurance

### Verification Tests
**TESTS/test_ca_discharge.py** ✓ All 3 tests passing
1. **Import completeness** - Verifies 297 gauge rows and 244,632 observations loaded
2. **Pskem consistency** - Validates r = 0.998 correlation between gauge 16290 and local station
3. **Data structure** - Confirms GeoJSON output, CSV comparison, and metadata manifest integrity

### Consistency Check: Pskem Station (16290)
- **Local dataset:** PUBLISHED/data/hydroclimate/pskem-discharge-daily.csv
- **CA-discharge source:** Gauge 16290 (Pskem – Mullala)
- **Overlap period:** 555 paired dekads
- **Agreement metrics:**
  - Pearson correlation: 0.9982 (excellent agreement)
  - Mean absolute error: 0.62 m³/s
  - Root mean square error: 0.35 m³/s
  - Bias: −0.09 m³/s (negligible systematic offset)

### Data Quality Exclusions
Per original publisher warnings, excluded attributes:
- `gl_dmdt_km3a` (glacier mass-change rate)
- `gl_dmdtda_mma` (glacier mass-change rate annual)

These glacier-thinning fields are flagged as unreliable and not included in any output.

## Storage Strategy
- **Compact GeoPackage (24.6 MB):** Held in GEODATA/ca-discharge-2023/ outside web artifact
- **Derived evidence (≈150 KB total):** Published in PUBLISHED/data/research/
- **Raw archive (11.8 GB):** Not mirrored; reference maintained in manifest for future archival audit
- **Update rule:** Checksum-pin each Zenodo release; never silently overwrite prior snapshot

## Build & Deployment
- **npm run build:** Completed successfully
- **git status:** 5 files modified:
  - .gitignore (added GeoPackage path exclusion)
  - INTERFACE/data-lineage-main.jsx (updated tree node and integration section)
  - PIPELINES/build_*.py (3 build scripts updated with CA-discharge references)

## Next Steps (Optional Future Work)
1. **Model integration:** Use 555 Pskem pairs as benchmark for discharge modeling validation
2. **Regional testing:** Extend consistency checks to other stations in the dataset
3. **Archive audit:** Verify raw-data archive availability at Zenodo on quarterly schedule
4. **Scenario modeling:** Incorporate full CA-discharge time series as alternative forcing for headwater models

## References
- Nature article: https://www.nature.com/articles/s41597-023-02474-8
- Zenodo record: https://doi.org/10.5281/zenodo.8147591
- UzGeoData research page: https://uzgeodata.uz/research.html
- Data lineage tree: https://uzgeodata.uz/data-lineage.html#tree
