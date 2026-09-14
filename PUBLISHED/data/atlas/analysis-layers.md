# The four layers

Each layer answers a different kind of question, and the ones above the store cannot
be checked against the thing they describe. So each is built around what it refuses to
say as much as what it computes.

| Layer | What it holds | State |
|---|---|---|
| 1 — Reference | 281 HydroATLAS attribute definitions across 7,445 level-12 basins | Complete |
| 2 — Observation | The append-only record: 9 dated variables 2003–2024, plus epoch and static sources | Dated series complete; ~9 of 20 intended variables |
| 3 — Derived products | Normals, anomalies, seasonal figures, trends, water balance, SPI | Complete |
| 4 — Models | A fitting harness, validated against an independent gauge | Harness complete; one validated case |

---

## Layer 2 — the observation record

Nine dated variables, every one spanning **2003–2024 at 1,965,480 rows** (7,445 basins
× 264 months): precipitation, actual and potential evapotranspiration, soil moisture,
runoff, snow cover, and minimum, mean and maximum temperature. 17,689,320 rows in all.

Each year names the run that produced it, and a ledger accumulates across runs rather
than being rewritten by the latest one. A run vouches only for the years it fetched;
the ledger above them carries the full span.

**An unfinished run does not vouch for its own output.** This is worth stating because
it was tested in earnest: 625,380 valid rows of 2003–2009 temperature sat in the store
for two days, withheld from every query, because the run that wrote them was
interrupted before it could enter `run.csv`. Nothing downstream saw a number it could
not defend, and no alarm was needed for that to hold.

## Layer 3 — derived products

`ATLAS_MODULES/core/products.py`. Nothing here is stored; each product is derived on
demand from the published record, so a correction below propagates rather than leaving
a stale derivative behind.

| Product | What it gives | What it refuses |
|---|---|---|
| `normals` | The average each calendar month brings, per basin | Reports the year count behind every value, so a normal from four years cannot pass as one from twenty |
| `anomalies` | Departure from the normal, and a standardised score | Baseline comes from the whole record, never the window examined; withheld under 10 years, and the score withheld where the baseline has no spread |
| `seasonal` | A season summed for a flux, averaged for a state | A flux total is withheld if any month is missing — a summer short of July is not a summer |
| `trend` | Least-squares slope per year | Counts missing years, flags a record thinning towards the present, and carries the variable's caution onto its own result |
| `water_balance` | Precipitation less actual evapotranspiration | Named a climatic difference, not a catchment balance: nothing routes water, accounts for storage, or closes against a gauge |
| `spi` | Standardised Precipitation Index, 1–24 month windows | A real gamma fit per basin and calendar month; zeros as a mixed distribution; withheld under 10 years |

**Why SPI is fitted and not approximated.** A z-score of accumulated rainfall is the
common shortcut and it misreads both tails, because precipitation is bounded at zero
and right-skewed. On a 22-year test record the driest quarter reads −1.11 as a gamma
fit and only −0.76 as a z-score — a real drought rendered unremarkable — while the
wettest reads 2.68 against an inflated 3.33.

Accumulation windows refuse to span a calendar gap, and a null month is never summed
as a dry one.

## Layer 4 — models

`ATLAS_MODULES/core/models.py`. A model is the first output here that is not a
measurement at all: it produces a number for a month nobody observed. The harness is
therefore mostly refusals.

- **Skill is never reported on the training period.** Overlapping windows raise; there
  is no option to ask for it.
- **Both periods must be explicit.** An open-ended window cannot be checked for overlap.
- **Fewer than 24 held-out months yields no score**, the least that distinguishes skill
  from having memorised a seasonal cycle.
- **Skill is reported against climatology**, not only against the evaluation mean.
- **Missing predictors drop the month; they are never filled.** For a catchment, a
  month missing any basin is dropped whole.
- **Basins are area-weighted**, and a basin with no area raises rather than silently
  falling out of the average.

### The validation case: the Pskem at Mullala

