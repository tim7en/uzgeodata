# Basin-scale hydroclimatic trends and water-balance diagnostics across the Amu Darya and Syr Darya: what survives multiple-testing correction in open environmental data, 2003–2024

**Draft 1 — prepared from the UzGeoData public preview.**
Status: manuscript draft for external review. All numbers are traceable to the
published release named in §Data availability; no result in this paper has yet
passed independent scientific reproduction, and the text is written so that this
statement remains true while the reproduction programme (UzGeoData roadmap,
phases *reproduction* and *edition*) is in progress.

**UzGeoData contributors**
Contact: repository issues — https://github.com/tim7en/uzgeodata/issues

---

## Abstract

1. The Amu Darya and Syr Darya support one of the world's largest irrigated
   systems, yet publicly available basin-scale environmental evidence for the
   two rivers is fragmented between published reference atlases, gridded model
   products and national water-management reports that share no common spatial
   frame. We present a reproducibility-first analysis that binds all three kinds
   of evidence to a single geography: the 7,445 level-12 HydroBASINS units of
   the two systems (965,724.8 km²), with a coarser level-7 comparison frame
   (438 units, median 1,510 km²).

2. For fourteen hydroclimatic variables we computed Mann–Kendall trends with
   continuity correction and Sen's slope on annual basin series for 2003–2024,
   applying Hamed–Rao variance inflation for serial persistence and
   Benjamini–Hochberg false-discovery control within each variable. Every test
   is published three times — uncorrected, persistence-corrected and
   family-controlled — and gated on source resolution: a basin is tested only if
   it contains at least four native source cells.

3. The headline result is a correction cascade, not a trend map. Between 239 and
   3,471 basins per variable are called significant before correction; after
   false-discovery control, five of the twelve testable variables retain zero
   significant basins region-wide, precipitation among them (smallest raw
   p-value across all 7,445 basins: 0.011). Soil moisture (46% of testable
   basins) and minimum temperature (27%) retain the largest surviving shares.
   Seven of the nine published-record variables agree across both basin scales;
   the two that do not are the ERA5-Land pair that level 12 cannot resolve at
   all (1.05 source cells per basin). A modelled precipitation-minus-
   evapotranspiration diagnostic (93.35 km³/yr) and two provider runoff products
   (153.71 and 95.19 km³/yr) disagree by more than the entire reported irrigation
   withdrawal of either river; we present this as a product-disagreement
   diagnostic, not a water balance, and identify the absence of canal
   withdrawals, return flows and reservoir routing in the gridded record as the
   structural reason a closed regional accounting is not currently computable.

4. We argue that for heavily managed basins the binding constraint on trend
   interpretation is not statistical power but the missing managed-water layer:
   withdrawals of 44.26–47.99 km³/yr (Amu Darya, 2022–2024) and 13.44–13.83
   km³/yr (Syr Darya above Shardara) are reported at reach and country level and
   cannot be joined to basin trends without inventing geography. We specify what
   records a defensible account would require and release the entire evidence
   chain — geometry, series, code, hashes and negative results — for independent
   scrutiny.

**Keywords:** Central Asia; Amu Darya; Syr Darya; HydroBASINS; trend analysis;
Mann–Kendall; false discovery rate; water balance; TerraClimate; ERA5-Land;
data provenance; ontology

---

## 1. Introduction

Trend maps for Central Asia are not scarce. What is scarce is a trend map that
publishes, beside each coloured basin, how much of the colour is method. Testing
thousands of spatial units simultaneously, on series that persist from year to
year, produces "significant" results whether or not anything is happening: the
expected share of false positives under naive per-basin testing at α = 0.05 is
five per cent of *tested* basins for every variable, and serial correlation
inflates the variance of the test statistic further. The size of this effect is
rarely reported alongside the map it distorts.

This paper reports a basin-scale study of the Amu Darya and Syr Darya designed
around that observation. Its contributions are:

