# The UzGeoData evidence base: site, remote, grid and modelled records for the Amu Darya and Syr Darya

**Draft 1 — data descriptor, prepared from the UzGeoData public preview.**
Status: manuscript draft for external review. Every count, path and statistic in
this article is read directly from the manifest or output file it cites in
§Data availability; none of it is retyped from memory or from an earlier
document. No record described here has passed independent scientific
reproduction (see §Technical validation and `REPRODUCIBILITY.md`); the article
is written so that this remains true while the reproduction programme is in
progress.

**UzGeoData contributors**
Contact: repository issues — https://github.com/tim7en/uzgeodata/issues

Companion paper: [paper-01, basin-scale trends](paper-01-basin-trends-amu-syr-darya.md),
which analyses a subset of the grid data described here (§2.3).

---

## Abstract

1. UzGeoData assembles evidence about the Amu Darya and Syr Darya basins from
   four structurally different sources — ground station observations, remote
   (satellite/DEM/inventory) observations, gridded climate products, and
   model outputs — and publishes them with per-record provenance rather than
   silently merging them into one time series. This descriptor documents all
   four record types as released: what was measured or computed, over what
   spatial and temporal support, with what screening, and with what it is not.
2. **Site observations**: 319 meteorological stations (123 from a national
   archive, 196 from the NSIDC-mirrored series; 303,359 station-month
   observations, elevation 29–4,169 m), 113 gauge/canal/outlet metadata sites,
   and 297 Central Asian discharge gauges imported from the CA-discharge
   research archive (Marti et al. 2023) with 244,632 observations spanning
   1910–2021. A local Pskem daily discharge record cross-validates against the
   nearest CA-discharge gauge at Pearson r = 0.998 (RMSE 0.35 m³/s, n = 555
   paired dekads) — reported as a provenance consistency check, not as
   independent hydrological validation.
3. **Remote observations**: six Earth Engine products (SRTM terrain, MODIS
   NDVI, MODIS land-surface temperature, MODIS snow-cover fraction, ERA5-Land
   monthly aggregate, OpenLandMap soil texture) extracted at station
   coordinates under explicit QA thresholds, plus three deliberately separate
   glacier records — a 25,294-glacier, 14,328 km² GLIMS-derived headwater
   outline set spanning the whole Pamir-to-Tian-Shan domain (survey dates
   averaging two decades old, assembled through GLIMS's international
   regional-centre structure rather than a modern national inventory for
   every country in the domain), a 210-point Uzbekistan-only administrative
   centre catalogue, and a Pskem-catchment elevation-zoned inventory — kept
   apart because they differ in geographic scope, provenance and geometry
   type, not just in size.
4. **Grid data**: a 2003–2024 monthly cube of thirteen variables (eleven from
   TerraClimate at ~4.6 km, two from ERA5-Land at ~11.1 km) reduced onto 7,445
   level-12 and 438 level-7 HydroBASINS units, published with a per-basin
   native-source-cell count so that any downstream use can apply its own
   resolution gate rather than trust a raster that has already been resampled
   onto a finer lattice.
5. **Modelled data**: a calibrated daily HBV-type hydrological model for the
   Pskem catchment (chronological holdout: daily NSE 0.72, monthly NSE 0.76,
   against a published stratified-split reference of 0.88/0.90 that the
   project explicitly does not treat as the honest number); a regional
   stacking ensemble predicting monthly discharge at 38 quality-screened
   CA-discharge gauges (median R² 0.857, mean R² −1.59 — the two disagree
   because a minority of gauges fit very badly, and we report both rather than
   the flattering one); and a documented, gap-audited adaptation of a 2018
   MSc thesis's four daily model structures, published as an adaptation with
   an explicit no-reproduction statement, not as a validation of the original
   thesis. No modelled output here has been promoted past the `implemented`
   or `validated` stage of the project's reproduction ladder.

**Keywords:** Central Asia; Amu Darya; Syr Darya; data descriptor; station
network; CA-discharge; MODIS; TerraClimate; ERA5-Land; HBV; provenance

---

## 1. Background and summary

UzGeoData's public preview presents a basin atlas built from published
reference values (HydroATLAS), independently computed open-data estimates, and
monthly hydroclimate records. Those derived products are described in
[paper-01](paper-01-basin-trends-amu-syr-darya.md). This descriptor documents
the layer underneath them: the observational and modelled evidence itself —
what was retrieved, from where, under what screening, and with what it does
not mean.

The project organises evidence into four kinds that are kept structurally
separate rather than merged at ingestion:

- **Site observations** — a human or an instrument at a fixed point recorded a
  value: meteorological stations, discharge gauges.
- **Remote observations** — a sensor on a satellite, or a derivative product
  built from one, describes a place without a person there: MODIS, SRTM,
  ERA5-Land point extraction, glacier inventories.
- **Grid data** — a modelled or reanalysis product delivered on a regular
  lattice and reduced onto basin geometry: the TerraClimate/ERA5-Land monthly
  cube that Section 2.3 documents and that paper-01's trend study consumes.
  wholesale.
- **Modelled data** — a fitted or calibrated model produces a number for a
  time or place nobody observed: the Pskem daily hydrological model, the
  regional discharge ensemble, the Sabitov (2018) adaptation.

This separation is not a filing convenience. Each kind fails differently.
A station can be mislocated; a satellite product can be measuring the wrong
physical quantity under a familiar name; a grid product can be asked a
question its native resolution cannot answer; a model can look skilful purely
by reproducing a seasonal cycle it was never tested against. Keeping the four
kinds apart, with the specific failure mode of each stated beside the data,
is the organising idea of both this descriptor and the `ATLAS_MODULES/core`
code it documents (`observations.py` for site/remote/grid records,
`models.py` and `products.py` for modelled and derived products).

Every subsection below follows the same template: **Provenance** (source,
licence, retrieval date), **Spatial/temporal support** (resolution, period,
coverage), **Processing & QC** (screening, exclusions, crosswalks), **Known
limitations**, **File manifest**, and **Validation evidence**.

## 2. Data records

### 2.1 Site observations

