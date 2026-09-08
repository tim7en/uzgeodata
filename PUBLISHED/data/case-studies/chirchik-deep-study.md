# Pskem–Charvak: historical validation and seasonal water evidence

This study replaces the initial data-readiness assessment with Earth Engine extractions and reproducible tests against the held station records. It distinguishes station validation, agreement between satellite products, a retrospective seasonal-flow experiment, and reservoir extent monitoring. None of these by itself identifies glacier melt fractions or absolute reservoir storage.

## Study domain and data

The Pskem candidate contains 20 level-12 units, approximately 2,627 km². It includes the full unit containing the Mullala gauge and is provisional pending reach/partial-unit review. Pskem and Oygaing are the mountain station checks; Tashkent is the lowland comparison. Ground records cover precipitation and temperature (Pskem 2010–2024, Oygaing 2020–2022, Tashkent 2010–2019), Pskem discharge (2001–2017), and observed snow-day counts (Pskem 2020–2024; Oygaing 2020–2022).

| Product | Extracted support | Role |
| --- | --- | --- |
| ERA5-Land monthly | Native station cells for observed months; area-weighted Pskem basin 2000–2024 | Temperature/precipitation validation; antecedent precipitation, March temperature and SWE |
| CHIRPS v3 pentads | Six pentads per observed station month | Precipitation comparison |
| CHIRTS daily | Daily Tmin/Tmax midrange aggregated monthly, 2010–2016 overlap | Temperature proxy cross-check |
| MODIS Terra/Aqua v6.1 | Daily Terra/Aqua basin snow 2000–2024; combined series extended to latest extraction; station cells 2020–2024 | Snow-day checks, sensor agreement and pre-April predictors |
| SRTM | Elevation bands below 1500, 1500–2500, 2500–3500 and above 3500 m | Snow stratification |
| JRC Global Surface Water v1.4 | Monthly water detections, 2000–2021, Charvak polygon plus 1 km | Reservoir extent evidence, with missing-data screening |

ERA5 accumulated precipitation is converted from m to mm; 2 m temperature from K to °C. CHIRPS pentads are summed, not averaged. CHIRTS is monthly mean daily (Tmin+Tmax)/2 and is explicitly a proxy: the station mean may use another observing convention. Native station sampling uses the source projection and affine transform. [ERA5-Land documentation](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_MONTHLY_AGGR), [CHIRPS v3](https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHC_CHIRPS_V3_PENTAD), [CHIRTS](https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRTS_DAILY).

Station assimilation/contribution to these gridded products has not been audited. These are observation comparisons, not proof of fully independent product validation. Station elevations and relocations are not established by the supplied ontology, so no fixed lapse rate is assumed.

## 1. Raw forcing validation

Bias is product minus observation. Temperature errors are °C; precipitation errors are mm/month. Each row uses its own explicitly stated overlap.

| Station | Product | Variable | Period | N | RMSE | Bias | r |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| Tashkent | chirps-v3 | precipitation_total | 2010-01–2019-12 | 120 | 13.29 | 2.30 | 0.937 |
| Tashkent | chirts-midrange | air_temperature_mean | 2010-01–2016-12 | 84 | 1.74 | -1.53 | 0.997 |
| Tashkent | era5-land | air_temperature_mean | 2010-01–2019-12 | 120 | 2.27 | -1.42 | 0.986 |
| Tashkent | era5-land | precipitation_total | 2010-01–2019-12 | 120 | 16.63 | 6.72 | 0.913 |
| Pskem | chirps-v3 | precipitation_total | 2010-01–2024-12 | 180 | 24.80 | -1.31 | 0.915 |
| Pskem | chirts-midrange | air_temperature_mean | 2010-01–2016-12 | 81 | 1.32 | 1.18 | 0.998 |
| Pskem | era5-land | air_temperature_mean | 2010-01–2024-12 | 177 | 7.23 | -7.13 | 0.994 |
| Pskem | era5-land | precipitation_total | 2010-01–2024-12 | 180 | 41.59 | 34.09 | 0.929 |
| Oygaing | chirps-v3 | precipitation_total | 2020-01–2022-12 | 36 | 25.71 | -8.83 | 0.909 |
| Oygaing | era5-land | air_temperature_mean | 2020-01–2022-12 | 36 | 3.78 | -3.65 | 0.996 |
| Oygaing | era5-land | precipitation_total | 2020-01–2022-12 | 36 | 72.82 | 51.04 | 0.680 |

### Fair comparison on identical months

The following scores restrict each station/variable to the intersection of months available from every compared product. This prevents a short CHIRTS window from being ranked directly against a longer ERA5 period. CHIRTS remains a midrange proxy.