- **A two-scale, three-verdict trend design.** The same trend is computed three
  ways for every basin and every variable — uncorrected, corrected for serial
  persistence (Hamed & Rao variance inflation), and controlled for false
  discovery across the whole family of tests (Benjamini–Hochberg within each
  variable) — and the whole design is repeated at two basin sizes (level 12 and
  level 7) so that scale artefacts are visible rather than absorbed.
- **Resolution gating.** A basin is tested only where the source product
  resolves it (≥ 4 native source cells). Variables whose grid cannot resolve the
  median level-12 basin are withheld entirely rather than reported at a
  resolution they do not have.
- **A managed-water boundary statement.** Gridded precipitation,
  evapotranspiration and runoff products know nothing of the canal network that
  moves 44–48 km³/yr out of the Amu Darya. We quantify what the reported
  withdrawal record would add, and why it cannot yet be joined to the basin
  frame, instead of silently stitching the two.
- **A provenance-complete release.** Every number is computed by versioned,
  reviewed code from hashed inputs over versioned geometry, with the observation
  contract, negative results and refusal logic published alongside the data.

The paper is deliberately conservative in its causal language. Nothing here
establishes a physical mechanism; associations are reported as associations, and
§7 lists the reasons — including the absence of canal withdrawals from every
gridded series — why even well-supported associations in this basin cannot be
read as drivers without the managed-water layer.

## 2. Study area and spatial frame

The study domain is the union of 7,445 level-12 HydroBASINS units covering the
Amu Darya and Syr Darya systems across national boundaries (965,724.8 km²),
delineated from HydroSHEDS hydrography. Level 12 is the finest HydroBASINS
resolution (median basin 136 km²); the comparison frame is level 7 (438 units,
median 1,510 km²), a seventeen-fold coarser aggregation that reduces the number
of simultaneous tests by the same factor.

Two properties of this frame drive the design:

1. **Basin size vs source resolution.** TerraClimate is provided at ~4.6 km
   (21.5 km²) cells — about 6 cells per median level-12 basin, resolvable but
   marginal. MODIS MYD10A1 snow cover at 500 m is comfortably resolved (~519
   cells). ERA5-Land at ~11.1 km (123.2 km²) yields 1.05 cells per median
   basin: basins and cells are effectively interchangeable, neighbouring basins
   read the same number, and any "trend" would describe the reanalysis grid, not
   the basins. ERA5-Land runoff and mean temperature are therefore withheld at
   level 12.
2. **Nested support.** Upstream (accumulated) attributes describe the catchment
   above a basin and must not be added across basins. All series used here are
   local-basin means, so the 7,445 units are non-overlapping.

All rasters were resampled onto the 15 arc-second HydroSHEDS lattice before
reduction. The stored cell-count describes that lattice, not the evidence; the
resolution gate is evaluated on *native* source cells, which is the quantity the
lattice count conceals.

## 3. Data

### 3.1 Gridded environmental record

The published monthly record holds nine dated variables for 2003–2024 (264
calendar positions per basin; runoff appends through August 2026 and is analysed
only over complete years):

| Variable | Source | Native cell | Role |
| --- | --- | --- | --- |
| Precipitation (pre) | TerraClimate | 4.6 km | flux |
| Actual evapotranspiration (aet) | TerraClimate | 4.6 km | flux |
| Potential evapotranspiration (pet) | TerraClimate | 4.6 km | flux (demand) |
| Climatic water deficit (cwd) | TerraClimate | 4.6 km | derived diagnostic |
| Palmer drought severity index (pds) | TerraClimate | 4.6 km | state index |
| Soil moisture (soil) | TerraClimate | 4.6 km | state; modelled |
| Runoff, TerraClimate (rtc) | TerraClimate | 4.6 km | flux; modelled |
| Snow-water equivalent (swe) | TerraClimate | 4.6 km | state; modelled |
| Snow cover (snw) | MODIS MYD10A1 | 500 m | state; observed |
| Vapour pressure deficit (vpd) | TerraClimate | 4.6 km | state |
| Runoff (run) | ERA5-Land | 11.1 km | flux; modelled; withheld at level 12 |
| Mean temperature (tmp) | ERA5-Land | 11.1 km | state; withheld at level 12 |
| Min/max temperature (tmn, tmx) | TerraClimate | 4.6 km | state |

