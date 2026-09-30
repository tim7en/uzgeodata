# Seasonal flow forecasts from snow: Pskem, then seven more gauges

**Build date:** 2026-09-29. **Page:** `/snow-forecast`. **Per-basin view:** the **Snow forecast** tab on level-12 basins in the basin explorer. Outputs: `PUBLISHED/data/case-studies/snow-forecast/`.

## Question

Can snow and precipitation known on 1 January, February, March or April predict
the April–September (vegetation-season, irrigation) mean flow of a mountain river?
And have flow, melt timing or snow changed?

## Where the design comes from

The design follows a USGS and Uzhydromet HMRI study of the Kashkadarya (Barnhart,
Umirzakov, Gafurov, Yarashev, Crowley-Ornelas and Asquith). It used the
vegetation-season target, forecast months 1 to 4, and predictors of basin and
200 m elevation-band snow water equivalent, cumulative October-onward
precipitation and monthly temperature, with a bootstrapped regression. Their snow
comes from SnowModel (Liston and Elder, 2006) forced with downscaled ERA5-Land,
published as *Simulated Snow and Meteorology Variables, Qashqadaryo Region,
Uzbekistan, 1950–2023* (USGS data release, doi:10.5066/P1IHVOVG). Their journal
article is in review. The slides shared with the project are marked preliminary
and not for citation, so none of their figures are reproduced here.

No SnowModel run exists for the Chirchik basins. This study therefore takes the
same predictors straight from **ERA5-Land DAILY_AGGR** on its native 0.1° grid,
which is available everywhere from 1950. Whether that coarser snow still carries
the signal is the question being tested.

## Data

- **Flow:** CA-discharge 2023, 10-day values 1932–2016, as monthly means of three
  complete decades. For Pskem, the Uzhydromet monthly workbook adds 2016–2017. Over
  185 overlapping months the two sources agree at r = 0.9988 with a mean ratio of
  1.003.
- **Snow and weather:** ERA5-Land daily SWE, precipitation and 2 m temperature for
  every grid cell touching the gauge basin (47 cells for Pskem), weighted by
  overlap. Each cell is given its mean SRTM elevation to form 200 m bands.

## Method

Each forecast uses only information from before its issue date. Three kinds of
skill are reported:

1. **In-sample adjusted R²** of the best model with up to three predictors, with a
   1,000-sample bootstrap. This matches how the USGS study reports skill, and it
   is optimistic.
2. **Leave-one-year-out cross-validation**, with the predictor search repeated
   inside every fold.
3. **Operational hindcast**, the headline measure. From 1971, every year is
   forecast from a regression on April 1 basin-mean SWE, fitted on earlier years
   only. The forecast is then shifted by the mean error of the previous ten years.
   Skill is 1 − MSE(forecast) / MSE(previous 30-year mean), so 0 means no better
   than the average a manager would otherwise use.

Trends use tie-corrected Mann–Kendall with Sen's slope.

## Pskem: what worked and what did not

| Issue | In-sample adj. R² | LOYO R² | Operational skill 1971–2017 | 1996–2017 |
| --- | ---: | ---: | ---: | ---: |
| 1 Jan | 0.30 | 0.24 | 0.05 | −0.40 |
| 1 Feb | 0.33 | 0.17 | 0.22 | −0.15 |
| 1 Mar | 0.41 | 0.24 | 0.42 | 0.15 |
| 1 Apr | 0.58 | 0.46 | **0.58** | **0.32** |

- **Forecasts are useful from 1 March, and best on 1 April.** In January and
  February the snow that matters has not fallen yet.
- **Free predictor search overfits.** It repeatedly picked October and November
  temperature, and those models failed on 1996–2017 (NSE −0.61 to −0.05). April 1
  basin-mean SWE alone did better out of sample.
- **Runoff per unit of snow has fallen.** Every model fitted on earlier years
  over-predicts the recent years by 8–19 m³/s. Mean flow dropped from 137 m³/s
  (1951–1978) to 124 m³/s (1996–2017) while ERA5-Land precipitation and snow did
  not. The ten-year level correction removes most of that bias (+11 to +4 m³/s).
