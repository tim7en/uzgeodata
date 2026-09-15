# Water-flow case study: scientific and numerical review

Reviewed 15 September 2026. The revised page is a **source-audited descriptive
accounting study**, not an independently validated regional discharge model.

## Findings and corrections

| Previous behaviour | Why it failed | Revised representation |
| --- | --- | --- |
| A connected diagram routed modelled precipitation minus AET into national withdrawals | Different spatial boundaries and periods; withdrawals are not net depletion | Model diagnostics and reported management accounts have separate charts |
| Country withdrawal nodes looked like river inflow/outflow accounts | Border flows, transfers, storage and returns were absent | Country bars show reported withdrawal and separate allocation limits; unknown border flows remain null |
| Delta delivery was subtracted from Uzbekistan's Amu withdrawal | The source did not define that subtraction | Delta deliveries are independent reporting records |
| Large Aral drainage was drawn through the Amu delta | The cited collecting drain bypasses the delta | Route is explicitly South Karakalpak drain; no invented delta-to-sea link |
| Syr aggregate was coloured as Uzbekistan, while the accounting boundary was simplified to exclude Kazakhstan | An aggregate cannot establish a country allocation; downstream exclusion does not exclude every upstream Kazakhstan abstraction | Explicit upstream-of-Shardara boundary; no country split inferred |
| Figures were labelled hydrological-year actuals | The yearbooks explicitly report their analysis for calendar years | January–December dates recorded per figure |
| 2022 withdrawals were repeated against 22 years of modelled P − AET | Resulting historical shortages were neither observed shortages nor an accepted water-stress index | Historical shortage counts and the arbitrary threshold are removed |
| Uzbekistan's efficiency target and national agricultural share were applied across basin-country withdrawals | Wrong jurisdiction and denominator; recoverable returns were ignored | Dimensionless illustrative efficiency arithmetic, with hypothetical recoverability and no national volume forecast |
| Gridded estimates and plant inventory totals were labelled measured | Computation does not establish field observation or common geography/year | Reported statistics, model estimates and calculated diagnostics are distinguished |
| SQL accepted 12 rows even if values were null, and summed changing basin footprints | Missing data could appear as lower annual volume | Exactly 12 distinct finite values per basin/year and the complete domain are required |

## Source audit and scope

The [2022](https://www.cawater-info.net/yearbook/2022/02_yearbook2022_en.htm),
[2023](https://www.cawater-info.net/yearbook/2023/02_yearbook2023_en.htm) and
[2024](https://www.cawater-info.net/yearbook/2024/02_yearbook2024_en.htm) SIC ICWC
Water Yearbooks supply the reported numerical series. Section 2.1 covers
allocation, withdrawal, reservoirs and Northern Aral delivery; section 2.2.1
supplies the more precise mixed delta delivery and Large Aral collector series.
All 54 transcribed rows retain source URL, source ID, section, dates, unit,
reporting entity and uncertainty note. These checks verify transcription and
arithmetic against public reports, not the independent accuracy of the reporting
bodies' measurements. The 2023 summed country limits differ from the reported
total by 0.01 km³ because of reported precision; no hidden adjustment is made.

Afghanistan belongs to the Amu Darya riparian context. Its omission from this
particular allocation table must not imply no abstraction. There is no assembled
national inflow/outflow dataset here for any of the six riparian countries.
The obsolete `national-targets.csv` remains a historical source transcription;
it is not an input to the revised study and its legal status has not been reverified.

## TerraClimate and discharge

Precipitation and AET already came from TerraClimate. The comparison now also
uses its separately identified runoff product when present in the public cube.
ERA5-Land runoff remains an alternative diagnostic. Both are aggregated over the
same basin areas and common complete 2003–2024 years; neither is routed discharge.
Their numerical closeness to a water-balance diagnostic cannot select a winner.

The [TerraClimate paper](https://doi.org/10.1038/sdata2017191),
[provider limitations](https://www.climatologylab.org/terraclimate.html),
[Earth Engine catalogue](https://developers.google.com/earth-engine/datasets/catalog/IDAHO_EPSCOR_TERRACLIMATE)
and [ERA5-Land documentation](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land-monthly-means?tab=overview)
provide the product distinctions. A [multi-product hydrological evaluation](https://doi.org/10.5194/hess-28-3099-2024)
supports catchment-specific testing. The [Naryn snow/glacier study](https://doi.org/10.5194/hess-27-453-2023)
provides a regional modelling example. The page defines a gauge-based benchmark
with matched geometry, chronological validation, common model structure, seasonal
metrics, volume bias, uncertainty and regulated-flow accounting. That benchmark
has **not** been run as part of this accounting review.

The [FAO real-water-savings guidance](https://www.fao.org/family-farming/detail/en/c/1447785/)
supports distinguishing gross withdrawal reduction from net savings. The retained
0.63 → 0.73 arithmetic is an illustration with no jurisdiction, real-volume unit or
claim of a current legal target. Return-flow recoverability cases are hypothetical,
not measured bounds or probabilities.

## Data and chart contract

- `regional-withdrawals.csv`: reviewed reported figures and row-level citations.
- `regional-water-flow.json`: country, reservoir and environmental accounts; schema v2.
- `regional-water-flow-sensitivity.json`: model diagnostics, coverage, assumptions
  and exact input hashes; schema v2 intentionally removes the old `observed` stress
  and policy-scenario fields. Consumers must migrate rather than reuse old semantics.
- `regional-model-annual.csv`: one row per product/year, complete basin count, area
  coverage and a nullable full-domain volume.
- SVG figures are generated with Matplotlib. Withdrawal bars have zero-based,
  identical axes and allocation limits as separate ticks. Source-specific
  environmental deliveries are not stacked or linked. Every numerical chart uses
  the JSON/CSV products; page tables expose the underlying values.
- The map uses tracked basin polygons, river lines and dam coordinates, simplified
  only for display. Input hashes and plotted landmarks are in its JSON sidecar.
  Basin area calculations use unsimplified published area attributes.
- The water-flow directory card shows the same map and three actual reporting
  years, replacing the former unsupported shortage headline.

The cube is a projection and does not retain within-basin pixel coverage or all
revision evidence. File hashes record the inputs used; they do not preserve their
bytes after future mutation. Full evidence retention and independent scientific
review remain necessary.

## Rebuild and validation

With the repository's pipeline environment (including DuckDB, Matplotlib and
Shapely):

```sh
npm run cases:water-flow
python -m pytest TESTS/test_water_flow.py -q
npm run build:launch
```

The build does not acquire imagery or retrain a model. It updates this study and
its directory card, leaving the other studies' evidence unchanged. The source
CSV is reviewed input, not scraped automatically from changing web pages.

Regression tests cover units/area conversion, nulls, duplicate and missing months,
missing basins, invalid values, country reconciliation, non-inferred border flows,
source boundaries, return-flow arithmetic, snapshot hashes and map integration.
Visual review covers chart labels, map landmarks and page rendering at desktop and
mobile widths. These are computational/presentation checks, not peer review.