TerraClimate variables derive from a climatic water-balance model with fixed
land cover; its runoff is not routed discharge, and AET inherits the model's
structure. Soil moisture is a modelled quantity, not an observation. These
provenance distinctions are carried per value and repeated wherever results are
interpreted.

### 3.2 Reported water-management record

Transcribed from the SIC ICWC Water Yearbooks (2022, 2023, 2024, section 2),
calendar-year reporting: country withdrawals and limits for the Amu Darya
(Tajikistan, Turkmenistan, Uzbekistan), the Syr Darya aggregate above the entry
to Shardara reservoir, paired reservoir inflow/release accounts (Nurek,
Tuyamuyun, Toktogul), and environmental deliveries to the Northern Aral, the Amu
Darya delta and the Large Aral via the South Karakalpak collecting drain. These
are management reports tied to reaches and administrative units; they are not
gauges, carry no uncertainty intervals, and do not share a spatial frame with
the basin record (§7.1).

### 3.3 Reference atlas and ontology

Published HydroATLAS attribute definitions (281) supply the reference context —
elevation (`ele_mt_sav`), system and headwater position from the routing graph,
and cropland, irrigated, forest and urban shares used as strata. No HydroATLAS
attribute has passed independent scientific reproduction in this project; the
strata are used as published reference values, not as validated measurements.

## 4. Methods

### 4.1 Trend tests

For each basin and variable, annual values are computed only from years with all
required months observed (flux years need 12 monthly sums; state variables use
means over observed months). A year short of a month is dropped, not scaled —
which is why basin counts differ slightly between variables (6,016–7,262 at
level 12).

- **Test:** Mann–Kendall with continuity correction.
- **Slope:** Sen's slope, the median of all pairwise slopes.
- **Serial correlation:** Hamed and Rao (1998) variance inflation, applied by
  default; the uncorrected verdict is retained beside it.
- **Multiple testing:** Benjamini–Hochberg false-discovery-rate control within
  each variable (family = all basins tested for that variable).
- **Validation:** τ and slope verified against `scipy.stats.kendalltau` and
  `theilslopes`; removing the continuity correction reproduces scipy's
  asymptotic p-value to 1e-9.

The implementation is tested by the repository's Python suite
(`TESTS/test_trends.py`, 16 tests) and its outputs are regenerable from the
published cube alone.

### 4.2 Scale comparison

The full design is run independently at level 7. A variable is *consistent* if
its surviving-signal verdict agrees across scales, *one scale only* if it is
testable at only one level, and *diverges* otherwise. Agreement across scales is
not independent confirmation: both scales read the same underlying grids, so a
bias in the source product appears identically in both. Scale comparison tests
the aggregation, not the data.

### 4.3 Water-balance diagnostics

Annual regional volumes are computed as
`Σ_basins [Σ_12 months depth (mm) × local basin area (km²) × 10⁻⁶]` over the
common complete years 2003–2024. A regional total is withheld unless every
domain basin has 12 distinct finite monthly values for that variable-year;
duplicates, incompatible units and unknown basin IDs fail the build. These
checks establish numerical support, not measurement accuracy.

### 4.4 Association with reported withdrawals

Reported withdrawals are compared with modelled diagnostics only as side-by-side
series. No regression, residual or "stress" statistic is computed between them:
the withdrawal record's spatial support (reaches, countries) does not match the
basin frame, and a constant-denominator comparison would imply a water balance
the data do not contain. (An earlier version of the public page did compute such
comparisons; it was removed — see §7.1.)

## 5. Results

### 5.1 The correction cascade

Figure 1 (published as `trend-correction-cascade.svg`) shows, for each variable,
the number of basins called significant at each stage. At level 12 (7,445
basins; 6,016–7,262 testable after the resolution and completeness gates):