#### 2.1.1 Meteorological stations

**Provenance.** 319 stations combine two archives: 123 from a national
station catalogue (shapefile coordinates transformed from declared EPSG:4284
to WGS84) and 196 mirrored from the NSIDC archive, which carries its
source-published coordinate directly. Manifest generated 2026-09-11T03:56:50Z.

**Spatial/temporal support.** Elevation range 29–4,169 m; 61 stations above
1,500 m. Measurement mix: 181 stations report air temperature, 233
precipitation, 71 soil temperature (a station may report more than one).
303,359 station-month observations in the published archive.

**Processing & QC.** A station symbol records *how* its coordinate was
obtained: a national-archive point reached its coordinate through a name
match that one check did not contradict — not a verified identity — while an
NSIDC point carries the coordinate its source published. The two are drawn
with different placement-status symbology precisely so a user does not read a
name-matched point as equivalent evidence to a source-declared one. Of the
underlying station identity audit (§2.1.3): 86 stations carry a genuinely
unique source ID; nine zero/ambiguous-key stations were assigned deterministic
local IDs so they no longer silently overwrite a shared placeholder ID.

**Known limitations.** Name-match coordinates are plausible, not surveyed.
71-station soil-temperature coverage is far sparser than the 233-station
precipitation network and should not be treated as commensurate. Local
station identity is a bookkeeping convenience, not an assertion of ontology
membership.

**File manifest.** `PUBLISHED/data/hydroclimate/meteo-stations.geojson` (point
layer) with sidecar `meteo-stations.manifest.json` (counts, archive split,
elevation range, generation timestamp — the source of every number above).

**Validation evidence.** None beyond internal consistency counts; no
independent station-identity re-survey has been performed (§2.1.3, §3).

#### 2.1.2 Discharge gauges

**Provenance.** Two independent gauge records:

- *CA-discharge* (Marti, B., et al. 2023, "CA-discharge: geo-located discharge
  time series for mountainous rivers in Central Asia," *Scientific Data* 10,
  579; DOI 10.1038/s41597-023-02474-8; Zenodo record
  10.5281/zenodo.8147591; licence CC BY 4.0). Imported as a checksum-pinned
  compact GeoPackage (24.6 MB, MD5 `e0ba6664aaec3e0b27138abdfd4ba263`); the
  11.8 GB raw archive and 228 MB scripts archive are catalogued in the source
  manifest but not mirrored.
- A locally held Pskem daily discharge record
  (`PUBLISHED/data/hydroclimate/pskem-discharge-daily.csv`), used both as the
  target series for the Pskem HBV model (§2.4.1) and as an independent
  cross-check against the imported archive.
- 113 gauge/canal/outlet metadata sites (90 river gauges, 21 canals, two
  outlets) from a national workbook; these carry station metadata, not new
  discharge time series, and the workbook does not declare its CRS or
  vertical datum — plausible coordinates, not survey-verified ones.

**Spatial/temporal support.** CA-discharge: 297 gauge locations region-wide,
136 with an attached time series, 244,632 observations spanning 1910–2021.

**Processing & QC.** Gauge 16290 (Pskem–Mullala) is crosswalked to the local
Pskem station; 555 overlapping ten-day (dekad) periods are compared between
the two independent sources: Pearson r = 0.998, MAE 0.62 m³/s, RMSE 0.35 m³/s,
bias −0.09 m³/s (negligible) per the originally published integration record
(`CA-DISCHARGE-INTEGRATION.md`). Two glacier-thinning attributes from the
source (`gl_dmdt_km3a`, `gl_dmdtda_mma`) are excluded from every output per the
original publisher's own reliability warning.

**Known limitations.** The dekad comparison is a **provenance consistency
check between two records of the same physical river**, not independent
hydrological validation of either — the two archives are not statistically
independent measurements of a hidden truth, only two transcriptions that
happen to agree closely. Metadata-only gauge/canal/outlet sites contribute no
discharge values.

An independent recomputation directly from the published comparison CSV
(`ANALYSIS_R/site/02_discharge_gauges.R`, run against
`ca-discharge-pskem-comparison.csv`) reproduces the correlation almost exactly
(r = 0.9982) but **not** the RMSE or bias: 3.96 m³/s and −0.407 m³/s against
the stated 0.35 m³/s and −0.09 m³/s — roughly a tenfold gap on both. The
`difference_cms` column already published in that CSV agrees with the
recomputed RMSE/bias, not with the originally stated ones, so the discrepancy
sits in how the summary statistic was computed for the original integration
record, not in the underlying paired series. This is flagged here rather than
silently corrected; until it is reconciled, cite the correlation (r ≈ 0.998)
but not the RMSE/bias figures from `CA-DISCHARGE-INTEGRATION.md`.

**File manifest.** `PUBLISHED/data/research/ca-discharge-summary.json` (3.9
KB), `ca-discharge-stations.geojson` (132 KB), `ca-discharge-pskem-comparison.csv`
(16 KB), `ca-discharge-source-manifest.json` (1.2 KB, Zenodo checksums and
storage policy) — all under `PUBLISHED/data/research/`. Local discharge:
`PUBLISHED/data/hydroclimate/pskem-discharge-daily.csv`. Gauge/canal/outlet
metadata: `PUBLISHED/data/hydroclimate/hydromet-station-network.manifest.json`.

**Validation evidence.** `TESTS/test_ca_discharge.py` (3 tests): import
completeness (297 gauge rows, 244,632 observations), Pskem consistency (r =
0.998), and output structure (GeoJSON/CSV/manifest integrity).

#### 2.1.3 Station and gauge network audit

The identity and calendar-convention audit behind §2.1.1–2.1.2, run over
120,233 monthly source rows (252 identical duplicate extras collapsed to one
JSON entry; conflicting duplicates would be quarantined rather than
collapsed):

- **2,593 values are quarantined**, including two source sheets with suspect
  variable labels; negative precipitation alone does not justify swapping
  whole temperature/precipitation blocks, so raw values are retained in CSV
  rather than silently corrected.
