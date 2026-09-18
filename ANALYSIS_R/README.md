# ANALYSIS_R

Per-dataset descriptive QC scripts in R, one script per dataset documented in
[docs/papers/paper-02-original-data-release.md](../docs/papers/paper-02-original-data-release.md),
organised into the same four categories: `site/`, `remote/`, `grid/`,
`modelled/`.

Each script reads one dataset straight from `PUBLISHED/data/`, reports
dimensions, missingness, duplicates and column ranges, and — wherever
paper-02 states a count or a statistic for that dataset — recomputes it
independently from the file and prints `PASS`/`MISMATCH` rather than assuming
agreement. Nothing here fits a model, re-derives a scientific result, or
edits a published file; it is an audit layer that sits next to the data,
not a second pipeline.

## Run

```sh
# One dataset:
Rscript ANALYSIS_R/site/01_meteo_stations.R

# Everything, in the order the datasets appear in paper-02:
Rscript ANALYSIS_R/run_all.R
```

Every script can be run standalone from any working directory, or via
`run_all.R`; both paths are exercised and both work. `run_all.R` continues
past a failing script and prints a pass/fail summary at the end.

Per-dataset summary tables are also written to `ANALYSIS_R/output/*.csv`
(git-ignored — they are regenerated on every run, not source).

## Requirements

R packages: `readr`, `dplyr`, `jsonlite` (all part of the `tidyverse`
install already on this machine), plus `arrow` for `grid/07_regional_climate_cube.R`
only, which reads the Hive-partitioned Parquet cube under
`PUBLISHED/data/atlas/cube/`:

```r
install.packages("arrow", type = "binary")
```

## Datasets covered

| Script | Dataset | Paper-02 section |
| --- | --- | --- |
| `site/01_meteo_stations.R` | Meteorological station network | 2.1.1 |
| `site/02_discharge_gauges.R` | CA-discharge archive + local Pskem daily record | 2.1.2 |
| `site/03_station_gauge_network_audit.R` | Station/gauge identity and calendar-convention audit | 2.1.3 |
| `remote/04_remote_station_extractions.R` | Earth Engine products extracted at station coordinates | 2.2.1 |
| `remote/05_glacier_inventories.R` | GLIMS headwater outlines, regional point centres, Pskem inventory | 2.2.2 |
| `remote/06_infrastructure_inventories.R` | Dams (Global Dam Watch) and water bodies (HydroLAKES) | 2.2.3 |
| `grid/07_regional_climate_cube.R` | TerraClimate/ERA5-Land/MODIS monthly cube, level-12 basins | 2.3 |
| `grid/08_headwater_elevation_bands.R` | SRTM-derived headwater elevation-band stratification | 2.3 |
| `modelled/09_pskem_hbv_model.R` | Pskem daily HBV-type model, both evaluation splits | 2.4.1 |
| `modelled/10_regional_discharge_ensemble.R` | Regional stacking-ensemble monthly discharge model | 2.4.2 |
| `modelled/11_sabitov_adaptation.R` | Sabitov (2018) thesis adaptation, four daily models | 2.4.3 |

## Findings surfaced by the first run (2026-09-18)

Every paper-02 count/statistic that these scripts check reproduces exactly
from the released files, with the following exceptions — all now folded into
paper-02 itself (§2.1.2, §2.2.1, §2.2.2, §2.4.2, §2.4.3, §3) rather than left
only here:

- **`site/02_discharge_gauges.R`**: recomputed Pearson r against the local
  Pskem record matches paper-02 (0.9982 vs. stated 0.998), but recomputed
  RMSE and bias from the same published CSV (3.96 m³/s, −0.407 m³/s) do not
  match `CA-DISCHARGE-INTEGRATION.md`'s stated 0.35 m³/s / −0.09 m³/s —
  roughly a 10x gap, still unreconciled. Cite the correlation, not the
  RMSE/bias, until this is resolved.
- **`remote/04_remote_station_extractions.R`**: `station-product-monthly.csv`
  actually holds a CHIRPS/CHIRTS/ERA5-Land product comparison at three
  stations, not the MOD13Q1/MOD11A2/MOD10A1 set paper-02 §2.2.1's main table
  documents — now described in §2.2.1 as a seventh, smaller comparison.
- **`remote/05_glacier_inventories.R`**: the GLIMS headwater outline set is
  far larger and more geographically extensive than the first paper-02 draft
  described — 25,294 glaciers, 14,328 km², spanning 67.6–78.4°E / 34.6–42.5°N
  (Pamir through Tian Shan, well beyond Uzbekistan). Its per-submission
  provenance (`glacier-source-attribution.csv`, 93 GLIMS records) shows
  Central Asian coverage is dominated by a single Russian Academy of Sciences
  submission (61/93, survey dates averaging 2002) plus a Texas A&M-led
  submission for the Afghan/Pakistani Hindu Kush portion — **not** a modern,
  dedicated national inventory from Kyrgyzstan or Tajikistan analogous to the
  Uzbek Kashkadarya/Surkhandarya workbooks that back the smaller 210-point
  catalogue. Now documented in full in paper-02 §2.2.2.
- **`modelled/10_regional_discharge_ensemble.R`**: all 38 trained gauges have
  `glacier_pct == 0` (not just "few qualifying gauges" as the case-study
  narrative states); and every `terraclimate_*`/`upstream_*` predictor column
  in `regional_discharge_predictions.csv` is 100% missing, despite those
  being the model's documented primary predictors.
- **`modelled/11_sabitov_adaptation.R`**: this adaptation's Models 2 and 4
  score far higher (NSE ≈ 0.84) than the original thesis reports for the
  same model numbers (0.23, 0.29), while Models 1 and 3 land close to the
  thesis figures — consistent with paper-02's own warning that this is an
  adaptation on possibly-different forcing, not a proven reproduction, but a
  large enough gap to flag explicitly.
