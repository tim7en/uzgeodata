# Basin report: scientific review and the next stage (2026-09-29)

A hydrologist reviewed a precipitation report generated for a level-12 basin and
raised four corrections and one clarification, then proposed what the atlas needs
to become decision support rather than a collection of statistics. This records
what was changed and what is planned.

## Corrections made

| Issue | What the report said | What it says now |
| --- | --- | --- |
| 1. Precipitation volume called runoff | Depth × area was labelled "Water volume", with a note about generated runoff, for every water variable. | Each volume is named for what it measures: **precipitation volume** (gross precipitation, before evapotranspiration, infiltration and storage change — not runoff), generated runoff volume, evapotranspiration volume, evaporative demand, climate water deficit. |
| 2. Trend units | A Sen slope over annual *totals* was printed in "millimetres per month per decade". | Fluxes are summed to annual totals and the slope is stated as **millimetres per year, per decade**; intensive quantities (temperatures) keep their unit per decade. The report says which (annual totals or annual means) it was fitted to. |
| 3. Uncertainty of multi-month totals | ±48.28 mm for 12 months was the sum of eight monthly p90 errors, shown like a calibrated interval. | It is labelled a **conservative bound**: the sum of held-out 90th-percentile absolute errors, not a calibrated 90% interval, because errors in neighbouring months are correlated. |
| 4. "Observed" | TerraClimate and ERA5-Land values were called observed. | They are **historical gridded data** (modelled from stations, satellites and reanalysis, not gauge readings), and later months **provisional model-derived estimates**, each with its source and version. CSV codes are `historical_gridded`, `provisional_estimate`, `no_value`. |
| 5. Two baselines | Monthly anomalies (2003–2025 record) and SPI-12 (1991–2020) appeared side by side. | Both baselines are stated separately in the report and PDF, with a note that a month can be below its 2003-based normal while its water year is near normal against 1991–2020. |

Code: `INTERFACE/reportTerms.js`, `INTERFACE/catchmentStatisticsModel.js` (`totalDefinition`),
`INTERFACE/PoiReportModal.jsx`, `INTERFACE/poiExports.js`; tests in `TESTS/test_report_terms.mjs`.

## Next stage: from statistics to decision support

The reviewer proposed three components. First steps of each are now in every basin
report under **Upstream in detail**; the rest is planned.

**Spatial attribution of upstream conditions** — *first step shipped.* For the latest
water year the gridded record holds completely, each upstream sub-basin's anomaly
against its own normal is mapped, and the level-7 ranges that pushed the catchment
wetter or drier are listed with their contribution (area share × own anomaly; the
contributions add up to the catchment anomaly exactly). *Planned:* attribution for
the current water year including provisional months, and attribution to runoff
through a calibrated hydrological model.

**Snow accumulation and melt** — *first step shipped.* For each water year, October–March
precipitation is set against the peak snowpack it built (TerraClimate v1.1 SWE), so a
wet winter that replenished snow reserves is told apart from one that fell as rain.
*Planned:* MODIS snow-cover persistence and snow-line elevation (the MODIS series needs
its growing gaps explained first), freezing-level change from ERA5, and peak timing.

**Hydrological response** — *first step shipped.* The report lists the CA-discharge
gauges inside the upstream catchment with the years their records cover, so a reader
sees what measured-flow evidence exists. *Planned:* publish the gauge series, set
seasonal runoff against precipitation and snow where records overlap, and use the
pooled dry-spell model (validated on gauges withheld from training) where no gauge
exists — so a meteorological drought can be told from an actual supply shortfall.

Code: `INTERFACE/upstreamModel.js`, `INTERFACE/UpstreamInsights.jsx`; tests in
`TESTS/test_upstream_model.mjs`.

## Second review round: assessment, snow wording, glaciers and land cover

**Basin assessment.** Right after the introductory map every report now answers five
questions in plain sentences generated from its own numbers: what happened in the last
water year; where precipitation and snow storage stand now; where the main precipitation
anomaly came from; what the seasonal forecast indicates and whether it has earned trust
(RPSS against climatology); and what can and cannot be said about river discharge. Each
answer names what it rests on — historical gridded data, provisional estimates, the
seasonal forecast, or nothing yet — and a missing figure yields "not established", never
a guess. The discharge answer always states that the report contains no measured flow
and no calibrated runoff model, so a precipitation or snow deficit is not a water-supply
deficit.

**Snowpack wording.** Winter precipitation and peak snow storage are classed separately
against the terciles of their own record (below / near / above), and the report states
both numbers explicitly — e.g. "Winter precipitation was 6% below average, while peak
modelled snow storage was 21% below average" — instead of a single "near normal" label.
The rule is printed under the table.

**Attribution map.** Titled "Contribution to the catchment-wide precipitation anomaly"
with a caveat that it is not each sub-basin's share of the change in river flow: a high
mountain sub-basin can supply far more runoff than its area share.

**Glaciers.** From the GLIMS/RGI inventory: ice area in the catchment, number of glaciers,
ice below 4,000 m and in glaciers under 0.5 km² (the most sensitive to warming), survey
years, and the share of the catchment the survey covers. One survey per glacier —
change over time is not measured. *Planned:* glacier mass change from repeat elevation
surveys (e.g. Hugonnet et al. 2021) per sub-basin.

**Land cover.** Annual 10 m land cover (Impact Observatory / Esri, 2017–2025) with the
first and last year compared and the largest class changes listed. The series covers
basins intersecting Uzbekistan only; where it covers less than a tenth of the catchment
no composition is shown. *Planned:* extend the series to the transboundary headwaters.

**Next, in order.** (1) Publish the gauge discharge series and set seasonal runoff
against precipitation and snow anomalies where records overlap. (2) A seasonal
water-availability assessment combining snow storage, glacier context, gauge response
and the SEAS5 outlook.

Code: `INTERFACE/assessmentModel.js`, `INTERFACE/BasinAssessment.jsx`,
`INTERFACE/upstreamModel.js`, `PIPELINES/build_glacier_basin_context.py`; tests in
`TESTS/test_assessment_model.mjs`.