- **Crosswalk coverage.** Exact normalised-name matches place 93,260 rows
  against 74 network identities; the remaining 26,973 rows, across 25 station
  blocks, require a manually reviewed crosswalk — fuzzy string similarity
  alone is not accepted as a match.
- **Calendar-year convention.** October–September reporting blocks use an
  *ending* year. The audit checks ±1-year alignment against the separately
  imported Tashkent/Pskem records and publishes n and MAE per site; a site is
  marked "checked" only if both seasonal halves and both variables (air
  temperature, precipitation) pass — elsewhere the convention remains
  inferred, and only checked sites enter date-matched comparisons.
- Seven gauge-height sentinel values were removed outright, not imputed.

**File manifest.** Source audit outputs under
`PUBLISHED/data/hydroclimate/` (original-value/QC tables) and
`PUBLISHED/data/case-studies/regional-station-*` (downloadable summaries);
manifests retain source hashes, asset IDs and retrieval times. Narrative:
`CASE_STUDIES/regional-station-environment.md`.

### 2.2 Remote observations

#### 2.2.1 Earth Engine products extracted at station coordinates

Six products, each extracted at the native-grid cell containing a station's
coordinate — not a basin mean and not an instrument-equivalent resample — with
per-product QA screening:

| Product | Role | Screening | Explicit non-claim |
| --- | --- | --- | --- |
| SRTM (`USGS/SRTMGL1_003`) | Terrain elevation/slope | — | Terrain elevation, not surveyed station height |
| MOD13Q1 v6.1 | NDVI | ×0.0001 scale; `SummaryQA = 0` | — |
| MOD11A2 v6.1 | Daytime land-surface temperature | ×0.02 K→°C; mandatory QA = 0, error class ≤ 2 K | Not 2-m air temperature |
| MOD10A1 v6.1 | Snow-cover fraction | Fraction of QA-valid days with NDSI ≥ 40 | Not SWE, snow depth or water storage |
| ERA5-Land monthly aggregate | Reanalysis temperature/precipitation, point-extracted | — | Reanalysis, not independent satellite observation |
| OpenLandMap v02 USDA texture | Modelled soil texture class, 0 cm | Hengl (2018), DOI 10.5281/zenodo.1475451, CC-BY-SA-4.0 | Modelled, not a field soil survey |
| MCD12Q1 v6.1 (auxiliary) | IGBP land-cover class, 2015/2020 | — | Class differences are not verified land-cover change |

**Processing & QC.** At least half of the source images in a compositing
window must pass QA; land-surface temperature additionally requires two
passing composites, and snow requires ten clear daily observations. Monthly
satellite means group composites by start date, not an exact day-weighted
calendar mean, and clear-sky sampling bias in cloud-affected months is not
corrected. All-season site summaries (used in the regional station-satellite
study, historical window 2015–2020) require three eligible years in every
calendar month before the twelve month means are equally weighted; available
years differ by site. Anomalies subtract each site's own six-year
calendar-month mean, not a 30-year climate normal, and no spatial
interpolation is applied anywhere in the pipeline.

**Known limitations.** ERA5-Land point extraction here is a *different
pipeline and use* from the basin-area-weighted ERA5-Land grid cube in §2.3:
the two must not be conflated even though they share a source. All-season
eligibility is uneven across products (86 stations for ERA5 temperature, ten
for LST, 35 for NDVI, zero for snow in the current build), so cross-product
comparisons implicitly compare different station subsets.

A seventh, smaller comparison exists alongside the six products above and is
not part of the same six-product table: `station-product-monthly.csv` holds
1,170 monthly records at three station cells comparing ERA5-Land against
CHIRPS v3 (`UCSB-CHC/CHIRPS/V3/PENTAD`, 5,566 m native scale, precipitation)
and CHIRTS-midrange (`UCSB-CHG/CHIRTS/DAILY`, 5,566 m, a monthly average of
daily (Tmin+Tmax)/2 used as a temperature proxy, record ending 2016). Its own
manifest states plainly that "station assimilation/contribution not yet
audited; no fitted bias correction" — this file was found by an independent
QC pass (`ANALYSIS_R/remote/04_remote_station_extractions.R`) rather than
originally documented here, and its three-station coverage should not be read
as regional.

**File manifest.** Extraction counts, raw extracts and screening decisions are
downloadable alongside `PUBLISHED/data/case-studies/regional-station-study.manifest.json`
and companion remote-* manifests (`remote-climate.manifest.json`,
`remote-snow-terra.manifest.json`, `remote-snow-aqua.manifest.json`,
`remote-snow-combined.manifest.json`, `remote-reservoir*.manifest.json`).

**Validation evidence.** Descriptive-only: OLS reports n, slope, r, R²; slope
confidence intervals use 500 deterministic bootstrap draws (whole years for
temporal pairs, one-degree geographic blocks requiring five blocks for site
comparisons). Dependence beyond these blocks, retrieval error and confounding
are explicitly unquantified, and these are stated as descriptive statistics,
not multiple-testing-adjusted significance claims. Worked example: elevation
vs. ERA5 temperature r ≈ −0.828 (n = 86, slope ≈ −5.67 °C/km), which the
source document explicitly declines to call a measured atmospheric lapse
rate.

#### 2.2.2 Glacier inventories

Three deliberately separate, non-interchangeable glacier records, differing
in geographic scope, national provenance and geometry type:

