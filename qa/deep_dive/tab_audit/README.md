# Screenshot basin: monthly, recent climate, drought (first pass)

**Basin:** HydroBASINS level 12 `4121292070`. The catchment morphology record reports 89 members including the selected basin and 11,885.5 km² traced, matching the screenshot's 88 upstream basins and rounded 11,886 km². Re-run with `python qa/deep_dive/tab_audit/check_screenshot_basin.py`. [Machine-readable evidence](result.json) records SHA-256 hashes for every numerical input, exact results, and limitations.

## What the numbers support

| Check | Recalculation | Finding |
|---|---:|---|
| 2025 actual evapotranspiration | 341.84587 mm annual sum from 12 basin-month values | All 12 monthly values in the monthly tab agree with the published intermediate table within 0.000044 mm, consistent with four-decimal display rounding. This is **internal parity**, not a raw grid or field-observation validation. |
| January 2026 actual evapotranspiration estimate | 22.336998 mm | Independently applying the stored basin/month intercept, slope, and ERA predictor reproduces the published estimate exactly. The record supplies a 14.795 mm river-system 90th percentile held-out absolute error, **not** a basin-specific confidence interval. |
| 2020–2025 local AET holdout | 72 months; model RMSE 13.795 mm/month; seasonal baseline RMSE 16.596 mm/month | The fitted model beats this baseline for this basin over this holdout, but residual error remains substantial. This checks the published model against its published TerraClimate target, not against field measurements. |
| Water year 2025 precipitation | 476.147 mm, October 2024–September 2025 | Superseded: the served drought record, its 1991–2020 normal, anomaly and SPI are now verified in [../drought](../drought/README.md) (−30.4%, SPI −1.78). |

## Data identity and quality

- **Monthly record:** Fourteen series, 2003–2026. For this basin, most TerraClimate v1.1 series have 276 non-null months through December 2025 and 12 null months in 2026. ERA5-Land temperature and runoff each have 284 non-null months through August 2026, then four nulls. MODIS Aqua snow cover has 264 non-null months and 24 gaps and is explicitly withdrawn from trend use. The tab calls all non-null values “observed,” although these are gridded producer estimates, with ERA5-Land a reanalysis. Retain the source and quality meaning beside the count.
- **Recent climate:** The local per-basin record has 22 series (11 variables × local/upstream), all `estimated_v1.1`, January–August 2026. It contains no `direct_v1.1` series, despite UI code supporting a direct TerraClimate legend. The comparison to 2025 direct values is therefore not present in this tab. Values use a fitted ERA-to-TerraClimate mapping; upstream runoff is generated runoff depth, not routed discharge. The upstream area changes the spatial support and must not be compared as if it were the selected polygon.
- **Drought & outlook:** *(Now verified against the served file — see [../drought](../drought/README.md).)* The tab expects `/data/atlas/drought-study/basins/4121292070.json`, which is excluded from the checkout by `.gitignore`. Its annual anomaly, SPI, PDSI, upstream runoff, and outlook cannot be checked against actual served bytes here. The drought study's method uses October–September years, TerraClimate v1.1, a 1991–2020 WMO reference, and a gamma-fit SPI; the current-year outlook additionally combines the monthly record with provisional continuation. These product boundaries should remain visible.

## Required next validation

1. Acquire and hash the exact producer TerraClimate v1.1 NetCDF files plus the geometry version used for this basin. Independently reduce at least one AET and precipitation month with fractional cell overlap; assess pixel support and source quality flags. The original NetCDF files are not available in this checkout.
2. ~~Reproduce the drought normal, anomaly and SPI against served values~~ — done in [../drought](../drought/README.md). Still open: PDSI, upstream columns and the outlook.
3. In the portal, label gridded values as estimates/reanalysis and show source, update cutoff, null coverage, validation scope, and version on each series. For the Recent climate tab, either publish the direct-v1.1 companion series or describe it explicitly as provisional 2026 estimates only.

No production or published data were changed by this audit.
