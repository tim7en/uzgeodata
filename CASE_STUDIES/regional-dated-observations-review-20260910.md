# Review: dated basin observations at regional scale

Reviewed 10 September 2026, approximately 14:03–14:15 UTC. This is a read-only
review of the active extraction and the supplied mid-run narrative. No extraction
code or observation partitions were changed by this review.

## Verdict

The programme is taking the right engineering direction: pilot definitions,
regional benchmarking, server-side basin reductions, dated records, checkpointing,
explicit missing values and separation from the original HydroATLAS reference.
Actual regional tabular data have been acquired. However, the store is still a
research staging system. Independent reproduction is not the only outstanding
gate: checkpoint identity, source/geometry provenance, temporal semantics and
snow observation coverage need work before repeated operational refreshes or
published trend/anomaly claims.

## What was verified

* `regional-snow-ledger.json`: 1,786,800 rows, 7,445 basins, 2003–2022,
  8,097.15 seconds (2.25 hours), complete, no failures.
* `regional-terraclimate-ledger.json`: 7,147,200 rows, four variables over the
  same domain/period, 7,181.15 seconds (1.99 hours), complete, no failures.
* These total 8,934,000 regional dated records. Pilot rows and other modes are
  additional records, not additional independent regional observations.
* A Python process was actively executing `extract_regional_monthly.py
  era5_runoff --years 2003-2022`; its completion ledger was not yet present.
  ERA5 is therefore running, not verified complete. Its expected row count is
  1,786,800, not a completed-download count.
* The completed 2022 partition contains 89,340 rows for each TerraClimate
  indicator and 89,580 snow rows (89,340 regional plus 240 pilot). There were
  no duplicate basin/geometry/indicator/year/month keys or nonfinite values
  in this checked partition. This is a sample, not a full-store content audit.
* 29 existing tests passed in the dated-monthly, zonal-kernel and regional
  batching suites. The full suite was not rerun against the actively changing
  store. Additional in-memory probes exposed gaps those tests do not cover.

The scripts call Earth Engine `reduceRegions(...).getInfo()`, then retain JSON
checkpoints and CSV observations. We are downloading computed basin summaries.
We are not archiving all native source imagery. This is an efficient acquisition
strategy, but it requires a stronger source snapshot manifest for reproducibility.

## Findings requiring action

### 1. Checkpoints are not identified by the scientific recipe or geometry — high priority

`PIPELINES/extract_regional_monthly.py` stores caches under source/batch/year;
`PIPELINES/extract_regional_snow.py` uses batch/year. An existing file is reused
without verifying source snapshot, geometry bytes, grid, band list, mask,
conversion factors, recipe version or batch membership. Changing batch size,
geometry or code can therefore reuse the wrong data, potentially assigning
previously computed values to a newly generated recipe/run identity.

Key caches by a job fingerprint covering those inputs. Store the fingerprint,
exact expected basin IDs, source items, original acquisition timestamp and an
output checksum in every checkpoint. Reject a mismatch and create a new cache
namespace. Preserve reuse provenance instead of describing a reused checkpoint
as a fresh Earth Engine retrieval.

No mismatched cache was demonstrated in the completed runs; this is a concrete
correctness risk in the implemented resume/update path.

### 2. Provenance identifiers do not yet pin all the evidence — high priority

The regional geometry version hashes the layer name and basin IDs, not polygon
coordinates or CRS. An in-memory probe confirmed that different geometries with
the same IDs receive the same geometry version. The regional geometry side-table
row has an empty SHA-256.

Dated source releases are explicitly `pinned=False`, with no content hashes.
Collection names and monthly image counts do not uniquely fingerprint content.
`recipe.csv` currently contains only recipe version and mode; it does not itself
contain the promised resolution, units mapping, mask description, code dependency
manifest or environment. `merge_table` replaces a side-table row under its key,
so reused release IDs can also change descriptive provenance in place.

Hash a canonical geometry snapshot including CRS. Retain exact source image IDs,
dates and release metadata, a complete executed-code/environment manifest,
parameters and hashes of the returned tables. Link to immutable source subsets
where obtainable; distinguish reproducible saved-result analysis from a future
independent re-extraction when the provider can revise source pixels. Hashing a
result table alone does not pin its source imagery.

### 3. Monthly totals are labelled as monthly means — high priority

`extract_regional_monthly.observation_rows` sets `temporal_statistic=monthly_mean`
for every band. That label is misleading for monthly accumulated precipitation,
evapotranspiration and `runoff_sum`. The mean being computed by the basin reducer
is spatial; it should not redefine a monthly accumulated depth as a temporal mean.
The 2022 store sample confirms the label is present in saved precipitation rows.

Separate spatial statistic from temporal statistic. Describe flux-depth fields
as monthly totals, and give soil moisture its source-defined state/statistic.
Version the correction and preserve earlier records. Annual water-budget and
ontology code must know whether to sum months or average states.

