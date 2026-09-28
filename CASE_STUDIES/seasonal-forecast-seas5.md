# Seasonal forecast: ECMWF SEAS5 against TerraClimate

**Pipeline:** `PIPELINES/seasonal_forecast_seas5.py` · **Page:** `/seasonal.html` ·
**Data:** `PUBLISHED/data/atlas/seasonal-forecast/` (`latest.json`, `forecast-<init>.json`, `skill.json`)

## What it answers

The atlas reports where each basin stands now; SEAS5 is what says anything about
the six months ahead. Monthly means of ECMWF SEAS5 (system 51) come from the
Copernicus Climate Data Store (`seasonal-monthly-single-levels`): 51 members for
the forecast and 25 for the 1993–2016 hindcasts, precipitation and 2 m temperature.

## How it is read

* **Units.** Both are reduced to the 7,445 level-12 basins by fractional overlap of
  the one-degree grid, then averaged by area into the 438 level-7 basins, the
  runoff-formation (headwater) and lowland zones of each river and the two systems.
  Level 7 is the finest unit reported: dozens of level-12 basins share one cell.
* **In TerraClimate's terms.** Each member's percentile in the pooled hindcast
  (24 years × 25 members) is mapped to the same percentile of TerraClimate v1.1 over
  the same years. This removes the model's bias in these mountains without inventing
  a relationship the hindcast does not show.
* **Windows.** The next three months after the start month, and the five-month
  accumulation season (an autumn start covers the winter whose snow is next
  summer's river).
* **Statements.** Tercile probabilities (drier / near / wetter; colder / near /
  warmer), the median and 80% range in millimetres or degrees, and the chance of a
  drought-level season: below the 16th percentile, the share SPI −1 marks.

## Comparison with TerraClimate

`skill.json` scores every start month's hindcasts against TerraClimate v1.1, each
year left out of the thresholds it is judged by: anomaly correlation, ranked
probability skill score against climatology, ROC area for a below-normal season,
and the raw model's bias against the record by calendar month. A forecast is
called skilful where RPSS > 0 and the correlation is significant at 5% (r ≥ 0.404,
n = 24); elsewhere the interface draws it grey and says to read it as the normal
range.

## Running it

```bash
# ~/.cdsapirc holds the CDS URL and personal access token; the dataset licence
# must be accepted once on the CDS website.
npm run seasonal:download -- --init 2026-09 --all-hindcasts   # first time: all 12 hindcasts
npm run seasonal:build -- --init 2026-09
python PIPELINES/seasonal_forecast_seas5.py skill
```

Monthly, after the new run is released on the 5th: `seasonal:download` and
`seasonal:build` for the new start month.

**Limits.** Precipitation and temperature only: not a forecast of river flow, which
also depends on the snow and ice already in the mountains. Skill is measured on
24 years, so a single basin's score is noisy; the zone and system scores are the
ones to lean on.

## First results (built 2026-09-28)

**Forecast from 1 September 2026, October–February.** SEAS5 is wetter than in any of
its 24 hindcast years across the region (raw October precipitation 1.84 × its own
climatology). In TerraClimate's terms: +27% in the Amu Darya lowlands and +29% in the
Syr Darya lowlands, 82–88% for the upper tercile, and a 0–2% chance of a drought-level
season against 16% in an ordinary year. In the lowlands the forecast has skill for this
start and window (RPSS 0.22 and 0.28, ROC 0.91 and 0.90), so the wet signal is worth
weight there. In the headwater zones it has none for precipitation (RPSS ≈ 0) and is
shown as the normal range. Mean temperature leans warmer, partly the warming since the
1993–2016 reference.

**Skill against TerraClimate v1.1, 1993–2016, five-month window.** Temperature is the
more predictable quantity: the Amu Darya headwaters show skill from every start month
tested (RPSS +0.03 to +0.32), and 62–94% of level-7 basins beat climatology for winter
and spring starts. Precipitation skill is patchy: present for February–April and
September starts in the lowlands and for February–April starts in the Amu headwaters,
absent for May–August starts almost everywhere (1–14% of level-7 basins).

**Raw-model bias.** SEAS5 at one degree is 2–7 °C colder than TerraClimate over the
Amu Darya headwaters and rains 1.1–1.5 times more over the Syr Darya headwaters; in
the Amu lowlands it is too wet in spring and half as wet in summer. The quantile
mapping removes these before any forecast is shown.

October was collected on 2026-09-28 and the skill table covers 11 of 12 start months;
for October starts the forecast beats climatology in 55% of level-7 basins for
five-month precipitation and 46% for temperature. June stayed queued at the CDS for
over six hours, so the stalled request was deleted and resubmitted; its skill is
unknown until it completes, and the page shows the month as pending. The downloader stores job IDs
in `WORKSPACE/derived/seas5/jobs.json`, resumes those requests on subsequent runs,
and collects completed files without submitting duplicate queued requests.

Run `npm run seasonal:download -- --init 2026-09 --all-hindcasts` again to collect
them (or add `--wait 60` for bounded polling per job). Once all 12 files are cached,
rerun the `skill` command above, then `python PIPELINES/build_study_landing.py`
to refresh the catalogue card and preview. Publish using `npm run publish:site`.
The dedicated page is also linked from the case-study catalogue at `/case-studies`.
