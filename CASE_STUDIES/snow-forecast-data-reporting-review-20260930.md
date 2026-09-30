# Snow forecast: reproducibility and reporting review (2026-09-30)

**Rerun completed:** The regional builder now writes full-precision
`operational_inputs` into each gauge and issue record of `gauges.json`, including
when it reuses score checkpoints. On 2026-09-30 this machine downloaded the
pinned CA-discharge GeoPackage (MD5 `e0ba6664aaec3e0b27138abdfd4ba263`),
extracted 75 ERA5-Land water-year grids for 1951–2025, and reran all 52
gauges. `PIPELINES/verify_snow_forecast_region.py` independently refitted all
208 issue records and passed. Against the previous tracked regional JSON,
every operational score and sample period is unchanged; the maximum absolute
score difference is `1.33e-15`. The build also regenerated 558,375 annual
rows for 7,445 basins and 7,445 per-basin JSON files. The extracted grids,
basin Parquet and per-basin JSON files remain gitignored.

## Scope

This review compares the 2026-09-29 saved regional study with a full local
re-extraction and rebuild on 2026-09-30. It checks the source GeoPackage hash,
all 52 recalculated gauge scores, all 208 independently refitted operational
hindcasts and the generated basin file count. After publication it also checks
the live regional JSON, manifest and Parquet against the release bytes. The
large regional grids, basin predictor Parquet and per-basin JSON
files are intentionally gitignored and available locally for the rebuild.

## Result and verification boundary

The saved operational hindcasts report positive 1 April skill against the previous
30-year mean at 49 of 52 gauges; median skill is 0.389. Of 42 gauges with a
recent-period score, 37 are positive; median recent skill is 0.340. The other
ten gauges lack enough 1996-onward hindcast years to report a recent score.
The rebuilt `region/gauges.json` (4.3 MB) now contains full-precision annual
SWE and flow inputs in each issue record, plus scores and chart-oriented
hindcasts. The independent verifier refitted 208 operational hindcasts from
those rows. All 376 available all/recent score objects agree to a strict
numeric tolerance, and every operational score matches the previous tracked
regional study to within `1.33e-15`. A reader can now refit the fixed
operational model from the public JSON. Reproducing the spatial SWE extraction
still requires the source grids, catchment geometry and grid-weighting code.

## Public verification package

| Tier | Artifact | Purpose | Size / treatment |
| --- | --- | --- | --- |
| Regenerated locally | `operational_inputs` in `region/gauges.json`: water year, April–September mean discharge (m³/s), basin-mean SWE (mm), by gauge and issue date | Refit the fixed one-predictor operational hindcast and reproduce the 52-gauge headline | Full precision; 208 issue records. |
| Useful | `regional-operational-hindcasts.csv`: gauge, issue month, year, observed, raw forecast, corrected forecast, prior-30-year mean, all in m³/s | Recompute skill, RMSE, bias and periods without parsing nested JSON | A later convenience export; the current JSON has two-decimal hindcasts. |
| Published | `verification-manifest.json` and `verify-snow-forecast-region.py` | Pin source, grid, method and output hashes; independently refit all/recent operational scores | Both live in the regional download directory; the verifier passed for all 208 issue records. |
| Useful | Per-gauge quality table: source resolution, complete seasons, first/last year, number of ERA5 cells, glacier-cell share, regulation status, outlet area ratio, all/recent sample counts and error metrics | Explain where a score is reliable and why one is missing | Publish as CSV and use it to drive page labels. |
| Optional bulk | `basin-predictors.parquet` and 7,445 per-basin JSON files | Explore basin snow; they are not required to verify the gauged hindcast | Generated locally and gitignored. The regional Parquet was published to R2; the per-basin JSON files were outside this publication prefix. |
| Source archive | ERA5 regional rasters, CA-discharge GeoPackage, basin polygons | Reproduce extraction and spatial weighting from source | Keep separate; link to authoritative source releases and document exact versions and checksums. Do not require these for a score audit. |

The model-ready inputs are the critical addition. The builder now regenerates
them from `gauge_predictors(...).join(veg)` for every scored gauge, including
cached results; `--inputs-only` avoids rebuilding the basin files. The separate
verifier independently refits the expanding-window regression, ten-year
residual correction and prior-30-year baseline and checks all/recent scores.
It has been checked against the published Pskem single-gauge input CSV and the
completed 52-gauge regional rerun.

## Release and reporting corrections

- `PUBLISHED/release-includes.txt` already declares the gitignored basin files
  and Parquet for the R2 release. A checkout without them logs and skips those
  paths. Their previous absence locally was not evidence of a live-site defect.
- The new `gauges.json` declares itself public research and contains the
  refitting inputs. The approved R2 publication uploaded it, and a live
  download matched the built release SHA-256 exactly. The live verifier passed
  for 52 gauges and 208 issue records. The downloadable verifier and manifest
  were also published and byte-checked against the built release.
- The regional page uses fixed labels such as `1996–2017`, although gauge
  records end in different years, some as late as 2020. Show each gauge's actual
  scoring years and sample count. Report `37/42 with a recent score` and `10
  unavailable`, instead of presenting 37/52 as a comparable recent success rate.
- A score at the nearest downstream gauge is evidence for that gauged catchment,
  not validation of the individual basin. The platform associates 1,208 of
  7,445 basins with a scored gauge, including 929 linked to April skill above
  0.3. The basin view should state this distinction beside the score.
- Show corrected-forecast RMSE and bias alongside skill and the baseline RMSE;
  those values are already in the saved regional JSON. Label ERA5-Land SWE as
  gridded reanalysis and discharge as source observations/reconstructed inflow
  where applicable.

## Source terms and attribution

The project records CA-discharge as CC BY 4.0 in its local source manifest, but
the public Zenodo landing page does not display a machine-readable licence in
the text inspected here. Confirm the exact rights on the downloaded release
before redistributing input discharge values. ERA5-Land's CDS page lists a
CC-BY licence; the USGS Qashqadaryo SnowModel release is marked CC0. The
verification manifest should cite each source and preserve their terms. The
project's `DATA-LICENSING.md` grants no blanket licence over the combined data.

## Acceptance checks

1. Done: the launch build carries the regenerated `gauges.json` and manifest.
2. Done: the regional files were published to R2, and live JSON, manifest and
   Parquet bytes match the built release. The live JSON passed the independent
   verifier.
3. The study page source now links the public input JSON, verifier and manifest;
   that frontend edit awaits the next site deployment. Further reporting work
   should show each gauge's available period, missing recent scores, baseline
   RMSE and observational/modelled provenance.
