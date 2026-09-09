# Sabitov (2018): full-thesis methodology audit and implemented Pskem experiments

This review uses the supplied 76-page file `storage/Sabitov_Master_ERE_2018.pdf`, read in full. Page references below are printed thesis pages; add nine for the PDF page number. Timur Sabitov is the sole thesis author; supervisors are not listed here as coauthors. The earlier abstract-only review is superseded.

## Finding

Our earlier case study had monthly water-balance, random-forest and Bayesian comparisons but lacked the daily hydrologic structure central to the thesis. The extension now executes four daily model adaptations, elevation-dependent snow and glacier processes, five-day antecedent rainfall, SCS runoff, distinct soil and groundwater stores, Hamon ET, flow-duration analysis, monthly trend diagnostics and climate stress tests. It retains the existing statistical models as separate monthly experiments.

A more elaborate model is not automatically more credible. Daily and monthly scores answer different questions; a good discharge curve can conceal wrong snow storage, ET or glacier melt. The new outputs expose these checks and limitations rather than declaring the best score operational.

## What the thesis actually did

Chapter 2 used local Pskem climate and streamflow, glacier information, DEM topography and a six-class unsupervised Landsat classification. Model 1 was a lumped snow/storage balance; Model 2 added three elevation zones and empirical glacier melt; Model 3 added SCS runoff and separate unsaturated/saturated stores in a lumped basin; Model 4 combined the SCS structure with elevation zones. The thesis assumed CN near 50 downstream and 90 in the upper rocky/glaciated zone, seasonal lapse-rate magnitudes of 6–6.7 °C/km, and an empirical glacier temperature at 3643 m. These were partly calibrated/assumed properties, not distributed observations (pp.24–35).

The last two observed years were used for calibration after a first-year warm-up (p.36). There is no independent later test period in that description. Table 2-4 (p.53) reports daily NSE 0.70, 0.23, 0.76 and 0.29 for Models 1–4; monthly NSE is 0.90, 0.24, 0.77 and 0.69. The abstract gives monthly R² values 0.84, 0.77, 0.93 and 0.85; body passages use correlation terminology. Do not equate r, R² and NSE. Model 1 achieves its attractive fit with zero ET; that is not adopted as a physically acceptable calibration strategy here.

The simulation dates also need author/source-code clarification: the abstract describes water years 2013–2015, a results passage says October 2013–September 2015, and Table 3-1 gives 1095 daily values. Without original forcing and code, an exact numerical reproduction cannot be asserted.

## Method-by-method gap matrix

| Method | Thesis location | Current status | Implementation / remaining requirement |
| --- | --- | --- | --- |
| Daily forcing and time step | pp.15,24–35 | Implemented | 6,575 actual daily ERA5 values, 2000–2017; daily forcing is not inferred from monthly observations. |
| Four structural models | Table 2-1; pp.24–35 | Adapted | Lumped/distributed stores with and without glacier and CN processes; positive ET retained in all structures. |
| Three elevation zones and seasonal lapse rates | pp.22,26,34 | Adapted | Exact 2300/3300 m thresholds; open outer bounds retain all terrain; basin ERA5 mean conserved when temperature is redistributed. |
| Independent snow, soil and groundwater storage | Eqs.17–22 | Implemented | Daily conservation checks, field-capacity recharge and previous-day groundwater recession; release is 1 minus retention. |
| Five-day antecedent moisture and SCS runoff | Eqs.13–16 | Adapted | Prior rain only; dormant/growing thresholds in mm; daily-reset and event-accumulated variants, corrected SI retention. |
| Hamon PET and water-limited AET | Eqs.1–2; p.17 | Adapted | Explicit vapour-pressure units; compare corrected Hamon, literal printed equation and ERA5 potential evaporation. No forced 250 mm annual ET. |
| Glacier melt and area | Eqs.10–11; pp.28,34 | Adapted | Pskem-specific dated GLIMS inventory, finite ice reservoir, snow shielding; degree-day melt plus annual-cubic sensitivity. |
| Calibration and physical plausibility | p.36; Table 2-4 | Implemented | Fixed early calibration/later holdout; daily and monthly scores, seasonal baseline, budget/convergence and boundary parameters disclosed. |
| Flow duration and specific runoff | pp.20,38–41 | Implemented | Q50/Q90/Q95, Q90/Q50 proxy and area-normalized discharge; no unsupported recurrence-frequency extrapolation. |
| Monthly flow trends | pp.40–42 | Implemented | Kendall/Sen on 2001–2017 monthly flows with Holm correction; exploratory because serial correlation and short record remain. |
| Climate perturbation experiments | Chapter 3; pp.58–60 | Adapted | Warming/wetting and warming/drying stress tests with monthly timing and ice-area sensitivity. No date-specific 2050 forecast. |
| Satellite process checks | Extension beyond thesis | Implemented | Held-out MODIS snow and MOD16 ET comparisons retain coverage filters and different spatial supports; not independent field truth. |
| Land-cover confusion matrix | p.35; Table 2-3 | Awaiting reference labels | Executable user/producer/overall accuracy evaluation and reference table supplied. No invented labels or transferred 82% accuracy. |
| Soils and spatial curve numbers | pp.30–31 | Awaiting soil evidence | CN50/CN90 remain thesis assumptions with sensitivity; Esri classes alone cannot establish hydrologic soil groups. |
| Tributary mass balance and local lapse validation | pp.20–22 | Awaiting observations | No simultaneous Oigaing/Maydantal/Charalma discharge or thesis-period paired elevation-confirmed daily meteorology in supplied files. |
| Gauge, ice thickness and recent verification | pp.15,28 | Unresolved | Two gauge coordinates audited; fixed 15/30/60 m water-equivalent ice scenarios are not measurements; discharge ends in 2017. |