- **Headwater outlines** (`PUBLISHED/data/hydroclimate/glaciers-headwaters.geojson`,
  mirrored under `GEODATA/glaciers_headwaters_v1/glims-*-outlines.geojson` /
  `*-internal-rock.geojson`; manifest `glaciers-headwaters.manifest.json`):
  **25,294 glacier polygons** (20,750 in the upper Amu Darya headwater system,
  4,544 in the upper Syr Darya), sourced from GLIMS snapshot
  `GLIMS/20230607` via Earth Engine, filtered to `line_type == glac_bound`,
  deduplicated to the latest `src_date` per `glac_id`, at 30 m glacier scale /
  90 m basin reduction scale, against the SRTM DEM (`USGS/SRTMGL1_003`).
  Total outlined area 14,328.1 km² (12,412.5 km² Amu Darya, 1,915.6 km² Syr
  Darya). This is the record that actually spans the full headwater domain:
  its footprint runs from 67.6°E/34.6°N to 78.4°E/42.5°N — the Pamir through
  the Tian Shan, well beyond Uzbekistan and into the mountain terrain of
  Tajikistan and Kyrgyzstan (and touching the Afghan/Chinese border ranges) —
  though the GeoJSON itself carries no country attribute, only `system_id`,
  `river_system_id` and `hybas_id_level10`.
  **Provenance by contributing GLIMS submission**
  (`PUBLISHED/data/hydroclimate/glacier-source-attribution.csv`, 93 rows, one
  per GLIMS regional-centre submission that intersects the domain): coverage
  is dominated by a single contributor, the **Russian Academy of Sciences**
  (61 of 93 submissions, filed under the region codes "Siberian Mountains" /
  "Russian Glaciers" / "Russian and former Soviet Union glaciers" — GLIMS's
  regional centre for former-Soviet Central Asia, which includes the
  Pamir-Alay and Tian Shan), followed by **Texas A&M University** (12
  submissions, "Southwestern Asia (Pakistan + Afghanistan)" — the Hindu Kush
  portion of the upper Amu Darya headwaters), an unaffiliated **Geographical
  Institute** (10), the **University of Colorado** (3, an RGI-into-GLIMS
  merge), and single-digit contributions from ICIMOD, the Chinese Academy of
  Sciences, Nagoya University and Graz University of Technology. Survey dates
  cluster heavily around 2002 (16,764 of 25,294 glaciers, 66%), with the full
  range spanning 1994–2006 — **this is not a modern, dedicated national
  inventory for Kyrgyzstan or Tajikistan** analogous to the Uzbek workbooks
  below; it is a two-decade-old multinational compilation assembled through
  GLIMS's regional-centre structure, and any of those countries' more recent
  official glacier inventories, if published, are not yet integrated here.
- **Regional point centres** (`PUBLISHED/data/hydroclimate/regional-glaciers.geojson`;
  manifest `regional-glaciers.manifest.json`): 210 glaciers (60 Kashkadarya,
  150 Surkhandarya) digitised from two 2023 national workbooks
  (`Kashkadarya_2023.xlsx`, `Surhandarya_2023.xlsx`, SHA-256 recorded in the
  manifest) after removing one exact duplicate. Unlike the headwater outlines,
  this record **is** a dedicated national source — but it is
  **Uzbekistan-only** (both source regions are Uzbek provinces) and reports
  only 210 glaciers against the 25,294 in the GLIMS-derived set, because it
  covers two specific Uzbek border ranges rather than the whole transboundary
  headwater domain. **These are point centres of reported area, not
  outlines** — the source geometry is not delivered, and a centre-with-area
  record must never be treated as equivalent to a digitised polygon.
- A third, catchment-specific set — `pskem-glims-outlines.geojson` — supplies
  the elevation-zoned glacier fractions consumed by the Sabitov model
  adaptation (§2.4.3): 0.38% of zone 1 (2,300–3,300 m) and 12.75% of zone 2
  (above 3,300 m), computed against the same GLIMS snapshot with matching
  internal-rock polygons removed.