- **Trends:** vegetation-season flow is −3.2 m³/s per decade over 1951–2017, not
  significant (p = 0.10). The flow centre of volume has moved **2 days per decade
  earlier since 1991 (p = 0.001)**. ERA5-Land shows no trend in peak SWE, its
  timing or winter temperature at Pskem's elevations (all cells are above
  1,690 m). The river records the earlier melt; the 9 km snow grid does not.

## Scaling test

| Gauge | Area km² | Apr in-sample adj. R² | Apr LOYO R² | Apr operational 1971–2017 (1996–2017) | Centre of volume since 1991 |
| --- | ---: | ---: | ---: | ---: | --- |
| Pskem – Mullala 16290 | 2,518 | 0.58 | 0.46 | 0.58 (0.32) | −2.0 d/decade, p = 0.001 |
| Chatkal 16279 | 5,669 | 0.68 | 0.60 | 0.64 (0.58) | −4.0 d/decade, p = 0.04 |
| Ugam – Khozhikent 16300 | 863 | 0.62 | 0.49 | 0.40 (0.32) | −2.5 d/decade, p = 0.08 |
| Charvak inflow 16924 | 9,983 | 0.71 | 0.61 | 0.63 (0.54) | −1.5 d/decade, p = 0.03 |
| Varganza 17231 | 480 | 0.48 | 0.30 | 0.24 (0.40) | none |
| Kattagan 17257 | 437 | 0.42 | 0.03 | 0.47 (0.49) | none |
| Gumbulak 17275 | 1,565 | 0.52 | 0.30 | 0.28 (0.34) | none |
| Bazartepa 17279 | 1,314 | 0.46 | 0.40 | 0.30 (0.25) | none |

- **ERA5-Land snow is enough for the large, high Chirchik basins.** Chatkal and
  Charvak inflow keep more than half of their April skill in 1996–2017.
- **It is weaker for the small Kashkadarya basins.** They are 13–30 grid cells
  wide and drier, and the gap between in-sample and cross-validated skill is
  large. This is where downscaled snow should help: the USGS SnowModel data
  release covers these basins from 1950 to 2023.
- **No significant vegetation-season flow trend at any of the eight gauges.**
- **Earlier melt shows only in the Chirchik system.** No Kashkadarya gauge shows
  a timing trend.

## Regional run: every gauged catchment

`PIPELINES/extract_snow_forecast_region.py` stores, for each water year from
1951, one 40-band ERA5-Land grid over the whole Aral region: SWE on the day before
each issue date, plus monthly precipitation, temperature and SWE. Cells whose
September SWE exceeds 500 mm in most years are ERA5-Land glacier cells, and are
kept out of every SWE predictor. `PIPELINES/build_snow_forecast_region.py`
reduces the grids to every CA-discharge catchment that drains to the Aral Sea
and has at least 25 complete April–September seasons since 1951. It then scores
each one the same way as the single-basin study, using 500 m bands.

**52 gauges were scored.** On Pskem, Chatkal and Charvak inflow the regional
store reproduces the daily-cell study to within 0.01 in skill.

| Issue | Median operational skill (IQR) | Gauges above 0 |
| --- | --- | ---: |
| 1 Jan | 0.09 (0.00–0.15) | 73% |
| 1 Mar | 0.26 (0.15–0.36) | 94% |
| 1 Apr | **0.39 (0.24–0.50)** | **94%** |
| 1 Apr, 1996–2017 only | 0.34 (0.20–0.49) | 71% |

- **Strongest:** the Chirchik system (median 0.58), Akhangaran, Kofarnikhan,
  Vakhsh, and Akdarya and Yakkabagdarya in the Kashkadarya.
- **Weakest:** Zeravshan (median 0.17), where glacier melt that winter snow
  cannot see feeds the summer flow, and a few small Fergana-valley rivers
  (Akbura, Isfara, Karakol) and the Rovatkhodzha diversion inflow.
- **Regulated gauges:** seven gauges have a dam in their catchment. They mostly
  score well because they are reconstructed reservoir inflows (Toktogul,
  Charvak, Nurek/Vakhsh). Where at least 25 years precede the dam, the
  pre-regulation score is stored as well.