| Station | Variable | Product | Common window | N | RMSE |
| --- | --- | --- | --- | ---: | ---: |
| Tashkent | precipitation_total | chirps-v3 | 2010-01–2019-12 | 120 | 13.29 |
| Tashkent | air_temperature_mean | chirts-midrange | 2010-01–2016-12 | 84 | 1.74 |
| Tashkent | air_temperature_mean | era5-land | 2010-01–2016-12 | 84 | 1.64 |
| Tashkent | precipitation_total | era5-land | 2010-01–2019-12 | 120 | 16.63 |
| Pskem | precipitation_total | chirps-v3 | 2010-01–2024-12 | 180 | 24.80 |
| Pskem | air_temperature_mean | chirts-midrange | 2010-01–2016-12 | 81 | 1.32 |
| Pskem | air_temperature_mean | era5-land | 2010-01–2016-12 | 81 | 7.27 |
| Pskem | precipitation_total | era5-land | 2010-01–2024-12 | 180 | 41.59 |
| Oygaing | precipitation_total | chirps-v3 | 2020-01–2022-12 | 36 | 25.71 |
| Oygaing | air_temperature_mean | era5-land | 2020-01–2022-12 | 36 | 3.78 |
| Oygaing | precipitation_total | era5-land | 2020-01–2022-12 | 36 | 72.82 |

## 2. Corrections tested on later years

For Pskem, fit through 2017 and test 2018–2024. For Tashkent, fit through 2016 and test 2017–2019. Each calendar month needs at least four training observations. Temperature uses an additive monthly offset; precipitation uses the ratio of observed to product training means. No coefficient or correction form is selected against the test scores. Oygaing is too short for this split and receives raw checks only; CHIRTS has no later test overlap.

| Station | Product | Variable | Test period | N | Raw RMSE | Corrected RMSE | Corrected bias | Test anomaly r |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| Tashkent | chirps-v3 | precipitation_total | 2017-01–2019-12 | 36 | 13.23 | 13.57 | 3.00 | 0.877 |
| Tashkent | era5-land | air_temperature_mean | 2017-01–2019-12 | 36 | 3.30 | 2.61 | -0.47 | 0.465 |
| Tashkent | era5-land | precipitation_total | 2017-01–2019-12 | 36 | 20.13 | 13.32 | 4.34 | 0.859 |
| Pskem | chirps-v3 | precipitation_total | 2018-01–2024-12 | 84 | 24.29 | 22.99 | -3.05 | 0.880 |
| Pskem | era5-land | air_temperature_mean | 2018-01–2024-12 | 84 | 7.16 | 0.77 | 0.15 | 0.881 |
| Pskem | era5-land | precipitation_total | 2018-01–2024-12 | 84 | 42.98 | 19.05 | 5.55 | 0.916 |

Anomalies subtract each calendar month’s training mean separately from observed and product values. This removes the recurring seasonal cycle without using test observations to establish a baseline. Calendar-year bootstrap intervals are in advanced-validation.json; they condition on fitted corrections and do not capture instrument or structural uncertainty. Temperature percent bias and temperature KGE are not reported because Celsius ratios depend on an arbitrary zero.

A strong raw correlation can coexist with a large mean error. Use held-out RMSE, seasonal biases and anomaly correlation together when choosing forcing. Station-cell corrections do not automatically transfer to area-mean mountain forcing. Product ranking can differ by station and season.

## 3. MODIS snow: quality first

Terra and Aqua are analysed separately and as a same-day combination: valid Terra pixels take priority, with valid Aqua observations filling Terra gaps. No adjacent dates are used. Valid pixels have NDSI in 0–100, best/good basic QA, and neither inland-water nor high-solar-zenith flag. The main snow mask is positive provider-screened NDSI; NDSI ≥40 is a conservative sensitivity test. Snow area is summed and divided by valid observed area. NDSI is never interpreted as fractional cover. Daily valid area must be at least 70%; monthly means require at least ten qualifying days. No cloud filling is used. [MODIS Terra band and QA definitions](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD10A1), [MODIS Aqua](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MYD10A1).

### Cross-sensor verification

These are matched-date comparisons with ≥70% coverage in both products. Terra is the reference for the sign of differences, not ground truth. Their clear pixels and overpass times can differ, so these are aggregate agreement scores, not pixel-level classification accuracy.

| Elevation band | Paired days | RMSE (percentage points) | Aqua − Terra bias | r |
| --- | ---: | ---: | ---: | ---: |
| 1500to2500 | 3110 | 5.28 | 0.39 | 0.992 |
| 2500to3500 | 2912 | 6.37 | 0.76 | 0.990 |
| above3500 | 2607 | 8.42 | 2.42 | 0.966 |
| all | 2972 | 5.27 | 0.19 | 0.991 |
| below1500 | 3190 | 2.70 | 0.01 | 0.996 |