**Known limitations.** The three glacier products answer different questions
(regional extent-as-outline vs. Uzbekistan-only count-and-reported-area vs.
one catchment's elevation-zoned fraction) and are not substitutable; none
reports ice volume or mass balance, and the source audit explicitly rejects
glacier-area proxies as a stand-in for glacier volume (see
`REPRODUCIBILITY.md`: "glacier area is not volume"). The GLIMS headwater
outlines are the only record with genuinely regional (multi-country)
coverage, but their survey dates are two decades old on average and their
provenance is an international scientific compilation, not an official
national inventory from every country in the domain — a materially different
evidence class from the Uzbek workbook source, which this section states
explicitly rather than letting the two blend under one "glacier inventory"
label.

**File manifest.** As listed above; all under `GEODATA/glaciers_headwaters_v1/`
and `PUBLISHED/data/hydroclimate/` and `PUBLISHED/data/case-studies/`.

**Validation evidence.** Deduplication and source-hash pinning only, plus the
count/area/extent/provenance figures above, independently recomputed from the
released files (`ANALYSIS_R/remote/05_glacier_inventories.R`). No independent
glacier-extent reproduction, and no cross-check against any Kyrgyz or Tajik
national inventory, has been run.

#### 2.2.3 Infrastructure inventories (dams, water bodies)

Two satellite/database-derived inventories, joined to the HydroBASINS routing
graph rather than measured on the ground:

- **Dams** (`PUBLISHED/data/hydroclimate/dams-transboundary.geojson`; Global
  Dam Watch v1.0, CC-BY-4.0): 100 dams native to a level-12 unit of the Amu or
  Syr system, 24 named/GRanD-linked, 200 basin links, 99 reach links, 60
  water-body links (54 within the selected domain).
- **Water bodies** (`water-bodies-transboundary.geojson`; HydroLAKES v1.0):
  1,393 water bodies (23 reservoirs, 1,370 lakes) with 2,786 basin links;
  reservoir storage totals 50,241.3 million m³ across the domain's reservoirs.

**Known limitations.** These are catalogue joins to routing geometry, not
field-verified dam/reservoir operating records; reservoir storage is nameplate
capacity from the source catalogue, not observed water storage
(`REPRODUCIBILITY.md`: "reservoir capacity is not observed water storage").

### 2.3 Grid data

**Provenance.** Thirteen monthly variables, 2003–2024, from two public
gridded sources:

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
| Vapour pressure deficit (vpd) | TerraClimate | 4.6 km | state |
| Min/max temperature (tmn, tmx) | TerraClimate | 4.6 km | state |
| Runoff (run) | ERA5-Land | 11.1 km | flux; modelled; withheld at level 12 |
| Mean temperature (tmp) | ERA5-Land | 11.1 km | state; withheld at level 12 |

(Snow cover from MODIS MYD10A1 is also part of the published record but is a
remote observation, not a grid model product — see §2.2.1's MOD10A1 entry for
the parallel Terra product; the Aqua series feeds this table via
`modis-snow-headwaters-daily.manifest.json`.) This table is reproduced from
paper-01 §3.1, which is the authoritative reference for the trend study built
on it; this descriptor documents the record itself, independent of that
study's use of it.

**Spatial/temporal support.** Reduced onto 7,445 level-12 HydroBASINS units
(965,724.8 km², median basin 136 km²) and 438 level-7 units (median 1,510
km²), all resampled onto the 15 arc-second HydroSHEDS lattice before
reduction. TerraClimate cells (21.5 km²) average ~6 per median level-12 basin;
ERA5-Land cells (123.2 km²) average 1.05 — below the ≥4-native-cell threshold
the project applies before treating a basin-level value as resolved, which is
why `run` and `tmp` are withheld at level 12 downstream (§Technical
validation). The stored cell count on the resampled lattice is not the same
number as the native-source-cell count; the record keeps both so a consumer
does not have to guess which was checked.

**Processing & QC.** Values are published in the long-table schema specified
by `observations.py`/`REPRODUCIBILITY.md`: `observation_id, basin_id,
geometry_version, basin_level, attribute_id, recipe_version, mode,
spatial_support, time_kind, valid_start, valid_end, year, month, value, unit,
coverage_fraction, quality_flag, missing_reason, source_release_id, run_id,
revision, supersedes`. A missing value is stored with a `missing_reason`, not
as zero. Upstream (accumulated) and local-basin means are distinct
`spatial_support` values and must never be summed across basins — the query
layer refuses requests that would do so.

**Known limitations.** TerraClimate is a climatic water-balance model with
fixed land cover: its runoff is not routed discharge, and soil moisture is a
modelled state, not an observation. ERA5-Land `run`/`tmp` have no usable
level-12 signal (1.05 cells/basin) and are withheld there by design, not by
omission. No canal withdrawal, return flow or reservoir operation is
represented in either source (see paper-01 §7.1 for the consequence of this
for basin-scale runoff trends).

**File manifest.** `https://uzgeodata.uz/data/atlas/` (release `release.json`,
Parquet cube); derived series under `PUBLISHED/data/hydroclimate/`:
`era5-land-full-basins-monthly.{csv,manifest.json}` (level-7, full-basin,
retrieved through 2026-07 at generation), `era5-land-headwaters-monthly.*`,
`era5-land-headwater-elevation-monthly.*`, `era5-land-full-basin-anomaly.*`,
`era5-land-headwater-anomaly.*`, `headwater-elevation-bands.*` (SRTM-derived
elevation-band terrain stratification, 90 m analysis scale).

**Validation evidence.** τ and Sen's slope verified against
`scipy.stats.kendalltau`/`theilslopes` (paper-01 §4.1); resolution-gating
logic tested by `TESTS/test_trends.py` (16 tests). No HydroATLAS attribute or
derived grid product has independently passed the project's reproduction gate
(`REPRODUCIBILITY.md` §Comparison/§Independent rerun).

### 2.4 Modelled data

#### 2.4.1 Pskem daily hydrological model

**Provenance.** A temperature-index snow model with a soil store and two
linear reservoirs (HBV-type structure), calibrated by KGE objective using a
seeded random search (6,000 samples, seed 1729) followed by local refinement.
Calibrated parameters: `tt = -1.5`, `cfmax = 2.4713`, `sfcf = 1.2991`, `fc =
127.3605`, `beta = 3.3967`, `perc = 3.6996`, `k_fast = 0.05`, `k_slow =
0.0119`, `lapse = -7.472`.

**Spatial/temporal support.** Pskem catchment, daily timestep. Two evaluation
protocols are published side by side, deliberately not collapsed into one
number:

| Split | Daily NSE (n) | Monthly NSE (n) | Seasonal NSE (n) |
| --- | --- | --- | --- |
| Reference (stratified, published) | 0.8787 (2,554) | 0.9008 (84) | 0.5917 (7) |
| Candidate (chronological: train 2002–2010, test 2011–2017) | 0.7228 (2,550) | 0.7595 (84) | −1.0386 (7) |

The project's own recorded decision (`model-review.json`): *"Preserve the
published stratified reference. Foreground the stricter chronological test;
do not tune further against its exposed holdout."* — i.e. the higher,
published number is kept as the release value, but the lower, harder-to-pass
chronological number is published beside it rather than suppressed, and no
further tuning against the chronological holdout is permitted once it has
been inspected.

**Processing & QC.** Inputs: `sabitov-daily-forcing.csv`, local Pskem
observed discharge, `pskem-candidate-catchment.geojson`
(`pskem-daily-model.manifest.json`). Output `observationClass`:
`model_hindcast` — explicitly flagged as a hindcast, not an operational
forecast product.

**Known limitations.** Seasonal-window NSE is markedly worse than daily/monthly
NSE in both splits (and negative under the chronological split), meaning the
model's within-year timing skill is far less trustworthy than its
overall-fit statistics suggest; a reader citing only the headline daily/monthly
numbers would be citing the model's best face. This is one of two distinct
Pskem models in the release — the other is a predictor-driven statistical
monthly model built through the general `models.py` skill harness
(§Technical validation), reported in paper-01 §5.5 with NSE 0.55 against its
evaluation period but **−2.46 against a seasonal-climatology benchmark** — and
the two must not be conflated; this descriptor does not re-verify that second
figure independently and cites it to paper-01.

**File manifest.**
`PUBLISHED/data/case-studies/pskem-daily-model.{csv,json,manifest.json}`;
chronological-holdout run:
`PUBLISHED/data/case-studies/model-audit/chronological-20260909/pskem-daily-model.{csv,json,manifest.json}`;
review record `PUBLISHED/data/case-studies/model-review.json`; figures
`pskem-daily-model-figures.manifest.json`.

**Validation evidence.** Both splits above; no independent second-operator
rerun has yet been logged per `REPRODUCIBILITY.md` §Independent rerun.

#### 2.4.2 Regional discharge ensemble

**Provenance.** A stacking ensemble — Random Forest (200 trees, max depth 12)
+ Gradient Boosting (150 estimators, learning rate 0.1) + Ridge meta-learner
(α = 1.0) — predicting monthly discharge across CA-discharge gauges from
basin static characteristics (area, elevation, slope, glacier/permafrost/land-cover
fractions), TerraClimate climate forcing (current, 1-month-lag, 3-month and
6-month accumulations, anomalies vs. 1980–2010), an upstream meteorological
station aggregate (319-station network, distance-weighted), and cyclical
temporal encodings. Generated 2026-09-17T12:22:43Z (assembly) /
2026-09-16T18:54:05Z (case study).

**Spatial/temporal support.** The assembled feature table spans 59,516
records across 114 unique gauges; after CA-discharge grade-1 quality
filtering and a ≥10-year coverage requirement, the trained and reported model
covers **38 gauges, 6,739 monthly records** (median 152 records/gauge).
Cross-validation is spatial 5-fold, grouped by basin cluster rather than by
date, so a fold never sees a gauge it is also trained on.

**Processing & QC.** Top predictive features by importance: `basin_mean_q_m3s`
0.376, `month_cos` 0.294, `month_sin` 0.101, `basin_elevation_max_m` 0.075,
`year_normalized` 0.063, `basin_slope_pct` 0.044, `basin_area_km2` 0.020,
`basin_elevation_min_m` 0.016, `basin_elevation_m` 0.011, `basin_glacier_pct`
0.000 (glacier fraction ranks last in this feature set — read as a property of
the fitted model, not as evidence that glacier extent is hydrologically
irrelevant).

**Known limitations.**

- **Mean R² (−1.59) and median R² (0.857) diverge sharply** because a
  minority of gauges fit very badly and drag the mean far below zero; a
  results summary that reports only the median would misrepresent the
  ensemble's actual regional performance, so both are published together.
- Skill distribution across the 38 gauges: high skill (R² > 0.70) 24 gauges
  (63.2%), good (0.60–0.70) 0 gauges (0.0%), moderate (0.50–0.60) 3 gauges
  (7.9%), low (R² < 0.50) 11 gauges (28.9%) — nearly 29% of gauges are
  low-skill, and the case-study text's own stratification by glacier
  fraction reports `nan` medians for the glacial- and snow-dominated strata
  (insufficient qualifying gauges), leaving only the rain-dominated stratum
  (median R² 0.857) actually populated. An independent recomputation from the
  released per-gauge skill table (`ANALYSIS_R/modelled/10_regional_discharge_ensemble.R`)
  makes this precise rather than merely "insufficient": **all 38 trained
  gauges have `glacier_pct == 0`** — there are zero glacial- or
  snow-dominated gauges in the trained set at all, not merely too few for a
  stable median. Read together with `basin_glacier_pct`'s last-place feature
  importance above, the released model has not actually been evaluated on a
  single glacierised basin, which should be stated plainly rather than left
  implicit in an `nan`.
- The same recomputation found that `regional_discharge_predictions.csv`
  carries the model's documented primary predictors — every
  `terraclimate_*` climate-forcing column and every `upstream_*`
  station-network column — as **100% missing** (all-`NA` `logical` columns)
  in the released file, even though the case-study narrative and the feature-
  importance table above describe climate forcing and the upstream station
  network as dominant contributors to the fitted model. Either these columns
  were dropped from this particular export after training, or the export
  pipeline has a gap; either way, a reader trying to inspect *which* forcing
  values produced a given prediction cannot currently do so from this file.
- **A validation figure in the published case-study report
  (`regional_discharge_case_study.md`) states the Pskem HBV daily model's
  benchmark NSE as 0.74**, an approximate round figure distinct from the
  split-specific values in `model-review.json` (§2.4.1: 0.72 candidate /
  0.88 reference). This descriptor flags the discrepancy explicitly rather
  than silently picking one; a reader comparing the regional ensemble
  against the Pskem model should use the §2.4.1 split-specific numbers, not
  the case-study's rounded citation of them.
- Post-dam discharge is captured as regulated flow, not decomposed into
  natural vs. managed components — the same managed-water absence documented
  structurally for the grid record in paper-01 §7.1 applies here too, since
  none of the predictors carries canal or reservoir-operation information.

**File manifest.** `PUBLISHED/data/case-studies/regional_discharge_data.csv`
(assembled features), `regional_discharge_predictions.csv`,
`regional_discharge_gauge_skill.csv`, `regional_discharge_skill_map.geojson`,
`regional_discharge_metadata.json`, narrative report
`regional_discharge_case_study.md`. Plan document (design, not results):
`CASE_STUDIES/regional-discharge-study-plan.md`.

**Validation evidence.** Spatial 5-fold cross-validation only; no independent
second-operator rerun logged.

#### 2.4.3 Sabitov (2018) thesis adaptation

**Provenance.** An adaptation of four daily hydrological model structures
from a 76-page MSc thesis (Sabitov, T., 2018, `storage/Sabitov_Master_ERE_2018.pdf`,
read in full for the review). This is explicitly **an adaptation, not a
reproduction**: the original thesis's own reported skill (Table 2-4: daily
NSE 0.70/0.23/0.76/0.29, monthly NSE 0.90/0.24/0.77/0.69 for Models 1–4) is
transcribed for reference only — "without original forcing and code, an exact
numerical reproduction cannot be asserted," and the thesis's Model 1 achieves
its fit with zero evapotranspiration, which this project does not adopt as an
acceptable calibration strategy.