| Variable | Tested basins | Significant, uncorrected | After serial correction | After FDR control |
| --- | --- | --- | --- | --- |
| soil | 6,016 | 3,470 | 3,436 | **2,789** |
| tmn | 6,016 | 2,473 | 2,467 | **1,619** |
| vpd | 6,016 | 3,033 | 2,944 | **1,401** |
| pds | 6,016 | 2,688 | 2,566 | **1,157** |
| swe | 6,016 | 1,671 | 1,593 | **193** |
| aet | 6,016 | 815 | 805 | **50** |
| snw | 7,262 | 1,220 | 1,197 | **39** |
| cwd | 6,016 | 880 | 880 | **0** |
| pet | 6,016 | 1,557 | 1,552 | **0** |
| pre | 6,016 | 239 | 236 | **0** |
| rtc | 6,016 | 1,711 | 1,695 | **0** |
| tmx | 6,016 | 2,844 | 2,596 | **0** |
| run (ERA5-Land) | withheld | — | — | — |
| tmp (ERA5-Land) | withheld | — | — | — |

**For five of the twelve testable variables — climatic water deficit, potential
evapotranspiration, precipitation, TerraClimate runoff and maximum temperature —
false-discovery control removes every significant basin in the region.** The
clearest single case is precipitation: its smallest raw p-value across all
7,445 basins is 0.011, which clears no Benjamini–Hochberg step-up threshold
anywhere in a family of six thousand tests. Serial-persistence correction alone
barely moves the counts (e.g. soil 3,470 → 3,436); the decisive correction is
the family control, which is invisible on any map that shows only per-basin
verdicts.

Two readings follow. First, for precipitation over 2003–2024, the regional data
do not support a claim of widespread significant monotonic change at the level-12
basin scale — the absence of a detectable regional precipitation trend is itself
the finding. Second, the variables that *do* survive are dominated by modelled
or state-like quantities (soil moisture, minimum temperature, vapour-pressure
deficit), and soil moisture in particular inherits TerraClimate's water-balance
structure; its 46% surviving share must be read with the source's own
limitations, not as an observed drying signal.

### 5.2 Scale comparison

At level 7 (438 units; 364–414 testable), seven of the nine published-record
variables agree with the level-12 verdict and none of the nine diverges; the two
that appear at one scale only are the ERA5-Land pair, resolvable only at level 7
(run: 2 of 364 significant; tmp: 0 of 364). Analysed at the level where it
resolves, ERA5-Land shows nothing — a result the level-12 analysis could not
have produced honestly, and the practical demonstration of the resolution gate.

Among the five TerraClimate-only indices, snow-water equivalent shows scale
sensitivity (3% of level-12 basins, 10% of level-7 basins, both retaining
significance). Its increase in surviving share at the coarser scale is
consistent with aggregation smoothing series noise, but with 22 annual values
the two estimates are not separable at conventional confidence, and the snow
record's independent, unresolved missingness problem (below) counsels against
reading either number as a trend.

### 5.3 Where the surviving signal sits

Stratified by system, headwater position, elevation band and land-cover shares,
the surviving soil-moisture and minimum-temperature signals concentrate in the
high-elevation headwater strata of both systems (published figures
`trend-strata-soil.svg`, `trend-strata-tmn.svg`). We report this as extent, not
evidential weight: a climate field is spatially correlated, adjacent basins share
signal even where cells are distinct, and false-discovery control remains valid
under this positive dependence only in the sense that the family-wise error rate
is controlled — the basin count is not a count of independent findings.

### 5.4 Modelled water fluxes vs reported withdrawals

Over the 22 common complete years and the full domain:

| Quantity | Mean (km³/yr) | Evidence type |
| --- | --- | --- |
| TerraClimate precipitation | 312.53 | gridded model/estimate |
| TerraClimate actual evapotranspiration | 219.18 | gridded model/estimate |
| TerraClimate P − AET | 93.35 | calculated difference |
| ERA5-Land runoff | 153.71 | gridded model/estimate |
| TerraClimate runoff | 95.19 | gridded model/estimate |

