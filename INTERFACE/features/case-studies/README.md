# Case-study UI modules

`INTERFACE/CaseStudies.jsx` owns hash routing and lazy study loading. With no
hash, it shows the study directory without fetching large study datasets.
`INTERFACE/ChirchikStudy.jsx` owns the detailed Chirchik page. Existing deep
links and published-data paths remain compatible; browser back/forward works.

- `ObservationEvidence.jsx`: Chirchik station/discharge views.
- `StudyDirectory.jsx`: image cards, study aims and small source-derived summaries.
- `CurrentModel.jsx`: current daily-model scores, monthly/seasonal charts and downloads.
- `usePublishedData.js`: abortable fetch, revalidation and retry states.
- `StudyPortfolio.jsx`: protocols collapsed separately from results.
- `TimeSeriesChart.jsx`: shared gap-preserving lines and exact-value tables.
- `RegressionChart.jsx`: supplied regression results, paired values and axes.
- `RegionalStationStudy.jsx`: regional loading/error state, QC, spatial and
  temporal views, station selection, sources and downloads.

Keep numerical methods in `PIPELINES/hydromet`, not chart components. Never
replace missing values with zeros or regress soil class numbers. Existing
specialist Chirchik components retain their paths pending tested migration.