Sources: [TerraClimate bands](https://developers.google.com/earth-engine/datasets/catalog/IDAHO_EPSCOR_TERRACLIMATE),
[ERA5-Land monthly aggregation](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_MONTHLY_AGGR).

### 4. Snow QA currently records spatial cells, not temporal support — high priority for research

`dated_snow.monthly_stack` averages valid daily threshold flags before spatial
reduction. `valid_count` then counts valid cells in the monthly raster. It does
not retain how many valid days supported each cell, the spatial distribution of
those days, or snow-day/valid-day sufficient statistics. A cell observed once can
contribute to the monthly mean like a cell observed throughout the month.

Retain temporal coverage alongside spatial coverage; define minimum valid-day
and valid-area thresholds and test sensitivity to them. Inspect the provider QA
and class bands to distinguish cloud, missing data, night, water and other
exclusions. Do not identify every masked month specifically as cloud without
evidence. Constant global image counts cannot diagnose local valid coverage.

The catalogue already masks provider values above 100 in `NDSI_Snow_Cover` and
provides separate quality/class bands. The current additional `<=100` test does
not constitute a full quality assessment.

Source: [MODIS MYD10A1 bands and QA](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MYD10A1).

### 5. The executable contract is weaker than its description — high priority before new ingestion

Read-only, in-memory probes confirmed the current store accepts:

* a NaN value with no missing reason;
* year/month values inconsistent with `valid_start`/`valid_end`;
* a missing temporal statistic;
* a change from monthly mean to monthly sum across months under the same
  recipe/geometry version, with no series conflict.

The completeness check also accepts twelve copies of January for one basin as a
complete year: it checks counts, not the exact expected basin × band × month keys.
This is not evidence that the sampled stored year contains such duplicates;
the sample did not. It shows the declared guarantees need stronger validation.

Require finite values or explicit null reasons; validate dates against year/month
and statistic; include temporal statistic in series checks; verify exact unique
expected keys. Enforce source/recipe/geometry/run references and validate records
at the write boundary. Add regression tests for these counterexamples.

### 6. Processing cells are not independent source observations — scientific interpretation

The 15 arc-second grid is a processing choice. TerraClimate is about 4.6 km,
ERA5-Land about 11.1 km in the Earth Engine catalogue, and MODIS snow about 500 m.
Hundreds of upsampled climate grid cells do not supply hundreds of independent
observations. Record native support and, where feasible, effective native-pixel
counts or area fractions in addition to analysis-grid counts.

The report's statement that a one-cell and a 900-cell basin are categorically
incomparable is too strong. Their basin summaries may be compared with explicit
support/uncertainty treatment; they simply do not carry equal information.
Zero nulls in a modelled product do not establish accuracy or eliminate changing
forcing/model errors. TerraClimate's provider specifically cautions against
using it directly for independent trend assessments.

Sources: [TerraClimate limitations](https://developers.google.com/earth-engine/datasets/catalog/IDAHO_EPSCOR_TERRACLIMATE),
[ERA5-Land resolution](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_MONTHLY_AGGR).

## Corrections to the supplied narrative

* The 14.3-hour old-kernel figure is still a projection: the benchmark measured
  40 basins and extrapolated to 7,445 and 250 passes. The 2.1-minute grouped
  figure scales one full-grid synthetic pass to 250 passes. The 405× ratio is
  an estimated comparative speedup based on those measurements, not a timed
  full scientific run with both kernels. The actual 2.25/1.99-hour source runs
  are the stronger end-to-end evidence.
* The precise TerraClimate/ERA5 climatology comparison quoted in the pasted
  text was not located as an executable pipeline or saved comparison report
  in the reviewed tracked files. `dated_monthly.py` references a
  `verify_against_climatology` routine that was not found by repository search.
  Preserve that check as a runnable test and report. Its claimed agreement
  would demonstrate implementation consistency, not independent accuracy.
* A 5–10× storage saving for Parquet or PostGIS is not established by a benchmark
  here. Compressed columnar storage is worth testing; PostGIS storage depends
  on schema, indexes and overhead. Measure a representative partition.
* The published store manifest was still the older 1.8-million-row snapshot
  during review, while newer partitions existed. This matches the declared
  mid-run state, but readers must not treat it as a current complete edition.
  Publish a consistent versioned snapshot after extraction and validation.

## Recommended sequence

1. Let the currently running ERA5 job finish into staging; retain its checkpoints
   and distinguish it from the last reviewed published snapshot.
2. Fix checkpoint identity, provenance and temporal/contract checks before
   changing methods, running refreshes or adding more full-region source jobs.
3. Add snow temporal QA and independently validate a stratified basin sample
   spanning both systems, basin sizes and elevation zones.
4. Freeze a source/geometry/code/result snapshot and have a second operator
   reproduce the extraction and analysis. Keep implementation agreement and
   scientific validity as distinct review questions.
5. Benchmark production storage and then add missing climate variables and the
   first environmental-atlas thematic module. Publish anomalies only from
   comparable, adequately sampled series with a pinned baseline and thresholds.

Regional acquisition in hours is now supported for these particular source jobs.
It does not imply that all 281 HydroATLAS attributes, the environmental atlas,
or a higher-resolution historical backfill will take the same time.