**Spatial/temporal support.** Real daily ERA5-Land forcing, 2000–2017 (6,575
rows), three elevation zones (below 2,300 m, 2,300–3,300 m, above 3,300 m;
areas 709.9, 1,199.5 and 720.9 km² respectively), glacier fractions from the
Pskem-dated GLIMS inventory (0% / 0.38% / 12.75% by zone).

**Processing & QC.** A method-by-method gap matrix records, per component
(daily forcing, four structural models, elevation zones and lapse rates,
independent snow/soil/groundwater stores, antecedent-moisture SCS runoff,
Hamon PET, glacier melt, calibration protocol, flow-duration analysis, monthly
trends, climate-stress tests, satellite process checks, land-cover confusion
matrix, spatial curve numbers, tributary mass balance, gauge/ice-thickness
verification), one of five explicit statuses: Implemented, Adapted, Awaiting
reference labels/evidence, or Unresolved. Nothing is marked done that has not
been executed against real data.

**Known limitations.** Curve numbers (CN 50/90) and glacier water-equivalent
scenarios (15/30/60 m) remain thesis assumptions carried forward with
sensitivity analysis, not independently observed values. Land-cover accuracy
and tributary mass-balance checks are explicitly unresolved pending reference
labels and simultaneous discharge/meteorology data that were not supplied
with the thesis. Discharge record ends 2017; no post-2017 verification.