- **Coverage gap:** the Amu Darya headwaters are thin in this gauge set. No
  Pyanj gauge has 25 complete seasons after 1951.

**Association with basins.** Each gauge is linked to the level-12 basin at its
location whose upstream area best matches the catchment (51 of 52 within a
factor of 1.5). Walking down the river network, every level-12 basin is tied to
the nearest scored gauge below it. 1,208 basins, mostly the headwater zone, are
covered by a tested forecast, and 929 of those by one with April skill above 0.3.
For all 7,445 basins and every water year, the build also stores April 1 SWE and
October–March precipitation, both locally and accumulated over the upstream area
(SWE volume in km³). These are inputs for forecasting ungauged basins later.

| File in `PUBLISHED/data/case-studies/snow-forecast/region/` | Content |
| --- | --- |
| `gauges.json` | Every score, predictor choice, hindcast series, regulation flag and full-precision annual SWE/flow inputs for refitting the operational hindcast per gauge and issue date |
| `gauge-skill.csv` | One row per gauge, all issue months |
| `gauge-basin-links.csv` | Gauge to level-12 outlet basin, with area ratio |
| `basin-gauge-association.csv` | Each level-12 basin to its nearest scored downstream gauge and that gauge's skill |
| `basin-glacier-cell-share.csv` | Share of each basin under ERA5-Land glacier cells |
| `verification-manifest.json` | SHA-256 hashes for the source GeoPackage, extracted yearly grids, methods and public regional outputs |
| `verify-snow-forecast-region.py` | Standalone verifier for the operational scores in `gauges.json` (requires NumPy and pandas) |
| `basin-predictors.parquet` | 7,445 basins × 76 water years, local and upstream April 1 SWE and Oct–Mar precipitation (gitignored, rebuilt by the script) |

## Next steps

1. Download the USGS SnowModel release for the Kashkadarya and rerun the four
   gauges with its elevation-band SWE in place of ERA5-Land, to measure how much
   downscaled snow adds out of sample. ScienceBase serves its files only to a
   browser (a Cloudflare challenge blocks scripts), so the yearly
   `QASH100_swed_wy<year>.nc` and `QASH100_prec_wy<year>.nc` files, `dem.asc` and
   `projection.wkt` have to be downloaded by hand into `storage/usgs-snowmodel/`.
2. Replace the ten-year level correction with an explicit cause (glacier area,
   warming or irrigation withdrawals) if one can be shown.
3. Add real-time issue: the ERA5-Land record already runs to the current month,
   so a 1 April forecast for the coming season can be produced each spring.

## Reproduce

```bash
python PIPELINES/extract_snow_forecast_forcing.py --gauge 16290   # ~5 min, Earth Engine
python PIPELINES/build_snow_forecast_study.py --gauge 16290       # ~1.5 min
python -m pytest TESTS/test_snow_forecast_study.py -q
```

Outputs per gauge are in `PUBLISHED/data/case-studies/snow-forecast/{CODE}/`:
`study.json` (all scores, trends and series), `predictors-and-targets.csv` and
`cells.json`. The daily ERA5-Land cell files are gitignored and rebuilt by the
extractor.

For the regional results, run
`python PIPELINES/build_snow_forecast_region.py --inputs-only` on the computer
with the cached ERA5-Land regional grids, gauge score checkpoints and
CA-discharge source. A full `python PIPELINES/build_snow_forecast_region.py` run
also produces these inputs.
This attaches `operational_inputs` to every scored issue in `region/gauges.json`,
including gauges whose score checkpoint was reused. The build rejects a cached
score if the current SWE or discharge inputs no longer reproduce it. Then run
`python PIPELINES/verify_snow_forecast_region.py` to refit and check every
operational hindcast from the published input rows. The rows are full precision;
the chart-oriented hindcast series remain rounded to two decimal places.
After a full regional rebuild, run
`python PIPELINES/build_snow_forecast_manifest.py` to refresh provenance hashes.
For a public verification without this repository, download `gauges.json` and
`verify-snow-forecast-region.py` into one directory and run
`python verify-snow-forecast-region.py` after installing NumPy and pandas.