## Dimensional corrections and deliberate departures

1. **SCS depth and threshold.** Eq.16 prints `2540/CN − 25.4`, which is a centimetre expression. The implementation consistently uses `S = 25400/CN − 254` in millimetres; direct runoff is zero when liquid input is at or below `0.2S`. Depth is converted to m³/s only after area weighting. Five-day thresholds are 13/28 mm dormant and 36/53 mm growing; April–September is our declared season assumption. Antecedent rain excludes today. The basic curve-number relationship is event based. Daily resetting is retained as a thesis-style approximation and compared with an event-accumulated variant that resets after a day with at most 0.1 mm liquid input. The extension to snowmelt is empirical. [USACE SCS method](https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/canopy-surface-infiltration-and-runoff-volume/infiltration/scs-curve-number-loss-model).

2. **Groundwater and ET accounting.** Eq.20 releases `(1 − Kb) × SAT`, so Kb=0.99 releases 1% of previous groundwater storage per day. ET is removed once from available soil water, before field-capacity recharge; it is not subtracted from discharge again. Each zone checks precipitation minus ET minus runoff against changes in snow, soil, groundwater and glacier-ice stores.

3. **Hamon units.** Thesis Eqs.1–2 mix a cm/day PET label with a saturation-vapour-pressure formula whose output is kPa. Our primary form uses `es = 0.6108 exp(17.27T/(237.3+T))` kPa, vapour density `2167 es/(T+273.15)` g/m³ and `PET = 0.1651 (daylight/12) density` mm/day. The factor 2167 explicitly converts kPa to hPa relative to the usual 216.7 expression. Daylight is astronomical, and T≤0 gives zero PET as in the thesis. Literal printed Hamon (including cm-to-mm conversion) and ERA5 potential evaporation are separate sensitivities. Crop coefficient remains positive and ET cannot exceed available water. The thesis 250 mm/year literature target is not treated as an observation. [USACE Hamon method](https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/evaporation-and-transpiration/hamon-method).

4. **Glacier melt.** Eq.10 labels the cubic ablation expression as m³/s, whereas Eq.11 requires annual ablation in mm/year. Applying the annual relationship directly as daily flow is dimensionally unsafe. The main adaptation instead uses 6 mm/°C/day ice melt at the stated 3643 m reference altitude, capped by remaining ice and shielded by remaining seasonal snow. The annual-cubic relationship divided by 365.25 is a sensitivity only; using daily temperature in it remains an empirical approximation. Snow melt uses a declared 4.5 mm/°C/day assumption, interpreting the thesis 0.45 coefficient as cm/°C/day; 3 and 6 mm alternatives are tested. No claim is made that these melt factors were locally measured.

5. **Initial ice and geometry.** Glacier outlines are fixed, and initial water-equivalent ice depth is assumed to be 30 m. Alternatives of 15/60 m and half mapped glacier area expose this uncertainty. Those depths are scenario parameters, not measured thickness or geodetic mass balance. Direct glacier drainage is a thesis assumption; separate routing/tracer observations are absent.