Reported withdrawals over 2022–2024: Amu Darya 44.26 → 47.58 → 47.99 km³/yr
(within limits of 21.8–23.6 km³/yr for Uzbekistan alone, utilised 71–81%); Syr
Darya above Shardara 13.83 → 13.65 → 13.44 km³/yr; reservoir release accounts
(Nurek, Tuyamuyun, Toktogul) close to ±1 km³/yr of inflow; environmental
deliveries of 0.82–2.60 km³/yr to the Northern Aral and 2.06–2.71 km³/yr to the
Amu Darya delta (mixed river, canal and drainage deliveries), with 0.50–0.61
km³/yr reaching the Large Aral via collector drainage that bypasses the delta.

The two runoff products disagree with each other by more than the entire reported
withdrawal of either river (58.52 km³/yr mean difference), and both disagree with
P − AET. Part of the TerraClimate agreement between P − AET and its own runoff
is shared model structure, not independent confirmation. **We therefore publish
no regional balance residual and no "stress" comparison between modelled
surplus and reported withdrawal** — the earlier public page did and was
corrected. What the comparison legitimately supports is narrower and more
useful: gridded products omit managed routing entirely, so any basin-scale
"runoff trend" downstream of the irrigated alluvium conflates climate with
whatever the canal network is doing that year. Section 7.1 quantifies the size
of that blind term.

### 5.5 Discharge modelling context

The repository's gauge-anchored experiments frame what model-based inference can
currently support. A monthly Pskem evaluation fitted on climate predictors
reports Nash–Sutcliffe efficiency 0.55 on its evaluation period but **−2.46
against a seasonal climatology benchmark** — the fitted model loses to the
seasonal reference, and the result is published as evidence about this
experiment, not as a regional forecasting claim. A separate Chirchik
snowmelt-focused study reports monthly NSE 0.7595 under a chronological split
(84 held-out months), 0.7228 daily, and negative seasonal skill (−1.0386);
different test periods make these scores mutually incomparable, which is why
every published score carries its split. These experiments are consistent with
the regional literature (Gebrechorkos et al. 2024 find no universally best
precipitation forcing; the Naryn studies show snow/glacier process fidelity and
gauge evaluation are decisive in Central Asian headwaters) and motivate §7.1:
even a perfect forcing cannot represent a river whose flow is allocated by
canal.

## 6. The role of the ontology

The analysis is held together by a typed ontology rather than by naming
convention. Its load-bearing pieces, all published:

- **Concept registry.** Variables are registered with unit, spatial support,
  time kind, temporal statistic, source and method; series identity cannot drift
  within a record. The same precipitation record supports the water atlas and
  any future agricultural atlas without being acquired twice.
- **Two spatial frames and a measured bridge.** Hydrological and administrative
  geography are parallel relationship frames; `uz:intersectsAdminArea` is the
  only measured link between them. This is what makes it *possible to state*
  precisely why the ICWC withdrawal record cannot be joined to basin trends
  today: the yearbooks describe reaches and countries, and no measured
  basin↔reach crosswalk exists in the record yet. The ontology turns the
  limitation from an unwritten assumption into a queryable absence.
- **Measured topology stays in tables; claims stay attributable.** The 7,445-basin
  routing graph lives in typed relationship tables; curated semantic claims are
  assertions with agent, confidence and provenance. Large measured relationships
  are never hand-curated, and no model proposal can promote itself into
  evidence — proposals enter a curator-reviewed queue with calibrated confidence.
- **Refusal logic.** The query layer answers coverage questions and declines
  requests it cannot support (a cube that invited summing upstream values across
  nested basins would be a trap; the library refuses and states why).

For the paper programme, the ontology is what makes the negative results durable:
"ERA5-Land cannot be tested at level 12" is a statement about registered spatial
support, not a sentence in a PDF, and it will automatically gate the same mistake
in the next study.