Gauge `uz:station/gauge-16290` (р. Пскем, с. Муллала) is a hydromet record measured
independently of everything this project produces. Walking the routing graph upstream
gives 20 basins and 2,627 km²; discharge is converted to millimetres of depth so it
stands in the same units as the fluxes predicting it. Predictors are area-weighted
precipitation, maximum temperature and snow cover — supply, melt energy, storage. Fit
on 2003–2012 (120 months), scored on 2013–2017 (59 months).

| | |
|---|---|
| Nash–Sutcliffe | **0.55** |
| Skill against climatology | **−2.46** |
| Bias | +14.0 mm/month |
| Mean absolute error | 28.0 mm/month |

**Read the second row.** An efficiency of 0.55 looks like a working model. Against the
calendar-month means of the training period — a forecast needing no model at all — it
is roughly three and a half times worse. A contemporaneous linear model on monthly
climate does not predict this river, because snowmelt discharge is governed by storage
and lag it has no access to. Published as it came out.

Reporting the efficiency alone would have presented a failed model as a successful
one, and nothing in that number would have shown it.

---

# What is still to do

Ordered by value per unit of effort.

## Layer 2 — five variables in a pass already being paid for

Reducing over basin geometry costs about the same for six bands as for one, measured
at 14.1 s against 15.8 s on a 250-basin sample. TerraClimate is already fetched for
four bands, so these ride along in the same pass rather than costing a new extraction:

| Band | Gives | Closes |
|---|---|---|
| `vpd` | Vapour pressure deficit | A concept currently registered as unavailable |
| `def` | Climate water deficit | The supply-demand gap the crude balance only approximates |
| `swe` | Snow water equivalent | Depth to stand beside snow-cover percentage, which is only extent |
| `q` | TerraClimate runoff | A second runoff source to set against ERA5's |
| `pdsi` | Palmer drought index | A published drought index beside the derived SPI |

Adding a band means extending `SOURCES` in `dated_monthly.py` and registering the
attribute; the runner and contract need no change. **Note the recipe hash moves when
that file changes, so the existing years become a second derivation rather than a
revision** — expected, and the reason the namespace count is a floor and not an
equality.

Needing genuinely new sources, in rough order of demand:

- **NDVI / EVI** (`MODIS/061/MOD13Q1`) — the most requested absent variable.
- **Land surface temperature** (`MODIS/061/MOD11A2`) — distinct from the air
  temperature already published, and routinely confused with it.
- **Dated surface water** (`JRC/GSW1_4/MonthlyHistory`) — currently a long-term
  climatology only, so no seasonal or trend question can be asked of it.

## Layer 3 — SPEI is now reachable

The registry says SPEI "would additionally need a water balance and is not offered."
That was true when written and no longer is: `pet_mm_s` is published for the full
record, so precipitation less PET gives the climatic balance SPEI is defined on. It
needs a log-logistic fit rather than SPI's gamma, and the registry entry should be
corrected when it lands.

Also worth having: percentile and return-period framing for extremes, which readers
ask for more often than a raw anomaly.

## Layer 4 — one case is not a harness

- **A second gauge.** One validated catchment shows the harness runs; it does not show
  it generalises. Other stations exist in `pskem-station-basin-links.csv`.
- **A lagged or snowmelt-aware model.** The honest next attempt at actually predicting
  the river, given that the contemporaneous one demonstrably does not.
- **Uncertainty on the skill scores.** A Nash–Sutcliffe from 59 months has a wide
  interval and none is printed, which is exactly the sort of omission this layer
  criticises elsewhere.
- **A recorded comparison of predictor sets.** Mean temperature became available again
  after the set was chosen; swapping now, with both scores known, would be choosing a
  model by its result. A second, separately recorded fit is the honest way to ask.

## Cross-cutting

- **`independently_reproduced` is still 0.** No attribute has passed independent
  scientific reproduction, and the preview says so everywhere. This is the single
  largest gap between what the platform is and what it claims to be for.
- **The store exists on one disk.** 520 MB of Parquet and 3.7 GB of checkpoints are
  not in Git and are not archived. A GitHub Release or Zenodo deposit would make the
  record survivable; the repository is the wrong place for it.
- **`integrity` CI is red** and has been for some time. It fails at collection on
  Linux (exit code 2), which does not reproduce on Windows or under a simulated clean
  checkout, so it needs the runner log to diagnose.