6. **Elevation and land cover.** Open lower/upper elevation bounds avoid dropping terrain outside the thesis 1251–4300 m domain. Temperature redistribution preserves the ERA5 basin mean around the DEM mean; it does not correct model orography or substitute unverified station elevations. Pskem station height is variously 1251/1254 m and the thesis elevation difference is arithmetically inconsistent; local lapse validation awaits resolved metadata. No unsupported positive precipitation gradient is imposed, especially because thesis higher Oigaing is drier. The 10 m Esri class series cannot distinguish every thesis mixed class or independently assign soil groups.

7. **DEM resolution and metrics.** ASF PALSAR RTC 12.5 m pixel spacing does not establish a native 12.5 m elevation model; source DEM resolution must be checked. The current 30 m Copernicus product is retained, with no artificial precision from resampling. Standard NSE uses paired simulated minus observed values; the apparent mean-observation substitution in thesis Eq.24 is not copied. Bias here is simulation minus observation. [ASF PALSAR documentation](https://docs.asf.alaska.edu/datasets/palsar/).

## Actual inputs and spatial audit

Earth Engine supplied 6,575 daily basin records from 2000-01-01 through 2017-12-31. Three 30 m raster zones total 2630.36 km², about 0.13% above the sum of nominal HydroBASINS areas (2626.9 km²); raster area is used consistently for the new depth-to-flow conversion. The thesis reports 2540 km². These boundaries are not interchangeable. [ERA5 daily catalogue](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_DAILY_AGGR).

The old headwater glacier export had no Pskem coverage. A catchment-specific GLIMS query selected 452 latest-per-ID outlines, removed matching internal rock and unioned overlaps. Rasterized ice totals 96.52 km² (3.67% of the candidate basin). Outline dates are 2000-09-23, 2002-07-10, 2010-08-30; the 2023 catalogue date is not a 2023 survey. This is a static hindcast inventory, including outlines surveyed after the earliest forcing years. [GLIMS catalogue](https://developers.google.com/earth-engine/datasets/catalog/GLIMS_20230607).

| Elevation zone | Area km² | Mean elevation m | Glacier area km² |
| --- | ---: | ---: | ---: |
| Below 2300 m | 709.89 | 1784.0 | 0.00 |
| 2300–3300 m | 1199.53 | 2842.1 | 4.61 |
| Above 3300 m | 720.94 | 3588.9 | 91.91 |

The thesis gauge position (p.15), 41°47′N 70°13′E, is 2.31 km from the existing coordinate. Both were checked against held HydroRIVERS geometry:

| Coordinate source | Longitude | Latitude | Closest reach | Offset m | Upstream km² |
| --- | ---: | ---: | --- | ---: | ---: |
| Existing station | 70.200000 | 41.766667 | 40297414 | 0.1 | 11.7 |
| Thesis p.15 | 70.216667 | 41.783333 | 40296998 | 277.2 | 2496.6 |

Neither coordinate was silently substituted. The complete nearest-reach alternatives are in `sabitov-methods.json`; original station metadata, river identity and a reviewed outlet delineation remain necessary.

## Held-out results

Daily calibration uses 3,652 screened observations in 2001–2010; evaluation uses 2,554 in 2011–2017. The invalid 2015-02-29 row and three manifest-flagged values are quarantined. Monthly comparisons use the same observed dates on both sides and at least 90% daily coverage. Missing gauge days are never filled.

| Model | Daily RMSE m³/s | Daily NSE | Monthly NSE | Modelled ice share | Mean AET mm/year |
| --- | ---: | ---: | ---: | ---: | ---: |
| Training seasonal baseline | 29.66 | 0.695 | — | — | — |
| M1 adapted · lumped snow and stores | 30.99 | 0.667 | 0.766 | 0.00% | 323.5 |
| M2 adapted · elevation and glacier | 25.92 | 0.767 | 0.837 | 0.00% | 101.8 |
| M3 adapted · lumped curve number | 27.30 | 0.742 | 0.826 | 0.00% | 273.7 |
| M4 adapted · elevation and curve number | 27.47 | 0.739 | 0.816 | 0.00% | 250.5 |

These are new adaptations evaluated on a different period and forcing, not recovered thesis results. Snow, ET, geometry and calibration constraints can change the ordering. The main figures show every predefined model; the holdout is not used to tune a winning structure. Optimizer budget/termination and parameter-bound flags are exported. A limited search does not establish a global optimum.

Maximum model water-balance residual is 3.4e-13 mm/day. This confirms numerical bookkeeping, not that flux magnitudes are correct. Fixed-parameter sensitivity experiments separate assumptions about CN, rainfall, ET, melt factors and glacier storage from fitted model performance.

## Process checks, low flows and climate scenarios

The M4 snow-area proxy has 27 eligible held-out MODIS monthly pairs; its RMSE is 9.32 percentage points. The ET check has 31 eligible MOD16 pairs and RMSE 18.50 mm/month. These differences include spatial/temporal support effects: three binary elevation zones versus fractional clear-sky snow, and whole-basin AET versus valid vegetated/terrestrial pixels. They reveal process mismatch, not independent sensor accuracy. Neither check influenced calibration.

Held-out observed Q50/Q90/Q95 are 39.85, 18.80, 17.50 m³/s. Q90/Q50 is 0.472; it is a low-flow persistence proxy, not hydrograph-separated baseflow. Specific runoff is 25.35 L/s/km² under the provisional area. Annual recurrence estimates and tributary closure are not manufactured from missing data or copied from the thesis table with inconsistent ratios.

Monthly Kendall/Sen analyses use the available 2001–2017 record and twelve-test Holm correction, not the thesis 1965–2015 record. Autocorrelation and the short record limit inference; nominal intervals and p-values are descriptive screening. No trend is labelled anthropogenic attribution.

Chapter 3 explored warming and altered precipitation. We implement rounded analogues (+2.2 °C/+5% P and +3.1 °C/+7% P), a +2 °C/−10% P case, and the latter with half glacier area. Both M3 and M4 retain frozen calibration and the same historical day sequence. Monthly hydrographs expose timing changes and structural disagreement. These are conditional stress tests, not calibrated probabilities, CMIP6 ensembles or a forecast for 2050.

## Remaining evidence required

The study can now execute the missing process methods, but additional measurements are still needed for defensible physical attribution: verified gauge position and drainage area; recent discharge/rating curves; daily station precipitation and temperature at confirmed elevations; glacier thickness or geodetic balance and area histories; hydrologic soil groups; independent land-cover labels; and tributary flow or routing constraints.

The reference CSV `CASE_STUDIES/landcover-reference-labels.csv` deliberately starts with no labelled samples. Add independently interpreted, dated samples with unique IDs and mapped/reference classes; rerunning computes the confusion matrix and user/producer/sample-overall accuracy. A stratified sample requires sampling probabilities and area-adjusted estimation before claiming basin-wide accuracy. The thesis 110 polygons and 82% overall accuracy do not transfer to Esri or to this basin/time automatically.

Dynamic glacier geometry, full surface-energy-balance melt, spatially supported soil/CN estimates, event routing and ensemble uncertainty remain separate extensions. Existing Bayesian/forest experiments are retained; they do not validate these physical parameters. Scientific readiness remains blocked even when every processing stage finishes.

## Reproduce and inspect

Run `npm run cases:sabitov:inputs` once for authenticated Earth Engine downloads, then `npm run cases:sabitov` for offline models, checks and artifacts. `npm run cases:update:offline` also includes these stages. Input/code SHA-256 hashes, source image IDs, projection, masks and dates are exported with `sabitov-methods.json` and `sabitov-artifacts.manifest.json`.

Outputs: `sabitov-methods-atlas.pdf`, six figure PNGs, `sabitov-methods-analysis.xlsx`, daily forcing/prediction tables, process components, flow-duration curves, month trends, scenario curves and the method gap matrix. The website includes these results under “Sabitov methodology”.

## Sources

- Sabitov, T. (2018), full local master thesis: `storage/Sabitov_Master_ERE_2018.pdf`; SHA-256 `36754b0494a58dc19133d77334e96fe61a3e7bbb4a26cd6df7a09886602cee6e`.
- [Author-uploaded thesis record](https://www.researchgate.net/publication/325033449_HYDROLOGIC_MODELING_OF_GLACIATED_WATERSHED_IN_CENTRAL_ASIA)
- [ERA5-Land daily aggregates](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_DAILY_AGGR)
- [SCS curve-number equations and event-model scope](https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/canopy-surface-infiltration-and-runoff-volume/infiltration/scs-curve-number-loss-model)
- [Hamon equations and calibration](https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/evaporation-and-transpiration/hamon-method)
- [ALOS PALSAR product resolution](https://docs.asf.alaska.edu/datasets/palsar/)
- [GLIMS snapshot](https://developers.google.com/earth-engine/datasets/catalog/GLIMS_20230607)
- [Copernicus GLO-30](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_DEM_GLO30_2024_1)