### Independent station snow-day consistency

The ground record provides monthly snow-day counts, not daily snow/no-snow labels. For each station-month, the satellite lower bound is the number of valid snowy days; the upper bound adds all unobserved days. The station count is checked against those bounds. A wide cloudy-month interval is weak evidence, so compatibility is reported only for months with ≥70% daily observations. Even then, a 500 m mixed pixel can differ from the station snow patch. No daily confusion matrix, snow-depth validation or SWE validation is inferred.

| Station | Sensor | Paired months | Months ≥70% observed | Mean daily coverage (%) | Mean unknown days | Compatible (%) in ≥70% months |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Oygaing | aqua | 36 | 6 | 53.09 | 14.28 | 83.33 |
| Oygaing | combined | 36 | 16 | 66.30 | 10.25 | 75.00 |
| Oygaing | terra | 36 | 13 | 57.58 | 12.89 | 84.62 |
| Pskem | aqua | 60 | 9 | 46.27 | 16.33 | 77.78 |
| Pskem | combined | 60 | 22 | 59.52 | 12.30 | 81.82 |
| Pskem | terra | 60 | 11 | 48.53 | 15.65 | 100.00 |

## 4. Does pre-April snow information improve summer-flow estimates?

Retrospective April 1 issue date. October–March precipitation and March temperature/SWE and March combined snow only. Fixed ridge alpha=1; same complete years for every model; no held-out tuning.

The target is observed April–September discharge volume in million m³. Every day must be present after screening; 2017 is excluded because flagged daily observations leave incomplete seasonal volume. Three source flags and the impossible 2015-02-29 date are retained in the separate audit. All candidate models use identical eligible training and test years. Predictors and response are centred/scaled from training data only; negative predicted volumes are clipped at zero.

Training years: 2001, 2004, 2005, 2007, 2008, 2009. Test years: 2011, 2012, 2014, 2015.

| Model | Test years | RMSE (million m³) | Bias (million m³) | NSE | RMSE skill vs climatology | RMSE skill vs climate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| seasonal_climatology | 4 | 365.50 | 336.83 | -5.636 | 0.000 | -0.378 |
| climate | 4 | 265.27 | 255.41 | -2.496 | 0.274 | 0.000 |
| climate_plus_snow | 4 | 376.03 | 361.91 | -6.024 | -0.029 | -0.418 |
| climate_plus_snow40 | 4 | 389.80 | 373.30 | -6.548 | -0.066 | -0.469 |
| climate_plus_swe | 4 | 427.66 | 373.79 | -8.085 | -0.170 | -0.612 |

Terra-only coverage check: 4 eligible training years and 2 test years; status `insufficient_eligible_years`. The analysis requires at least six training and three test years before fitting these specifications. This threshold is a minimum feasibility gate, not a guarantee of strong statistical evidence.

### Climate-only cohort, without a satellite-coverage gate

Retrospective April 1 issue date. October–March precipitation and March temperature/SWE only; no satellite snow coverage requirement. Fixed ridge alpha=1; same complete years for every model; no held-out tuning.

Training years: 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010. Test years: 2011, 2012, 2013, 2014, 2015, 2016. This larger cohort is a separate experiment; its scores cannot be used to claim snow improvement on a different set of years.

| Model | Test years | RMSE (million m³) | Bias (million m³) | NSE | RMSE skill vs climatology |
| --- | ---: | ---: | ---: | ---: | ---: |
| seasonal_climatology | 6 | 509.30 | 491.81 | -13.807 | 0.000 |
| climate | 6 | 358.37 | 335.77 | -6.331 | 0.296 |
| climate_plus_swe | 6 | 382.89 | 333.81 | -7.369 | 0.248 |

