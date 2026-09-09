# Case-study UI modules

`INTERFACE/CaseStudies.jsx` owns the page shell and study selection. Page URLs
and published-data paths remain compatible.

- `ObservationEvidence.jsx`: Chirchik station/discharge views.
- `StudyPortfolio.jsx`: protocols collapsed separately from results.
- `TimeSeriesChart.jsx`: shared gap-preserving lines and exact-value tables.
- `RegressionChart.jsx`: supplied regression results, paired values and axes.
- `RegionalStationStudy.jsx`: regional loading/error state, QC, spatial and
  temporal views, station selection, sources and downloads.

Keep numerical methods in `PIPELINES/hydromet`, not chart components. Never
replace missing values with zeros or regress soil class numbers. Existing
specialist Chirchik components retain their paths pending tested migration.
