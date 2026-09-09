# Hydromet pipeline modules

Keep original deliveries and filenames in `storage/` for provenance.

| Module | Responsibility |
| --- | --- |
| `io.py` | Strict JSON and atomic CSV/JSON publication, with Windows lock retries. |
| `extraction.py` | Native-grid Earth Engine extraction, QA, cache and offline replay. |
| `statistics.py` | Site/month anomalies and block-bootstrap descriptive regression. |
| `../build_hydromet_station_network.py` | Identity, coordinates and metadata cross-checks. |
| `../build_regional_climate_observations.py` | Workbook parsing, calendar audit and QC. |
| `../build_regional_glacier_inventories.py` | Separate 2023 point catalogues, not GLIMS outlines. |
| `../build_regional_station_study.py` | Analysis orchestration and public projections. |

CLI wrappers retain established paths and npm commands. Cache recipe versions
must change when masks, grid support or transforms change. Missing offline
caches are errors, never permission to fabricate data.

```powershell
npm run stations:network
npm run stations:climate
npm run stations:glaciers-regional
npm run cases:regional
npm run cases:regional -- --offline
npm run test:hydromet
```