Positive RMSE skill means lower error than the named baseline; negative skill means worse error. All tested specifications are retained, including failures. The snow40 model tests snow-threshold sensitivity; the SWE model uses reanalysis snow mass rather than observed snow extent. These tests measure retrospective association and predictive utility, not causal snowmelt attribution. Retrospective product latency and the provisional boundary prevent operational forecast claims. Small test samples produce broad uncertainty. [NSE/KGE benchmark interpretation](https://hess.copernicus.org/articles/23/4323/2019/).

Excluded years: 2002: March combined snow coverage fails minimum; 2003: March combined snow coverage fails minimum; 2006: March combined snow coverage fails minimum; 2010: March combined snow coverage fails minimum; 2013: March combined snow coverage fails minimum; 2016: March combined snow coverage fails minimum; 2017: incomplete screened April–September observed volume.

## 5. Charvak extent, not assumed storage

JRC provides 264 monthly records; 126 pass the ≥95% valid-area rule within the fixed analysis domain. Detected water area is not scaled up to fill unobserved pixels. The series stops in 2021 because that is the end of this JRC version. [JRC monthly water-history classes, coverage and attribution](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_MonthlyHistory).

Among eligible months, detected water area ranges from 15.96 km² (2020-03) to 36.33 km² (2019-08). These are extrema of the screened available observations, not guaranteed extrema of actual reservoir operation.

Landsat-derived JRC water detections within HydroLAKES 14452 plus 1 km buffer; may include adjoining channels. Not independently validated shoreline area, bathymetry or storage. Cloud/no-data months remain gaps.

JRC is generated from Landsat, so a Landsat-derived comparison would not be fully independent. Pskem discharge covers only one tributary; without other inflows, releases, diversions and independent levels/bathymetry, no absolute storage or operational rule is validated.

### Sentinel-2 verification

Same-month independent-sensor comparison: JRC monthly Landsat water against highest-coverage Sentinel-2 scene; ≥95% coverage in both. MNDWI>0 and NDVI<0.3; MNDWI>0.1 sensitivity.

There are 26 qualified month pairs. Sentinel-2 minus JRC bias is -0.16 km²; RMSE is 1.07 km². The CSV retains the Sentinel-2 acquisition date and both water thresholds.

Sentinel-2 SCL removes no-data, defective, shadow, cloud/cirrus and snow/ice classes. Within each month the highest valid-area scene is selected, with earliest date breaking ties; selection does not optimise agreement. The 20 m SWIR grid defines the reduction. [Sentinel-2 harmonised surface reflectance and SCL](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED). JRC is not ground truth and its monthly dates differ from the selected Sentinel-2 acquisition. Optical errors can be correlated. No manually labelled shorelines yet.

## Spatial verification and representativeness

The stored gauge coordinate is effectively on a small tributary. Two larger Pskem reaches lie roughly 700 m away. An automatic nearest-reach snap would select the wrong hydrological scale; no coordinate was changed. The full-unit basin trace is retained only as a provisional experimental domain.

| Candidate reach | Distance (m) | Upstream area (km²) | Reference discharge (m³/s) |
| --- | ---: | ---: | ---: |
| 40297414 | 0.1 | 11.7 | 0.21 |
| 40296998 | 694.3 | 2496.6 | 54.47 |
| 40297155 | 715.5 | 2509.6 | 54.81 |

SRTM gives terrain context, not surveyed station elevation or the actual ERA5 model orography. These differences should not be used as a verified lapse-rate correction.

| Station | SRTM at coordinate (m) | Mean SRTM within ERA5 cell (m) | Difference (m) |
| --- | ---: | ---: | ---: |
| Tashkent | 472 | 451 | -21 |
| Pskem | 1445 | 1689 | 244 |
| Oygaing | 2222 | 2974 | 752 |

At Pskem, the terrain difference is much smaller than would by itself explain a 7°C offset under a conventional lapse-rate assumption. Station representativeness, observing definitions and model orography therefore remain open questions; the successful empirical correction is not a causal explanation. [SRTM data specification](https://developers.google.com/earth-engine/datasets/catalog/USGS_SRTMGL1_003).

## Conclusions and next discriminating tests

1. Select climate forcing by station, variable and held-out error; raw seasonal correlation alone is insufficient. Audit station elevations, relocations and product station contributions before treating the comparisons as independent.
2. Use MODIS valid-area and missing-day budgets in every snow interpretation. Cross-sensor agreement and station snow-day bounds answer different questions and should not be merged into one accuracy score.
3. Retain the seasonal-flow baseline and every tested model. Added snow predictors must reduce held-out error; a plausible process story is insufficient. Extend discharge observations beyond 2017 before operational use.
4. Review the gauge-to-reach match and outlet-unit delineation, then repeat basin reductions to measure boundary sensitivity. A whole level-12 unit is a candidate spatial approximation.
5. Publish Charvak water extent with observation completeness. Upgrade to storage only when independent height and elevation–volume constraints support it.
6. Glacier-source attribution and land-use classifier accuracy remain separate studies. Neither is validated by a successful station comparison or runoff fit.

## Reproduction

```bash
npm run cases:forcing
python PIPELINES/extract_chirchik_remote.py --task climate
python PIPELINES/extract_chirchik_remote.py --task snow
python PIPELINES/extract_chirchik_remote.py --task reservoir
python PIPELINES/extract_chirchik_remote.py --task reservoir-check
python PIPELINES/audit_chirchik_spatial.py --terrain
npm run cases:analyse
npm run cases:build
npm run cases:figures
npm run cases:figures:validation
```

Input hashes, fitted coefficients, paired records, model predictions and uncertainty intervals are in advanced-validation.json and the adjacent CSVs. Earth Engine source image identifiers accompany the remote tables; cache files allow reproducible retrieval recovery without discarding completed years.
