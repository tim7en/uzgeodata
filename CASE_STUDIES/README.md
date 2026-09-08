# Chirchik–Charvak case studies

Open `/case-studies.html` in the running application. The six study protocols are
authored in [chirchik-portfolio.json](chirchik-portfolio.json); their methods and
evidence gates are rendered in both the browser and the generated report.

```bash
npm run cases:build
npm run cases:figures
npm run test:cases
npm run build
```

The offline build reads the existing monthly meteorological and daily discharge
deliveries, station/basin links and level-12 routing. It writes to
`PUBLISHED/data/case-studies/`:

- `chirchik-report.md`: comprehensive methods, initial results, limitations and sources.
- `chirchik.json`: browser evidence, scores, uncertainty, protocols and provenance.
- `discharge-audit.csv`: calendar-valid raw and screened monthly flow, coverage,
  complete-month volume and held-out predictions.
- `discharge-rejected-dates.csv`: impossible calendar dates retained for review.
- `station-annual.csv`: complete-year precipitation totals and day-weighted temperature.
- `joint-climate-discharge.csv`: eligible, contemporaneous Pskem P/T/Q months.
- `pskem-candidate-catchment.geojson`: full-unit reverse network trace; exact gauge
  position and the partial outlet unit still require review.
- `chirchik.manifest.json`: input hashes, processing version and quality policy.
- `pskem-observation-evidence.png` and `.pdf`: standalone scientific figure, built separately.

The existing daily import contains 2015-02-29, an impossible date. The case-study
build quarantines it without altering the source CSV. Three additional source
flags are screened; raw-versus-screened sensitivity uses the same eligible months.
Monthly means require at least 90% daily coverage. Observed volumes require all
days, avoiding unlabelled missing-day extrapolation.

The initial runoff benchmark learns monthly climatology from 2001–2010 and tests
2011–2017. Its confidence intervals resample held-out calendar years with a fixed
seed. It is a baseline to beat, not a calibrated rainfall–runoff model. KGE uses
the 2009 definition; undefined scores are null. Bias is prediction minus observation.

## Historical product validation

An authenticated Earth Engine session is needed for:

```bash
npm run cases:forcing
npm run cases:build
npm run cases:figures
```

The extractor samples native cells at the existing station coordinates, retrieves
only variables/months for which observations exist, and records image identifiers.
ERA5 monthly temperature is converted K → °C and precipitation m → mm. CHIRPS v3
uses six pentads per month; missing source images abort the retrieval. The previous
CSV is replaced only after a complete extraction. The network retrieval has not
been verified in this environment because saved Earth Engine credentials are absent.

The build accepts `--forcing path/to/station-product-monthly.csv`. Required fields
are `station_id,period,variable,value,unit,product,spatial_support`, with `period`
as `YYYY-MM`, `spatial_support=station_grid_cell`, and units `mm` or `°C`.
Use the extractor for full coordinate/image provenance. Duplicate keys, mismatched
units and basin-mean inputs fail validation. Absent or unpaired data produce no
scores. Raw product scores appear automatically by station and season after
extraction; fitted bias correction and anomaly skill are subsequent experiments
specified in the protocols, not implemented model results.

Future work follows the evidence gates: station-elevation and independence audit;
reviewed gauge boundary; historical snow and catchment forcing; disjoint-year
forecast tests; then independently constrained glacier and reservoir analyses.
