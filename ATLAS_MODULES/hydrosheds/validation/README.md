# Scientific validation evidence

Before implementing an attribute, store a reviewed tolerance specification here:
attribute ID, physical unit, reference release/hash, basin sample IDs, geometry
version, absolute/relative tolerance, missing-data policy, minimum coverage and
scientific rationale. Keep measured outcomes in a distinct versioned report.

Include mountain, arid, very small, upstream/downstream and terminal basins from
both Amu Darya and Syr Darya. Test weighted aggregation and absence of duplicate
upstream contributions, not just agreement for one convenient basin.

The first executable attribute is `ele_mt_sav`; its predeclared criteria are in
`ele_mt_sav.json`. Its comparison is **not passed** (15/20 within 1 m), so it is
marked implemented, not validated or reproduced. The run package includes all
20 differences and the initial failed attempt's timing is retained in run history.

An independent rerun report must identify the operator/environment, command,
locked inputs/code, comparison results and disposition of failures. Only after
review may the registry advance to `reproduced`. Implementation alone can advance
to `implemented` when code, tests and a real pilot comparison exist. No independent
scientific rerun reports exist yet.
