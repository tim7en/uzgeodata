# Pskem basin climate continuation, 2025 onward

**Status:** research case study, generated 2026-09-24. The outputs are climate
estimates for the 20 provisional Pskem level-12 basin units, not measured
reservoir water level, storage, inflow, or discharge. The existing Pskem gauge
record ends in 2017 and the gauge catchment delineation is provisional.

## Question and source boundary

Can monthly ERA5-Land extend the frozen TerraClimate v1.0 fields after their
last Earth Engine image in December 2024? The [TerraClimate Earth Engine
catalogue](https://developers.google.com/earth-engine/datasets/catalog/IDAHO_EPSCOR_TERRACLIMATE)
currently ends at 2024-12; the [ERA5-Land monthly
catalogue](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_MONTHLY_AGGR)
continues into 2026. The [TerraClimate producer](https://www.climatologylab.org/terraclimate.html)
describes a newer v1.1 driven by ERA5 and advises against mixing v1.0 and v1.1.
This experiment estimates a continuation of **v1.0** for two primary variables.
It does not extend TerraClimate's derived SWE, evapotranspiration, soil moisture,
runoff, or drought index; those require a separately validated water balance model.

## Spatial and temporal design

The fixed frame is the 20 Pskem units in the atlas run
`pskem-all281-20260909T184834061745Z`. ERA precipitation is reduced on the
same 15 arc-second analysis grid used by the atlas, with valid-cell counts in
the raw extraction. Temperature uses the existing ERA monthly basin cube.
TerraClimate precipitation and monthly minimum/maximum temperature come from
the existing basin cube. The midpoint of the two TerraClimate temperature
fields is a **midpoint of extrema**, not a true monthly mean air temperature.

For each basin and calendar month, the model learns a fixed additive temperature
offset or multiplicative precipitation factor from 2003–2018. Local parameters
are shrunk toward the Pskem-wide monthly parameter using eight pseudo-years;
precipitation factors are capped at 0.25–4. The fixed factor leaves ERA year to
year anomalies intact. This simple seasonal scaling is easier to audit than
quantile mapping with only 16 training values per calendar month. The concern
that conventional quantile mapping can alter trends is documented in the
[quantile delta mapping study](https://journals.ametsoc.org/view/journals/clim/28/17/jcli-d-14-00754.1.xml).

The complete 2019–2024 block is held out. No 2025–2026 TerraClimate value is
used, and no station observation is used to fit the basin factors. Scores compare
ERA and adjusted ERA to TerraClimate v1.0 at **basin support**. The 20 basins
share coarse ERA cells, so 1,440 basin-month pairs are not 1,440 independent
tests. These scores assess product emulation, not truth.

| 2019–2024 comparison | ERA RMSE | Adjusted RMSE | Adjusted bias |
| --- | ---: | ---: | ---: |
| Temperature midpoint, °C | 2.96 | 0.74 | +0.06 |
| Precipitation, mm/month | 55.85 | 8.36 | +1.95 |

## Station evidence and transfer test

At the Pskem meteorological site, native grid cells were sampled independently
for 2010–2024 and paired with the project's local station monthly records. Over
2019–2024, ERA temperature has −7.01 °C bias and 7.12 °C RMSE against the
station; TerraClimate's midpoint has −1.00 °C bias and 1.51 °C RMSE. ERA
precipitation has +36.33 mm/month bias and 42.78 mm/month RMSE; TerraClimate
has +0.31 mm/month bias and 20.17 mm/month RMSE. The station's identity and
relocation history have not been independently verified.

Applying the containing basin's correction to the station ERA cell lowers
temperature RMSE to **4.84 °C** and precipitation RMSE to **28.36 mm/month**.
This remains worse than TerraClimate at that point and is a stress test, not
independent spatial validation. It shows that the basin correction cannot be
presented as observed station weather. Sparse high-elevation stations also
prevent claiming accuracy across the headwaters. TerraClimate's own
[limitations](https://developers.google.com/earth-engine/datasets/catalog/IDAHO_EPSCOR_TERRACLIMATE)
include inherited temporal variation and unresolved orographic variability.

## Outputs and use

`PUBLISHED/data/case-studies/pskem-climate-continuation/` contains:

| File | Meaning |
| --- | --- |
| `continuation.csv` | 800 basin-month estimates: both variables, 20 basins, January 2025–August 2026. Each row is explicitly marked estimated. |
| `validation.csv` | Raw ERA, TerraClimate v1.0 and adjusted ERA in the held out block. |
| `coefficients.csv` | Every fixed basin and calendar-month factor or offset. |
| `era5-precipitation-grid.csv` | Reproducible ERA basin extraction and QA counts. |
| `pskem-station-product-grid.csv` | Native station-cell comparisons. |
| `report.json` | Scores, source hashes, periods, caveats and transfer test. |

The continuation is intentionally a **separate product**. The atlas's original
TerraClimate attributes and their `observed_through: 2024-12` metadata retain
their source meaning. Do not append these estimates under the original
TerraClimate attribute IDs. An operational basin monitoring view can show the
ERA source, the estimated v1.0 continuation and its validation status side by
side. A reservoir monitoring claim needs independently verified reservoir
levels/area, storage curve and inflow or outflow observations.

## Rebuild and update

```bash
# Offline, using checked-in ERA grid and atlas cube
.venv/bin/python PIPELINES/build_pskem_climate_continuation.py

# Refresh the latest ERA precipitation year and station cell extracts
.venv/bin/python PIPELINES/build_pskem_climate_continuation.py --extract-era
.venv/bin/python PIPELINES/build_pskem_climate_continuation.py --extract-station
```

The extraction commands use the configured Earth Engine project. The current
latest ERA year is refreshed on each extraction call so new monthly images are
picked up; the offline build never calls Earth Engine. If TerraClimate v1.1 is
adopted, build a separately versioned series and repeat the full validation.

The next scientific gate is spatially independent, altitude-stratified station
validation with verified locations and exposure, followed by a separately
evaluated basin water balance model and contemporaneous reservoir observations.
