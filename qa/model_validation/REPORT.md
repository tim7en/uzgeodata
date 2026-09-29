# Pskem monthly model: first validation pass

Run: `python qa/model_validation/check_pskem.py` (Python, `duckdb`, `numpy`). The script reads the published gauge and basin geometry, the dated observation store and the published model coefficients. It independently converts discharge to catchment depth, aggregates the three predictor fields, refits OLS, calculates predictions, derives a training-only monthly climatology and scores the held-out observations. Exact input hashes, month keys and numerical output are in [`results.json`](results.json). The observation row selection still uses the repository's `query` view for run completion and revisions, so this is a separate metric calculation, not a fully independent rebuild of the source observations.

## Model and split

The published artifact is a three-predictor linear association between same-month precipitation, maximum temperature, snow cover and gauge 16290 discharge depth over a 20-basin, 2,626.9 km² catchment. Its fixed chronological training interval is January 2003–December 2012 (120 months); evaluation is January 2013–December 2017 (59 valid months). February 2015 is excluded because the gauge CSV labels 29 observed days in a 28-day month. All predictor cells required for the 180 nominal months were present; the one evaluation loss is in the target. Coefficients refitted from the source series match the published coefficients exactly at printed precision.

## Held-out results

| Score, mm/month except skill | Model | Training-month climatology |
| --- | ---: | ---: |
| n | 59 | 59 |
| Bias (prediction minus observation) | +13.984 | +9.184 |
| MAE | 28.014 | 13.106 |
| RMSE | 35.834 | 19.278 |

The model's conventional Nash–Sutcliffe efficiency against the **evaluation-period mean** is +0.550. Its squared-error skill against the **training-period calendar-month climatology** is −2.455. Both published figures are reproduced within numerical rounding. The model has 3.46 times the climatology's sum of squared errors. These reference definitions differ; the positive NSE does not establish benefit over a seasonal baseline.

For November–April, model RMSE is 23.84 versus climatology 10.59 mm/month (29 months). For May–October it is 44.45 versus 24.95 (30 months). Target-flow terciles were cut using training observations: in 19 low-flow evaluation months, model RMSE is 21.66 versus 6.05; in 17 high-flow months, 34.36 versus 31.46. The model's held-out residual median is +15.03 mm/month; range −98.48 to +74.51. These are descriptive groups from one basin, with few independent years.

## Verdict and limits

**Verified result:** the printed performance metrics and temporal split are arithmetically reproducible from published series; the model performs worse than training-month climatology on this holdout. The published report already states the negative climatology skill, so this is a confirmed limitation rather than an undisclosed defect. `README.md` calls the artifact a “validated model result”; a clear caption should emphasize its negative skill against the seasonal baseline.

**Not verified:** prospective forecast skill. The model uses climate values from the same target month and has no issue date, lead time or real-time availability audit. It is best classified as a historical statistical reconstruction. Neither the model JSON nor this check provides a predictive or confidence interval; calibration and empirical interval coverage cannot be tested. The model JSON's `independence` statement concerns the gauge's origin, but does not establish independence of model choice from evaluation results. Snow-cover missingness outside this historical split, spatial transfer, and different catchments require separate work. No production model was changed.
