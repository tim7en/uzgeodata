# Regional station–satellite environment study

Implemented 2026-09-09. Open `/case-studies.html#regional-study`.
Historical window: 2015–2020. This is not operational forecasting or complete
transboundary station coverage.

## Questions

1. How do elevation and location relate to gridded temperature and vegetation?
2. Do soil/air-temperature relationships with satellite surface temperature
   persist after removing the calendar-month seasonal cycle?
3. How does vegetation vary across mapped soil-texture groups, without treating
   categorical class numbers as continuous physical measurements?

## Source audit

- 86 meteorological sites have unique IDs. Nine zero/ambiguous source-key sites
  receive deterministic local IDs; different stations no longer overwrite
  `meteo-0`. Local identity is not an assertion of ontology membership.
- 113 gauge/canal/outlet sites comprise 90 river gauges, 21 canals and two
  outlets. These deliveries contain metadata, not new discharge observations.
  Geographic coordinates are plausible, but the Excel source does not declare
  its CRS or vertical datum. Meteo shapefile coordinates were transformed from
  declared EPSG:4284 to WGS84. Plausibility is not survey verification.
- All 120,233 monthly source rows retain workbook, sheet, cell, unit, QC and
  date status. There are 252 identical duplicate extras; JSON represents them
  once. Conflicting duplicates would be quarantined.
- 2,593 values are quarantined, including two sheets with suspect variable
  labels. Negative precipitation does not justify automatically swapping whole
  temperature and precipitation blocks. Raw values remain in CSV.
- Exact normalized names match 93,260 rows to 74 network identities. The other
  26,973 rows across 25 station blocks require a reviewed crosswalk; fuzzy
  similarity alone is not accepted.
- October–September uses an **ending year**. The calendar audit compares ±1-year
  alignments against separately imported Tashkent/Pskem records and publishes
  n and MAE. Checked status requires both seasonal halves and both variables
  to pass; elsewhere the convention remains inferred. Only checked sites enter
  date-matched air/precipitation comparisons.
- Seven gauge height sentinels were removed, not imputed. Glacier catalogues
  publish 210 centres from 2023: 60 Kashkadarya and 150 Surkhandarya, after one
  exact duplicate was excluded. Centres and reported areas are not outlines.

## Products and methodology

| Product | Role and screening |
| --- | --- |
| [SRTM](https://developers.google.com/earth-engine/datasets/catalog/USGS_SRTMGL1_003) | Terrain elevation/slope, not surveyed station height. |
| [MOD13Q1 v6.1](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13Q1) | NDVI ×0.0001; SummaryQA=0. |
| [MOD11A2 v6.1](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD11A2) | Daytime LST ×0.02 K, converted to °C; mandatory QA=0 and error class ≤2 K. Not 2-m air temperature. |
| [MOD10A1 v6.1](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD10A1) | Fraction of QA-valid days with NDSI ≥40; not SWE, snow depth or water storage. |
| [ERA5-Land](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_MONTHLY_AGGR) | Reanalysis temperature and precipitation; not independent satellite observations. |
| [OpenLandMap v02](https://developers.google.com/earth-engine/datasets/catalog/OpenLandMap_SOL_SOL_TEXTURE-CLASS_USDA-TT_M_v02) | Modelled USDA texture at 0 cm. Hengl (2018), [DOI](https://doi.org/10.5281/zenodo.1475451), CC-BY-SA-4.0. Not a field soil survey. |
| [MCD12Q1 v6.1](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MCD12Q1) | IGBP endpoint classes for 2015/2020; differences are not verified land-cover change. |

Extraction uses native-grid cells containing station coordinates, not basin
means or instrument-equivalent samples. Monthly satellite means group composites
by start date, not exact day-weighted calendar means. At least half the source
images must pass QA; LST additionally needs two composites and snow ten clear
daily observations. Counts, raw extracts and screening decisions are downloadable.
Clear-sky sampling bias remains.

All-season site summaries require three eligible years in every calendar month,
then weight the twelve month means equally. Available years may differ by site.
Anomalies subtract each site's calendar-month mean over this six-year window,
not a 30-year climate normal. No interpolation is used.

Descriptive OLS reports n, slope, r and R². Slope intervals use 500 deterministic
bootstrap draws of whole years for temporal pairs or one-degree geographic
blocks for site comparisons, requiring five blocks. Dependence beyond these
blocks, retrieval error and confounding remain unquantified. These are not
multiple-testing-adjusted significance claims. Soil groups report median,
quartiles and n; class numbers are never regressed numerically.

## Results of this build

- 6,192 station-month rows. All-season eligibility: 86 ERA5 temperature sites,
  ten LST sites, 35 NDVI sites and zero snow sites. No annual snow–elevation
  regression is reported; eligible monthly snow values remain available.
- Elevation–ERA5 temperature r ≈ −0.828, n=86, slope ≈ −5.67 °C/km.
  Linear adjustment for latitude/longitude gives ≈ −7.08 °C/km. Neither is a
  measured atmospheric lapse rate or independent predictive validation.
- Pskem soil–LST r is ≈0.899 for 37 raw pairs and ≈0.591 for 36 anomaly pairs.
  Air–LST r is ≈0.951 for 36 raw pairs and ≈0.497 for 35 anomaly pairs. The raw
  relationship partly reflects seasonality; slightly different eligible samples
  mean this comparison is descriptive, not a formal significance test.
- Soil/NDVI groups contain 24 loam, six sandy-loam, four clay-loam and one
  loamy-sand sites. Sparse groups and irrigation/location confounding prevent
  attributing vegetation differences to soil alone.

The JSON is authoritative after reruns; this document records this build.

## Reproduction and next gates

Run `stations:network`, `stations:climate`, `stations:glaciers-regional`, then
`cases:regional`. Use `npm run cases:regional -- --offline` to rebuild from
cached extracts without credentials; `--refresh` explicitly refetches.
Do not run concurrent publishers. If Windows reports a persistent reader lock,
stop the development server, rebuild and restart it; do not truncate live data.

Downloads: `PUBLISHED/data/case-studies/regional-station-*`; original-value/QC
tables: `PUBLISHED/data/hydroclimate/`. Manifests retain hashes, asset IDs,
retrieval times and source-image catalogues.

Next: confirm aliases/WMO links and dated station relocations; resolve suspect
sheets and remaining year conventions; obtain soil-sensor depth and independent
soil/land-cover observations; assess common-period and spatial-block sensitivity;
extend genuinely prospective hydrological validation to independently gauged
Chatkal, Ugam and other tributaries before generalizing Pskem results.
