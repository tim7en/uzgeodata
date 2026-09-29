# Catchment statistics and independent estimates

## Catchment statistics: basin 4121292070

`python qa/deep_dive/other_tabs/check_catchment_basin.py` → [result.json](result.json)

Retraces the upstream network from `catchments/index.json` and recalculates what the
Catchment statistics tab shows. All **PASS**: 89 basins (88 upstream), 11,885.5 km²
traced (HydroATLAS reports 11,884.8 km²), relief 3,674 m and circularity 0.383
reproduce exactly, and precipitation covers 100% of the catchment in every checked
month. MODIS snow cover ends in December 2024 for this catchment and is withdrawn from
trend use.

## Independent estimates against the monthly record: all basins

`python qa/deep_dive/other_tabs/check_estimate_versions.py` → [estimate-versions.json](estimate-versions.json)

**FAIL, by design until fixed.** The 72 TerraClimate-based estimates (precipitation,
actual and potential evapotranspiration, soil water, moisture and aridity indices) were
derived from TerraClimate v1.0 as Earth Engine hosts it. The Monthly tab, catchment
statistics, drought study and reports were rebased on the producer's v1.1 on
2026-09-28. Recomputing 2003–2025 normals from v1.1 for all 7,445 level-12 basins:

| Variable | Annual normal, v1.1 against the published estimate (median basin) |
|---|---:|
| Precipitation | −9.6% (November–January about −14%) |
| Actual evapotranspiration | −6.4% |
| Potential evapotranspiration | −0.1% |

This matches the release comparison in
`PUBLISHED/data/atlas/climate-continuation/v1.1-vs-v1.0.json` (area-weighted precipitation
−5.5% Syr Darya, −8.6% Amu Darya). It is a product-version difference, not an arithmetic
error, but a reader comparing the two tabs for one basin sees different January
precipitation for the same years. The portal now says so on those estimates. The fix is
to re-derive them from v1.1 with `PIPELINES/derive_regional_substitutes.py` once the
observation store holds the v1.1 rows; the check then passes.
