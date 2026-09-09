# Pskem model and findings review — 2026-09-09

The former findings grid mixed runoff modelling, station-product comparisons,
reservoir mapping and trend analysis. Those are related studies, but their
figures do not jointly demonstrate seasonal forecast skill. The page now leads
with the chronological runoff experiment and retains the other analyses under
an explicitly labelled supporting-evidence disclosure.

## Corrections

- Removed the unsupported assertion that elevation bands reduced April error
  from 60% to 8%; the cited summary did not contain that controlled comparison.
- Replaced an incorrect calibration-year range (the first two entries in a
  nonconsecutive year list) with the actual configured years and warm-up rule.
- Seasonal class thresholds now use calibration observations only. Previously
  validation outcomes helped define the class thresholds. The old reference's
  within-one-class result changes from seven of seven to six of seven.
- Removed duplicate model figures from the headline grid. The new primary
  charts show monthly flow and seasonal volume against observations and a
  training-only climatology, at readable size. Supporting images retain their
  full aspect ratios rather than cropped thumbnails.

## New experiment

Command:

```powershell
python PIPELINES/build_pskem_daily_model.py --samples 6000 --split chronological --seed 1729 --output-dir PUBLISHED/data/case-studies/model-audit/chronological-20260909
```

The search evaluated 6,000 broad candidates plus four refinement rounds of 3,000.
Selection used calibration KGE only; physical bounds were unchanged. Scored
calibration years are 2002–2010; validation years are 2011–2017. Forcing starts
in 2000, and the original 2001 observation warm-up exclusion is retained.
The existing discharge-stratified reference was preserved, not overwritten.

| Held-out target | Pairs | Chronological model NSE | Training climatology NSE | Model bias |
| --- | --- | --- | --- | --- |
| Daily flow | 2,550 | 0.7228 | 0.6904 | +16.021% |
| Monthly mean flow | 84 | 0.7595 | 0.7381 | +16.074% |
| April–September volume | 7 | −1.0386 | −3.8733 | +16.587% |

The model modestly improves on the training-only climatology but does not
establish reliable seasonal-volume prediction. Negative seasonal NSE means
worse squared error than the *held-out seasonal mean*, a diagnostic reference
that would not itself be known prospectively. Seasonal class thresholds fitted
to the nine calibration years give two exact and six within-one-class matches
among seven validation years.

The earlier monthly NSE of 0.9008 came from a different, outcome-stratified
split. It is not a directly comparable accuracy gain or loss. The chronological
run is foregrounded for its clearer temporal test, not because it has the
highest score. No further parameter selection was performed against this
exposed holdout.

## Parameters and limitations

Selected parameters: tt −1.5, cfmax 2.4713, sfcf 1.2991, fc 127.3605,
beta 3.3967, perc 3.6996, k_fast 0.05, k_slow 0.0119, lapse −7.472 °C/km.
The threshold and fast-reservoir coefficient reach their bounds. This suggests
reviewing forcing and structure, not automatically widening bounds.

Monthly means follow this model's minimum 20 paired-day rule. Seasonal volumes
integrate available paired days, without extrapolation; coverage is downloadable.
The candidate catchment, gridded forcing, retrospective discharge screening,
unobserved SWE and absence of independent temperature profiles remain limits.

Next development should use inner cross-validation confined to calibration
years, forcing/bias diagnostics and independent hydrological observations.
Further tuning against 2011–2017 would require a new external test before
claiming generalization. Model complexity alone is not evidence of accuracy.

Outputs: `model-review.json` (scores, chart values, baseline, parameters and input
hashes) and the separately retained `model-audit/chronological-20260909/` run.
`npm run cases:publish` rebuilds the review and presentation without refitting.