## 7. Limitations

### 7.1 Canal withdrawals are absent from every gridded series — the structural limitation

The Amu Darya and Syr Darya are among the most heavily managed rivers on Earth:
reported withdrawals run at 44–48 km³/yr (Amu) and 13–14 km³/yr (Syr above
Shardara), comparable in magnitude to all modelled runoff. None of this
managed water appears in the gridded record. TerraClimate and ERA5-Land
parameterise land surface and climate; they have no canal network, no offtakes,
no return-flow drains and no reservoir operation beyond what their land-surface
models simulate. Concretely, in the Amu Darya's lower alluvium a "precipitation
minus evapotranspiration" diagnostic or a "runoff" field describes what the
climate would do to an unirrigated landscape — the actual river there is the
residue of an allocation decision made hundreds of kilometres upstream.

This limitation propagates through every layer of the study:

- **Trends.** A basin-level trend in any gridded flux downstream of the
  irrigated zone cannot be attributed to climate; it is a trend in the
  *unmanaged* water balance only. Because the managed term is large and
  regime-shifted (reservoir commissioning, canal expansion, post-1990
  reallocations), it can masquerade as a trend in any product naive enough to
  include it — a reason the present study's products, which exclude it, are
  biased toward *missing* managed change rather than inventing it.
- **Balance closure.** A closed regional account requires, per boundary and
  period: border gauges (Q), canal transfers (T), reservoir storage change
  (ΔS), return flows with quality, groundwater abstraction and consumptive use.
  The yearbooks supply fragments (withdrawals, releases, deliveries) whose
  boundaries differ and which share no measured crosswalk with the basin frame.
  We therefore publish ΔS = P + Q_in + G_in + T_in − ET − Q_out − G_out − T_out
  as the *specification* of the missing account, with its unobserved terms
  explicitly null in the downloadable data.
- **Water-savings arithmetic.** Because canal seepage is a return flow, reduced
  withdrawal is not reduced consumption: improving conveyance efficiency can
  reduce downstream availability while reducing "losses". The published
  savings illustration is dimensionless and holds delivered demand fixed; the
  study draws no basin-scale savings forecast from it (FAO 2019 guidance).

The correct research response is not to approximate the missing term but to add
the record that carries it: a measured basin↔reach crosswalk (the ontology
frame exists for it), digitised offtake registers, and border-gauge series. This
is the first item in the project's roadmap for the water atlas (§8).

### 7.2 Further limitations

- **No independent reproduction.** No HydroATLAS attribute and no derived
  product has passed the project's reproduction gate (pinned inputs, declared
  tolerances, independent rerun, signed comparison). The paper's numbers are
  computationally reproducible from hashed inputs, which is a weaker property.
- **Product disagreement is unresolved.** The 58.52 km³/yr gap between runoff
  products is diagnosed, not adjudicated; gauge-anchored forcing tests (§5.5
  protocol) are the designed arbiter and are not yet run region-wide.
- **Modelled quantities.** Soil moisture, SWE and TerraClimate runoff are model
  outputs; the soil-moisture "signal" shares structure with the model that
  defines it.
- **Snow.** The MODIS snow series is withdrawn from trend use: missing months
  increase across the record and the cause is unresolved. Its 39 surviving
  basins are reported for completeness, not promoted.
- **Dependence.** Spatial correlation means surviving-basin counts measure
  extent; FDR control is valid, but effective finding counts are lower.
- **Reported withdrawals carry no uncertainty**, are management (not
  hydrological) records, and omit Afghanistan's Amu Darya abstraction entirely;
  absence from the table is not zero use.
- **ERA5-Land withholding** means two of the nine record variables have no
  level-12 result at all; the level-7 analysis shows nothing for either.

## 8. Conclusions and next steps

