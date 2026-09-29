# Seasonal flow forecasts from snow: Pskem, then seven more gauges

**Build date:** 2026-09-29. **Status:** research result, not yet on the website.

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

## Next steps

1. Download the USGS SnowModel release for the Kashkadarya and rerun the four
   gauges with its elevation-band SWE in place of ERA5-Land, to measure how much
   downscaled snow adds out of sample.
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
