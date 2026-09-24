# Amu Darya and Syr Darya climate continuation

**Build date:** 2026-09-24. **Frame:** all 7,445 level-12 basins (4,917 Amu
Darya, 2,528 Syr Darya). The versioned data package is
`PUBLISHED/data/atlas/climate-continuation/`.

## Two different TerraClimate products

The atlas cube contains the Earth Engine TerraClimate v1.0 series through
December 2024. The [producer's v1.1 release](https://www.climatologylab.org/terraclimate.html)
changes the climate inputs to ERA5 anomalies and changes parts of the water
balance model. The producer explicitly advises against mixing v1.0 and v1.1
in one series. Its [yearly NetCDF catalogue](https://climate.northwestknowledge.net/TERRACLIMATE-DATA/)
currently offers 2025 but no 2026 file. The v1.1 2025 product is reduced
directly to every basin and kept under its own product name. It is a modelled
climate and water-balance product, not a station measurement.

The direct v1.1 extraction covers **14 variables × 12 months × 7,445 basins =
1,250,760 rows**, with complete spatial coverage in this build. It includes
precipitation, minimum and maximum temperature, AET, PET, water deficit, runoff,
soil moisture, radiation, SWE, vapour pressure, wind, VPD and PDSI. The code
reads each NetCDF file's packed scale and offset. In v1.1, for example,
precipitation has scale 0.1, while minimum and maximum temperature have scale
0.01 and offset −99 °C. Reusing the older Earth Engine factors would produce
wrong values.

An overlapping 2024 v1.1 extraction was compared to the atlas v1.0 basin
values. The v1.1–v1.0 RMSE is **4.97 mm/month** for Amu precipitation and
**3.65 mm/month** for Syr precipitation; for minimum temperature it is
**1.32/1.64 °C**, and for maximum temperature **1.54/1.15 °C**. This difference
includes the changed product method and a changed zonal reduction. It is large
enough to keep their identities separate in trend and monitoring work.

## ERA relationship and held out test

[ERA5-Land monthly reanalysis](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_MONTHLY_AGGR)
is reduced on its native 0.1° grid by fractional overlap with each basin. For
each basin and calendar month, a fixed additive offset maps ERA monthly mean
temperature to the v1.0 minimum or maximum temperature statistic. A fixed
multiplicative factor maps ERA monthly precipitation to v1.0 precipitation.
Local coefficients are shrunk toward each river system's monthly coefficient
using eight pseudo-years. Training uses 2003–2018 only. All 2019–2024 values
are held out; continuation is generated only when both RMSE and MAE improve
in **both** river systems.

| Held out 2019–2024 RMSE | Amu ERA | Amu adjusted | Syr ERA | Syr adjusted |
| --- | ---: | ---: | ---: | ---: |
| Precipitation, mm/month | 23.11 | **6.92** | 35.53 | **6.13** |
| Monthly minimum temperature, °C | 5.93 | **1.24** | 5.87 | **0.81** |
| Monthly maximum temperature, °C | 8.06 | **1.09** | 6.99 | **0.77** |

The 2025–August 2026 v1.0 continuation contains **446,700 explicitly estimated
basin-month rows**. Each has the raw ERA value and a river-system-specific 90th
percentile of absolute held out error. These are product-emulation errors, not
station uncertainty intervals. Subbasins share coarse ERA cells, so the row
counts are not counts of independent validation sites. The Pskem point check
in [the companion study](pskem-climate-continuation.md) shows that basin skill
does not establish mountain station accuracy.

Comparing the 2025 v1.0 estimate against direct v1.1 gives 6.04 mm/month
precipitation RMSE and about 1.97–1.99 °C temperature-extrema RMSE across
basins. This measures product agreement across a version change. Because
v1.1 itself uses ERA5 anomalies, it is **not independent verification** of
the ERA model.

## Water-balance emulation

The eight remaining v1.0 water-balance variables are continued with a separate,
simpler model (`PIPELINES/model_regional_climate_water_balance.py`). Twelve extra
ERA5-Land monthly fields are reduced to every basin in the same way
(`era5-land-extended/`). Each target has one ERA predictor: evaporation for AET,
potential evaporation for PET, PET minus AET for water deficit, runoff for runoff
(`q`), layer-2 soil water for soil moisture, snow water equivalent for SWE,
the Tetens deficit from temperature and dewpoint for VPD, and the trailing
six-month precipitation minus PET for PDSI. For each basin and calendar month,
the 2003–2018 predictor anomaly is scaled onto the v1.0 climatology. The local
slope is non-negative, capped at four times the system slope and shrunk toward
the river-system/month slope using eight pseudo-years. Flux estimates are
floored at zero.

The baseline for each variable is the basin/month 2003–2018 v1.0 climatology.
A variable is continued only if held-out 2019–2024 MAE and RMSE both improve in
both systems. All eight pass:

| Held out 2019–2024 RMSE | Amu climatology | Amu ERA-adjusted | Syr climatology | Syr ERA-adjusted |
| --- | ---: | ---: | ---: | ---: |
| AET, mm/month | 10.25 | **8.57** | 11.40 | **10.29** |
| Climate water deficit, mm/month | 17.05 | **9.68** | 16.24 | **9.44** |
| PET, mm/month | 12.98 | **8.35** | 11.73 | **7.42** |
| Runoff generation `q`, mm/month | 40.64 | **39.92** | 11.89 | **10.00** |
| Soil moisture, mm | 8.29 | **6.99** | 10.37 | **8.79** |
| SWE, mm | 202.07 | **187.84** | 17.17 | **13.01** |
| VPD, kPa | 0.256 | **0.169** | 0.208 | **0.135** |
| PDSI | 3.54 | **2.52** | 2.97 | **2.16** |

The gains differ a lot between variables. Deficit, PET, VPD and PDSI improve by
roughly a third. Runoff and SWE improve only a little over climatology in the Amu
Darya, where a few basins with very large values dominate the RMSE. PDSI has a held-out bias of about
+1.5 to +1.9 index units, because a six-month balance cannot reproduce the Palmer
model's full soil-moisture memory. `water-balance-report.json` holds the scores,
bias and 90th-percentile error by system.

`v1.0-water-balance-continuation.parquet` holds **1,191,200 estimated rows** (8
variables × 20 months × 7,445 basins), each with its raw ERA predictor and the
held-out error scale. They join the upstream accumulation and the basin modal as
`estimated_v1.0` series beside the direct v1.1 values. These are statistical
emulations of a product, not runs of the TerraClimate water-balance model. `q`
is modelled runoff generation, not observed or routed river discharge.

## Upstream accumulation

`upstream.parquet` has 2,888,660 records. Each downstream basin accumulates its
own local value plus every upstream level-12 unit **once**, weighted by local
`SUB_AREA`. The output keeps the source product, covered fraction, upstream
area and area-weighted mean. Precipitation, AET, PET and runoff (v1.1 and estimated) also have
an integrated water-equivalent volume in million cubic metres (depth in mm ×
area in km² × 0.001). The v1.1 runoff quantity is **modelled generation**, not
routed observed discharge or reservoir inflow. Temperature, deficit, soil
moisture, SWE, VPD, PDSI and the other state variables are area-weighted means
with no volume. An incomplete upstream set yields a null mean rather
than silently dropping the missing area.

For January 2025 v1.1 precipitation, the terminal Amu and Syr basin means are
23.26 and 18.70 mm over 639,852.6 and 325,872.2 km² respectively; both have
full upstream coverage. These totals check the routing traversal against the
sum of local basin areas.

## Files and updates

| File | Content |
| --- | --- |
| `index.json` | Public product paths, periods and meanings. |
| `terraclimate-v1.1/year=2025.parquet` | All 14 direct producer variables at local basin support. |
| `terraclimate-v1.1-primary/year=2024.parquet` | Three-variable version-overlap check. |
| `era5-land/year=*.parquet` | Source ERA basin series, 2003–August 2026. |
| `coefficients.parquet` | Fitted basin and month adjustments. |
| `v1.0-continuation.parquet` | Separate, labeled 2025–2026 ERA estimates. |
| `era5-land-extended/year=*.parquet` | Twelve ERA5-Land water and energy predictors, 2003–August 2026. |
| `water-balance-coefficients.parquet` | Basin/month anomaly slopes for the eight water-balance targets. |
| `v1.0-water-balance-continuation.parquet` | Labeled 2025–2026 water-balance estimates. |
| `water-balance-report.json` | Held-out water-balance scores against climatology. |
| `upstream.parquet` | Product-specific upstream means and eligible flux integrals. |
| `basins/{HYBAS_ID}.json` | Modal chart and CSV source for each of the 7,445 basins. |
| `basins-index.json` | Per-basin download schema and base URL. |
| `report.json` | Held out scores, source hashes and version comparisons. |

On the basin map, open a level-12 basin and choose **Climate 2025–26**. The
chart distinguishes the direct v1.1 product from the ERA-derived v1.0 estimate,
and the support control switches between local and upstream values. Each basin
offers CSV and JSON downloads with source, unit, coverage and applicable volume
or held out error fields. The existing **Monthly record** tab keeps the older
atlas series and does not silently extend it with either new product.

Rebuild with the pipeline environment installed:

```bash
npm run climate:regional:update
```

The TerraClimate command checks the producer's file listing and takes every
available year from 2025 onward. `--refresh` rereads a year if the producer
revises it. The ERA command updates the latest year when new months appear and
repairs an earlier partial year once the next year begins. The source files
remain separate, and future direct v1.1 years appear as direct products beside
the older v1.0 estimates. The Cloudflare release manifest declares this
versioned package for the next publication build.

The 2024 product-version overlap used for this case study can be refreshed
separately with `python PIPELINES/extract_regional_climate_grids.py
terraclimate-v11 --years 2024 --variables ppt,tmin,tmax --refresh`.

**Scope limit:** 2026 has no direct v1.1 release yet. The 2025–2026 v1.0 values
for all eleven continued variables are ERA-based statistical estimates. The
eight water-balance variables are emulated from single ERA predictors and are
not outputs of the TerraClimate water-balance model. They are weakest for
glacier-dominated runoff and SWE. No row here is observed reservoir storage,
river discharge or a forecast.
