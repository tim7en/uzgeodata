# Layers 3 and 4: derived products, and models

The store below these layers holds observations. An observation can be checked against
the thing it measured. Everything on this page cannot, so each layer is built around
what it refuses to say rather than around what it computes.

## Layer 3 — derived products

`ATLAS_MODULES/core/products.py`. Nothing here is stored; each product is derived on
demand from the published record, so a correction below propagates rather than leaving
a stale derivative behind.

| Product | What it gives | What it refuses |
|---|---|---|
| `normals` | The average each calendar month brings, per basin | Reports the year count behind every value, so a normal from four years cannot pass as one from twenty |
| `anomalies` | Departure from the normal, and a standardised score | Baseline comes from the whole record, never the window examined; withheld under 10 years, and the score is withheld where the baseline has no spread |
| `seasonal` | A season summed for a flux, averaged for a state | A flux total is withheld if any month of the season is missing — a summer short of July is not a summer |
| `trend` | Least-squares slope per year | Counts missing years, flags a record that thins towards the present, and carries the variable's caution onto its own result |
| `water_balance` | Precipitation less actual evapotranspiration | Named a climatic difference, not a catchment balance: nothing routes water, accounts for storage, or closes against a gauge |
| `spi` | Standardised Precipitation Index, 1–24 month windows | A true gamma fit per basin and calendar month, not a z-score; zeros handled as a mixed distribution; withheld under 10 years |

**Why SPI is fitted and not approximated.** A z-score of accumulated rainfall is the
common shortcut and it misreads both tails, because precipitation is bounded at zero
and right-skewed. On a 22-year test record the driest quarter reads −1.11 as a gamma
fit and only −0.76 as a z-score — a real drought rendered unremarkable — while the
wettest reads 2.68 against an inflated 3.33. Both directions are covered by tests.

Accumulation windows refuse to span a calendar gap, and a null month is never summed as
a dry one.

## Layer 4 — models

`ATLAS_MODULES/core/models.py`. A model is the first output here that is not a
measurement at all: it produces a number for a month nobody observed. The harness is
therefore mostly refusals.

- **Skill is never reported on the training period.** Overlapping train and evaluate
  windows raise; there is no option to ask for it.
- **Both periods must be explicit.** An open-ended window cannot be checked for overlap.
- **Fewer than 24 held-out months yields no score**, the least that distinguishes skill
  from having memorised a seasonal cycle.
- **Skill is reported against climatology**, not only against the evaluation mean. This
  is the number that matters and it is the harder test.
- **Missing predictors drop the month; they are never filled.** For a catchment, a month
  missing any basin is dropped whole — a mean over the area that happened to report is
  not a catchment mean.
- **Basins are area-weighted**, and a basin with no area raises rather than silently
  falling out of the average.

### The validation case: the Pskem at Mullala

`PIPELINES/validate_pskem_model.py`, published at `models/pskem-discharge.json`.

Gauge `uz:station/gauge-16290` (р. Пскем, с. Муллала) is a hydromet record measured
independently of everything this project produces. Walking the level-12 routing graph
upstream from its basin gives 20 basins and 2,627 km²; monthly discharge is converted to
millimetres of depth over that area so it stands in the same units as the fluxes
predicting it. Predictors are area-weighted precipitation, maximum temperature and snow
cover — supply, melt energy, and storage. Fit on 2003–2012 (120 months), scored on
2013–2017 (59 months, one rejected because the source records a 29-day February in a
non-leap year).

| | |
|---|---|
| Nash–Sutcliffe | **0.55** |
| Skill against climatology | **−2.46** |
| Bias | +14.0 mm/month |
| Mean absolute error | 28.0 mm/month |

**Read the second row, not the first.** An efficiency of 0.55 looks like a working
model. Against the calendar-month means of the training period — a forecast needing no
model at all — it is roughly three and a half times worse. A contemporaneous linear
model on monthly climate does not predict this river, because snowmelt discharge is
governed by storage and lag it has no access to. That is the result, and it is published
as it came out.

This is what the layer is for. Reporting the efficiency alone would have presented a
failed model as a successful one, and nothing in the number itself would have shown it.

### A coverage gap this exposed

The first predictor set used ERA5 mean temperature and the harness dropped 84 of 120
training months. `uzgeodata.dated.v1.tmp_dc_s` begins in 2010; the other eight dated
variables reach back to 2003. The registry now declares that span and carries a caution
on the variable. The predictor set was changed for coverage, before the second score was
seen, and the split never moved.

## What is still missing

Layer 2 publishes 9 of roughly 20 intended variables — no NDVI, land surface
temperature, vapour pressure deficit, or dated surface water. Layer 4 has one validated
case; a second gauge would test whether the harness generalises, and a lagged or
snowmelt-aware model would be the honest next attempt at actually predicting the river.