An independent recomputation of daily NSE from the released predictions
(`ANALYSIS_R/modelled/11_sabitov_adaptation.R`, `sabitov-daily-predictions.csv`)
against the thesis's own Table 2-4 values shows the four models do not
diverge from the thesis uniformly:

| Model | This adaptation's NSE | Thesis Table 2-4 NSE |
| --- | --- | --- |
| m1 | 0.7625 | 0.70 |
| m2 | 0.8356 | 0.23 |
| m3 | 0.7767 | 0.76 |
| m4 | 0.8357 | 0.29 |

m1 and m3 land close to the thesis figures; m2 and m4 score far higher in
this adaptation than the thesis reports for the same model numbers. This is
consistent with — and sharpens — the no-reproduction statement above: the two
implementations are not simply offset by a constant amount, so a reader
cannot treat "close on m1/m3" as evidence that m2/m4 must also be close. Given
the thesis's own irregularities already noted (Model 1's zero-ET calibration;
undisclosed forcing/code), this divergence is presented as a fact about the
comparison, not as a claim that either implementation's m2/m4 skill is wrong.

**File manifest.** `PUBLISHED/data/case-studies/sabitov-*` (daily
forcing/predictions, flow-duration, monthly trends, climate scenarios, process
checks, method-gap matrix, `sabitov-2018-review.md`,
`sabitov-inputs.manifest.json`, `sabitov-artifacts.manifest.json`).

**Validation evidence.** Held-out MODIS snow and MOD16 ET process checks
against different spatial supports (`sabitov-snow-process-check.csv`,
`sabitov-et-process-check.csv`), explicitly not independent field truth.

## 3. Technical validation

| Record | Consistency evidence | Independent reproduction status |
| --- | --- | --- |
| Meteorological stations (§2.1.1) | Internal count/placement audit only | Not attempted |
| Discharge gauges (§2.1.2) | CA-discharge ↔ Pskem: r = 0.9982 (independently reproduced); RMSE/bias not reproduced (§2.1.2) | Provenance check only; not independent validation |
| Station/gauge crosswalk (§2.1.3) | 93,260/120,233 rows exact-matched; calendar-year audit with published n/MAE | 26,973 rows await reviewed crosswalk |
| Remote products (§2.2.1) | Descriptive OLS with blocked bootstrap CIs | Not a significance-tested reproduction |
| Glacier inventories (§2.2.2) | Counts/area/extent/provenance independently reproduced from released files | No cross-check against any national Kyrgyz/Tajik inventory |
| Grid cube (§2.3) | τ/slope match `scipy` to 1e-9; resolution gate tested (16 tests) | No HydroATLAS/grid attribute has passed `REPRODUCIBILITY.md` §5–7 |
| Pskem HBV model (§2.4.1) | Two published splits, reference vs. chronological, independently reproduced | No second-operator rerun logged |
| Regional discharge ensemble (§2.4.2) | Spatial 5-fold CV; median/mean skill reproduced; predictor-column and glacier-stratum gaps found (§2.4.2) | Internal-discrepancy flagged; no rerun logged |
| Sabitov adaptation (§2.4.3) | Gap matrix per component; daily NSE independently recomputed for all 4 models (§2.4.3) | Explicitly not a reproduction of the original thesis |

No dataset in this release has passed stage 6 (independent rerun) or stage 7
(immutable snapshot manifest) of the `REPRODUCIBILITY.md` ladder
(`specified → implemented → validated → reproduced → released`). Where this
descriptor states a number, it is reading a published, checksummed file; it is
not asserting that the number is correct in an absolute sense.

An independent R-language audit layer (`ANALYSIS_R/`, one script per dataset,
`Rscript ANALYSIS_R/run_all.R`) recomputes every count and statistic this
descriptor states directly from the released files and reports PASS/MISMATCH
rather than assuming agreement. Most recomputed values matched exactly; the
four cases that did not (CA-discharge RMSE/bias, the undocumented
CHIRPS/CHIRTS station comparison, the regional ensemble's zero-glacier
training set and missing predictor columns, and the Sabitov m2/m4 divergence)
are documented in their respective subsections above and in
`ANALYSIS_R/README.md`.

## 4. Usage notes

- **Units and support are per-record, not global.** A value's `spatial_support`
  (local-basin vs. upstream-accumulated) and `time_kind` (flux vs. state) must
  be read from its own record; summing across nested basins or across a flux
  and a state is a category error the query layer refuses, and any external
  reuse should apply the same rule.
- **A missing value is not a zero.** Every grid, model and derived-product
  record stores a `missing_reason` (or equivalent QC flag) rather than
  imputing; treat an absent value as absent.
- **Reanalysis is not satellite observation, and terrain elevation is not
  surveyed station height.** These distinctions (§2.2.1, §2.3) are carried in
  the source table beside every affected variable and are restated here
  because they are easy to lose in a downstream join.
- **Point centres are not outlines, and reported glacier area is not glacier
  volume** (§2.2.2). Do not substitute the 210-centre, Uzbekistan-only
  inventory for the 25,294-glacier, whole-domain GLIMS-derived outline set or
  vice versa — they differ in geographic scope and provenance, not just
  geometry type, and the GLIMS set's ~2002-centred survey dates should not be
  read as current.