Across 7,445 basins and fourteen variables, the defensible regional statement
for 2003–2024 is not "X is drying" but: *after correcting for persistence and
for seven thousand simultaneous tests, most apparent trends vanish; the
survivors concentrate in modelled state variables and in headwater strata; and
the managed-water term that any water-resources reading requires is absent from
the evidential record by construction.* Publishing the cascade rather than the
map is the difference between those two sentences.

The research sequence this paper feeds is the project roadmap's:

1. **Reproduce the baseline** (in progress): pin inputs, declare tolerances and
   independently rerun attribute recipes, one family at a time — the gate every
   stratum and reference value in this paper currently sits behind.
2. **Add the managed-water record** (next): measured basin↔reach crosswalk,
   offtake and border-gauge series, so withdrawal data can be joined to basin
   geography without invented links — converting §7.1 from limitation to
   analysis.
3. **Extend the frame to vegetation** (next module): NDVI/EVI time series under
   the same trend design, for which the statistical frame here was built and
   tested ("vegetation is absent" is a registered gap, not an oversight).
4. **Freeze an atlas edition** (planned): immutable release snapshots and
   served-byte verification, so a citation to this paper's release ID preserves
   bytes, not just names.

## Data availability

All data, code and figures are public:

- Basin geometry, catalogue, monthly history and Parquet cube:
  `https://uzgeodata.uz/data/atlas/` (release `release.json`).
- Trend study results per variable: `PUBLISHED/data/trends/` in the repository;
  figures `trend-correction-cascade.svg`, `trend-strata-*.svg`, level-7 maps.
- Water-accounting tables with row-level citations:
  `https://uzgeodata.uz/water-flow.html` and its downloadable CSV/JSON.
- Analysis code: `PIPELINES/` (trend design: `build_trend_page.py`,
  `render_trend_study.py`); tests: `TESTS/test_trends.py`.
- Python client: `pip install uzgeodata`; every dataset resolves to a named
  release ID that should be cited with results.

## References (draft)

- Abatzoglou, J. T., et al. (2018). TerraClimate, a high-resolution global
  dataset of climate and water balance for 1958–2015. *Scientific Data* 5:170191.
- Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate.
  *J. R. Stat. Soc. B* 57(1), 289–300.
- FAO (2019). Guidance on realizing real water savings with crop water
  productivity interventions. FAO, Rome.
- Gebrechorkos, S. H., et al. (2024). Global-scale evaluation of precipitation
  datasets for hydrological modelling. *Scientific Data* (as cited on the
  water-flow page).
- Hall, D. K., & Riggs, G. A. MODIS/Terra and Aqua snow cover products
  (MYD10A1), NASA NSIDC DAAC.
- Hamed, K. H., & Rao, A. R. (1998). A modified Mann–Kendall trend test for
  autocorrelated data. *Journal of Hydrology* 204(1–4), 182–196.
- Lehner, B., et al. (2008). New global hydrography derived from spaceborne
  elevation data (HydroSHEDS). *EOS Transactions* 89(10), 93–94.
- Lehner, B., & Grill, G. (2013). Global river hydrography and network routing
  (HydroBASINS). *Hydrological Processes* 27(15), 2171–2186.
- Linke, S., et al. (2019). Global hydro-environmental sub-basin and river
  reach characteristics at high spatial resolution (HydroATLAS). *Scientific
  Data* 6:283.
- Mann, H. B. (1945). Nonparametric tests against trend. *Econometrica* 13(3),
  245–259.
- Muñoz-Sabater, J., et al. (2021). ERA5-Land: a state-of-the-art global
  reanalysis of land surface variables. *Earth System Science Data* 13,
  4349–4383.
- Sen, P. K. (1968). Estimates of the regression coefficient based on Kendall's
  tau. *JASA* 63(324), 1379–1389.
- SIC ICWC (2022, 2023, 2024). Water Yearbook, section 2 (calendar-year
  withdrawals, reservoir accounts, environmental deliveries). Scientific
  Information Center of the Interstate Commission for Water Coordination.
- Snow/glacier modelling for large Central Asian catchments: Naryn River
  (2023), as cited on the water-flow page.
