# Dry-Spell Held-Out Error Analysis

**Scope:** Corrected chronological validation predictions, Syr Darya / Amu Darya (Aral Sea drainage) gauges only.

The analysis contains **7,125 held-out records** across **75 gauges**. Overall p10-p90 interval coverage is **77.3%**. This is below nominal 90% and should not be described as calibrated uncertainty.

**0 CA-discharge gauges with usable discharge history were excluded** because their basin does not drain to the Aral Sea: . Harirud and Murghab flow toward Turkmenistan/Iran; Balkh, Shirintagab, Chu and Talas are separate endorheic basins. They are real, modellable gauges (see `gauge_ensemble_models.pkl`), just not part of this basin's study.

## Findings

- Mean absolute error during observed dry-spell months: **3.173 m3/s**.
- Mean absolute error during normal months: **15.035 m3/s**.
- Largest held-out RMSE: **17047 (378.252 m3/s)**.
- Dry-spell months in the held-out sample: **518** of 7125 records.
- The low-flow threshold proxy marks a predicted dry month when predicted median discharge is below the gauge Q25. It is a diagnostic, not a validated dry-spell classifier, because the published dry-spell label also contains precipitation and AET conditions.

## Gauge summary

| Gauge | N | Bias (m3/s) | MAE | RMSE | Interval coverage | Dry months | Dry-state MAE | Normal MAE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 13-0.000-1M | 21 | 0.030 | 0.374 | 0.465 | 61.9% | 3 | 0.163 | 0.409 |
| 13-0.000-2M | 33 | -0.155 | 0.736 | 1.513 | 57.6% | 7 | 0.739 | 0.735 |
| 14-0.000-1M | 30 | -4.003 | 24.010 | 37.039 | 73.3% | 7 | 17.462 | 26.004 |
| 14-0.000-2M | 32 | 2.333 | 11.099 | 24.263 | 68.8% | 6 | 8.477 | 11.704 |
| 14-0.000-3M | 33 | 4.858 | 11.709 | 28.556 | 54.5% | 6 | 8.027 | 12.527 |
| 14-0.000-4M | 23 | 0.301 | 7.474 | 14.931 | 69.6% | 5 | 1.943 | 9.010 |
| 14-0.000-6M | 25 | 1.262 | 4.914 | 6.763 | 68.0% | 2 | 2.212 | 5.148 |
| 14-0.000-8M | 19 | 0.195 | 1.015 | 1.192 | 63.2% | 0 | nan | 1.015 |
| 14-1.1L0-1A | 32 | -0.114 | 6.141 | 11.427 | 68.8% | 4 | 3.440 | 6.527 |
| 14-1.R00-2A | 33 | 7.656 | 21.890 | 44.291 | 54.5% | 4 | 11.022 | 23.389 |
| 14-1.R00-5A | 27 | 3.145 | 15.993 | 28.445 | 40.7% | 3 | 2.427 | 17.689 |
| 14-5.R00-1A | 32 | 5.851 | 8.305 | 17.529 | 59.4% | 4 | 1.288 | 9.307 |
| 14-9.R00-1A | 22 | 1.418 | 2.815 | 5.919 | 72.7% | 0 | nan | 2.815 |
| 15-0.000-1M | 33 | 13.543 | 47.215 | 80.930 | 66.7% | 2 | 51.956 | 46.910 |
| 16093 | 52 | 1.127 | 2.846 | 6.034 | 75.0% | 4 | 0.312 | 3.058 |
| 16096 | 92 | 1.387 | 4.810 | 9.458 | 85.9% | 4 | 0.443 | 5.008 |
| 16100 | 28 | -7.331 | 11.343 | 16.178 | 60.7% | 1 | 0.184 | 11.756 |
| 16101 | 24 | -1.469 | 3.082 | 4.572 | 29.2% | 1 | 0.118 | 3.211 |
| 16105 | 152 | -0.266 | 1.519 | 2.397 | 94.7% | 13 | 0.585 | 1.606 |
| 16121 | 123 | -1.710 | 14.768 | 30.476 | 78.9% | 2 | 1.833 | 14.982 |
| 16124 | 90 | -1.853 | 7.834 | 13.481 | 78.9% | 0 | nan | 7.834 |
| 16127 | 116 | 8.142 | 9.389 | 12.582 | 60.3% | 11 | 5.455 | 9.801 |
| 16133 | 65 | -0.832 | 1.188 | 2.522 | 83.1% | 0 | nan | 1.188 |
| 16134 | 122 | -0.114 | 0.947 | 1.982 | 81.1% | 8 | 0.178 | 1.001 |
| 16135 | 28 | -0.971 | 1.363 | 2.924 | 28.6% | 3 | 0.122 | 1.512 |
| 16136 | 133 | 2.872 | 4.505 | 7.843 | 84.2% | 5 | 2.888 | 4.569 |
| 16137 | 54 | 2.085 | 7.829 | 12.504 | 57.4% | 4 | 2.007 | 8.294 |
| 16139 | 119 | -0.844 | 7.211 | 13.414 | 78.2% | 11 | 1.526 | 7.790 |
| 16143 | 133 | 0.367 | 1.025 | 1.765 | 78.9% | 19 | 0.289 | 1.147 |
| 16146 | 134 | -0.841 | 10.089 | 17.589 | 76.1% | 4 | 1.946 | 10.340 |
| 16151 | 101 | -1.558 | 3.411 | 6.573 | 70.3% | 4 | 0.410 | 3.535 |
| 16153 | 58 | -0.193 | 0.989 | 1.444 | 82.8% | 10 | 0.266 | 1.139 |
| 16154 | 66 | -1.631 | 6.659 | 11.156 | 75.8% | 2 | 1.591 | 6.818 |
| 16159 | 134 | 0.900 | 2.253 | 3.643 | 52.2% | 1 | 0.059 | 2.269 |
| 16161 | 80 | -0.076 | 0.540 | 0.964 | 61.3% | 3 | 0.086 | 0.558 |
| 16169 | 155 | 1.037 | 4.556 | 8.813 | 92.3% | 14 | 4.938 | 4.518 |
| 16175 | 165 | -0.117 | 0.221 | 0.401 | 60.0% | 17 | 0.066 | 0.239 |
| 16176 | 158 | -0.001 | 1.451 | 3.064 | 78.5% | 9 | 0.192 | 1.527 |
| 16193 | 151 | -0.132 | 2.189 | 4.169 | 88.1% | 7 | 0.456 | 2.273 |
| 16198 | 158 | -4.120 | 9.119 | 15.692 | 72.2% | 11 | 2.906 | 9.584 |
| 16202 | 153 | 0.080 | 1.188 | 2.084 | 87.6% | 11 | 0.197 | 1.265 |
| 16205 | 116 | 0.060 | 3.230 | 5.495 | 75.9% | 14 | 0.646 | 3.584 |
| 16223 | 151 | 0.088 | 0.707 | 1.260 | 80.8% | 18 | 0.349 | 0.756 |
| 16230 | 133 | 1.966 | 5.966 | 9.755 | 86.5% | 17 | 2.526 | 6.470 |
| 16262 | 86 | 16.784 | 37.751 | 56.604 | 76.7% | 2 | 15.821 | 38.274 |
| 16279 | 154 | -0.617 | 20.632 | 35.942 | 87.0% | 2 | 2.173 | 20.874 |
| 16290 | 154 | 5.965 | 13.091 | 20.998 | 85.7% | 8 | 3.301 | 13.627 |
| 16298 | 116 | 0.346 | 0.977 | 1.537 | 67.2% | 0 | nan | 0.977 |
| 16300 | 153 | 2.452 | 5.474 | 8.731 | 86.9% | 11 | 2.819 | 5.680 |
| 16390 | 97 | 0.443 | 1.477 | 2.434 | 78.4% | 4 | 0.666 | 1.512 |
| 16487 | 27 | -3.455 | 8.555 | 16.896 | 63.0% | 2 | 2.224 | 9.061 |
| 16510 | 150 | -0.555 | 1.589 | 2.398 | 76.0% | 4 | 0.206 | 1.627 |
| 16924 | 154 | 14.393 | 35.091 | 58.497 | 84.4% | 2 | 10.275 | 35.418 |
| 16936 | 152 | 40.011 | 85.522 | 146.023 | 73.7% | 2 | 12.925 | 86.490 |
| 16938 | 130 | 16.190 | 38.710 | 63.385 | 85.4% | 7 | 33.607 | 39.001 |
| 17045 | 44 | -59.363 | 212.821 | 371.073 | 59.1% | 2 | 40.114 | 221.045 |
| 17047 | 46 | -197.423 | 241.217 | 378.252 | 71.7% | 0 | nan | 241.217 |
| 17089 | 111 | 1.610 | 106.052 | 158.887 | 80.2% | 2 | 100.391 | 106.156 |
| 17137 | 106 | -8.310 | 44.179 | 68.555 | 83.0% | 3 | 4.603 | 45.332 |
| 17194 | 54 | 1.562 | 15.025 | 24.782 | 64.8% | 2 | 1.102 | 15.561 |
| 17202 | 99 | -2.377 | 5.422 | 10.967 | 78.8% | 4 | 1.003 | 5.608 |
| 17211 | 153 | 1.764 | 4.957 | 8.902 | 77.1% | 16 | 1.118 | 5.405 |
| 17223 | 151 | 0.342 | 1.363 | 2.274 | 84.8% | 28 | 0.415 | 1.578 |
| 17231 | 154 | 0.203 | 1.486 | 2.530 | 76.6% | 26 | 0.246 | 1.738 |
| 17236 | 153 | 0.699 | 9.181 | 13.932 | 79.1% | 21 | 5.394 | 9.784 |
| 17257 | 154 | -0.160 | 1.176 | 2.157 | 81.8% | 11 | 0.122 | 1.257 |
| 17260 | 154 | -0.285 | 1.430 | 2.685 | 84.4% | 23 | 0.264 | 1.635 |
| 17275 | 130 | 0.297 | 1.265 | 3.286 | 79.2% | 19 | 0.092 | 1.465 |
| 17279 | 151 | -0.299 | 1.869 | 2.941 | 82.8% | 16 | 0.316 | 2.053 |
| 17288 | 87 | -1.210 | 22.030 | 37.728 | 78.2% | 5 | 11.461 | 22.675 |
| 17344 | 106 | 0.028 | 1.596 | 2.521 | 84.0% | 8 | 1.044 | 1.641 |
| 17459 | 21 | -1.499 | 139.155 | 186.425 | 33.3% | 0 | nan | 139.155 |
| 17461 | 59 | 1.028 | 22.704 | 40.209 | 71.2% | 3 | 3.101 | 23.754 |
| 17462 | 26 | -1.135 | 7.216 | 11.408 | 50.0% | 0 | nan | 7.216 |
| 17464 | 154 | -0.644 | 2.868 | 5.044 | 85.1% | 4 | 0.485 | 2.931 |

## Figures

![Held-out error atlas](dry_spell_error_atlas.png)

![BasinATLAS context map](dry_spell_basin_context_map.png)

![All-gauge held-out error map](dry_spell_gauge_error_map.png)

![Gauge network inventory map](gauge_network_inventory_map.png)

The BasinATLAS map is intentionally contextual. A complete verified gauge-to-basin coordinate crosswalk is not available for all gauges, so no unsupported spatial interpolation of model error is shown. The highlighted Pskem candidate catchment retains the existing reach-assignment warning.

## Interpretation limits

- Error magnitude is in cubic metres per second and is not comparable across gauges without flow normalization.
- Dry-spell error comparisons are sensitive to the rare-event count and should be paired with event-level recall and precision.
- The current analysis diagnoses continuous discharge error; it does not establish 1-, 2-, or 3-month dry-spell forecast skill.
- Basin attributes can stratify error and explain regime differences, but they do not replace time-varying climate forcing or validated routing.