- **Modelled ≠ observed, everywhere.** TerraClimate soil moisture/runoff/SWE,
  the Pskem HBV hindcast, the regional discharge ensemble and the Sabitov
  adaptation are all model outputs; none is a measurement, and none should be
  cited as one.
- **Snow is withdrawn from trend use** pending investigation of increasing
  missing months across the MODIS snow record (`DATA-LICENSING.md`); it is
  published here for completeness only.
- **Report both the median and the mean when quoting the regional discharge
  ensemble's skill** (§2.4.2) — they diverge by more than two full units of
  R² and citing only the median misrepresents regional performance.
- **The Pskem HBV benchmark number differs between two published documents**
  (§2.4.2); use the split-specific values in `model-review.json`, not the
  rounded citation in the discharge case study.

## 5. Data availability

All data, code and manifests are public:

- **Site observations:**
  `PUBLISHED/data/hydroclimate/meteo-stations.{geojson,manifest.json}`;
  `PUBLISHED/data/hydroclimate/pskem-discharge-daily.csv`;
  `PUBLISHED/data/hydroclimate/hydromet-station-network.manifest.json`;
  `PUBLISHED/data/research/ca-discharge-*`; audit narrative
  `CASE_STUDIES/regional-station-environment.md`.
- **Remote observations:**
  `PUBLISHED/data/case-studies/regional-station-study.manifest.json` and
  companion `remote-*` manifests; `PUBLISHED/data/case-studies/station-product-monthly.{csv,manifest.json}`
  (CHIRPS/CHIRTS/ERA5-Land station comparison);
  `GEODATA/glaciers_headwaters_v1/glims-*`;
  `PUBLISHED/data/hydroclimate/glaciers-headwaters.{geojson,manifest.json}`;
  `PUBLISHED/data/hydroclimate/glacier-source-attribution.csv` (per-submission
  GLIMS provenance); `PUBLISHED/data/hydroclimate/regional-glaciers.{geojson,manifest.json}`;
  `PUBLISHED/data/case-studies/pskem-glims-outlines.geojson`;
  `PUBLISHED/data/hydroclimate/dams-transboundary.*`,
  `water-bodies-transboundary.*`.
- **Grid data:** `https://uzgeodata.uz/data/atlas/` (release `release.json`,
  Parquet cube); `PUBLISHED/data/hydroclimate/era5-land-*`,
  `headwater-elevation-bands.*`.
- **Modelled data:**
  `PUBLISHED/data/case-studies/pskem-daily-model.*` and
  `model-audit/chronological-20260909/`, `model-review.json`;
  `PUBLISHED/data/case-studies/regional_discharge_*`;
  `PUBLISHED/data/case-studies/sabitov-*`.
- **Licensing:** third-party sources retain their original terms
  (`DATA-LICENSING.md`); CA-discharge is CC BY 4.0, OpenLandMap texture is
  CC-BY-SA-4.0, Global Dam Watch is CC-BY-4.0. No blanket licence is granted
  over the combined dataset or the repository's code.
- **Citation:** `CITATION.cff`; record the basin ID or gauge/station ID,
  source release, method/recipe version, repository commit and access date
  alongside any analysis built on this release.
- Python client: `pip install uzgeodata`.

## 6. Code availability

- Ontology and reproduction contract: `ATLAS_MODULES/core/observations.py`,
  `REPRODUCIBILITY.md`.
- Derived-product engine (normals, anomalies, trends, water balance):
  `ATLAS_MODULES/core/products.py`.
- Model-fitting and skill harness: `ATLAS_MODULES/core/models.py`.
- Build pipelines: `PIPELINES/build_regional_discharge_model.py`,
  `train_discharge_ensemble.py`, `analyse_regional_discharge.py`,
  `build_pskem_daily_model.py`, `extract_regional_monthly.py`,
  `build_regional_station_study.py`.
- Tests: `TESTS/test_ca_discharge.py`, `TESTS/test_trends.py`, and the
  project's observation-store acceptance suite.
- Independent QC audit layer (recomputes this descriptor's counts/statistics
  directly from the released files; see §3): `ANALYSIS_R/` (one script per
  dataset under `site/`, `remote/`, `grid/`, `modelled/`; `run_all.R` runs
  all of them; `README.md` lists what each script checks and what it found).

## References

- Abatzoglou, J. T., et al. (2018). TerraClimate, a high-resolution global
  dataset of climate and water balance for 1958–2015. *Scientific Data*
  5:170191.
- GLIMS Consortium (2005, updated 2023). Global Land Ice Measurements from
  Space glacier database. National Snow and Ice Data Center. Snapshot
  `GLIMS/20230607` used here; submitting analysts and regional centres for
  the Central Asian domain are recorded per-record in
  `glacier-source-attribution.csv` (§2.2.2).
- Hall, D. K., & Riggs, G. A. MODIS/Terra and Aqua snow cover products
  (MOD10A1/MYD10A1), NASA NSIDC DAAC.
- Hengl, T. (2018). Soil texture classes (USDA system) for 6 soil depths
  (predicted with random forest). Zenodo. DOI 10.5281/zenodo.1475451.
- Lehner, B., et al. (2008). HydroSHEDS. *EOS Transactions* 89(10), 93–94.
- Lehner, B., & Grill, G. (2013). HydroBASINS. *Hydrological Processes*
  27(15), 2171–2186.
- Marti, B., Siegfried, T., Yakovlev, A., Zhumabaev, A., Karger, D., Wakil,
  A., & Ragettli, S. (2023). CA-discharge: geo-located discharge time series
  for mountainous rivers in Central Asia. *Scientific Data* 10, 579. DOI
  10.1038/s41597-023-02474-8.
- Muñoz-Sabater, J., et al. (2021). ERA5-Land: a state-of-the-art global
  reanalysis of land surface variables. *Earth System Science Data* 13,
  4349–4383.
- Sabitov, T. (2018). *Master's thesis, Environment and Resource Economics*
  (internal document; not independently reproduced by this project).
- UzGeoData contributors (2026). Basin-scale hydroclimatic trends and
  water-balance diagnostics across the Amu Darya and Syr Darya. UzGeoData
  paper-01 (this repository).
