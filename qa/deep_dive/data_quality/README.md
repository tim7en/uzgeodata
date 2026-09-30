# Data quality and visibility review (2026-09-30)

Two layers: a full-coverage screen of every published monthly value, and a browser pass over
the public portal checking what a reader is told about those values.

## 1. Monthly record sweep

`python qa/deep_dive/data_quality/sweep_monthly_record.py` → [sweep.json](sweep.json)

Every level-12 basin (7,445) × every month 2003–2026 × all 14 served series, about 30 million
values, read from the catchment matrices the portal serves.

**What holds everywhere**

| Test | Result |
|---|---|
| Coverage of TerraClimate v1.1 (11 series) | 100% of basins, every month to 2025-12; no gap |
| Coverage of ERA5-Land runoff and temperature | 100%, every month to 2026-08 |
| Physical bounds (e.g. precipitation 0–1,500 mm/month, VPD 0–8 kPa, snow cover 0–100%) | No value outside, except one runoff month (below) |
| TerraClimate minimum above maximum temperature | 0 cases |
| Actual above potential evapotranspiration | 0 cases |
| Long-term AET above precipitation (would need added water) | 0 basins; highest ratio 0.96 |
| A series stuck at one non-zero value for 24+ months | 0, except 200 basins of TerraClimate soil moisture held at a constant store — plausible for the model, not investigated further |

**Findings**

1. **Glacier snow carried over for years (TerraClimate SWE).** 18 glaciated basins (3,333 km²)
   never melt out by September; they hold 2–9 m of modelled snow water equivalent, because the
   snow model has no glaciers. The store occasionally releases at once: basin 4120495490 lost
   3.2 m in July 2022, producing the record's one runoff value above 1,500 mm/month (1,659 mm).
   Downstream, carry-over is 17–18% of mean peak SWE for the large river outlets but changes their
   water-year 2025 anomaly by only 0.2 points (−17.3% vs −17.1%). It exceeds a quarter of peak SWE
   in 151 of 5,857 snowy catchments, and moves the 2025 anomaly by more than 10 points in 65 —
   mostly small glaciated headwaters. **Changed:** the basin report measures carry-over and says so
   where it exceeds 25%.
2. **Two runoff products disagree about twofold.** ERA5-Land runoff averages 152 mm/yr, TerraClimate
   72 mm/yr over the same basins; 6,125 of 7,357 basins differ by more than 2×, and in 902 basins
   ERA5-Land runoff exceeds TerraClimate precipitation. Neither has been compared with gauges here.
   Catchment statistics named both "Generated runoff volume". **Changed:** named by product, with
   the disagreement stated.
3. **Temperature products differ by elevation support.** ERA5-Land mean temperature is on average
   1.0 °C below the TerraClimate (min+max)/2 of the same basin-month (5–95%: −6.8 to +2.2 °C); 1,356
   basins carry a steady offset above 3 °C. Two products, not an error, but the Monthly tab shows
   both without saying they come from different models. **Changed:** labels name the product.
4. **Three series did not say how far they were extracted.** ERA5-Land runoff and temperature (to
   2026-08) and MODIS snow cover (to 2024-12) had no `extracted_through`, so months never fetched
   were counted as missing — MODIS snow showed "264 of 288 months" as if 24 were gaps.
   **Changed:** `PIPELINES/declare_extraction_ends.py` declares the end from the data (the last
   month any basin has a value); the Monthly tab now shows "ERA5-Land through Aug 2026".
5. **MODIS snow cover** has 94 months below 99% basin coverage, concentrated in summers 2006–2009
   onward, and is already withdrawn from trend use; winter snow cover and SWE disagree in 544
   (no cover, SWE > 50 mm) and 393 (full cover, no SWE) of 490,951 basin-months.
6. **2025 stands out in several TerraClimate series** (largest year-on-year step in the record for
   precipitation, AET, PET, deficit, VPD and maximum temperature, each about 3 standard deviations).
   ERA5-Land, a separate product, agrees: 2025 is its warmest year of 2003–2025 too (regional mean
   +1.15 °C over 2024, against +1.56 °C in TerraClimate maximum temperature), and its runoff is the
   second lowest. So it is read as climate — the documented 2025 drought and heat — not a product
   break; but 2025 is also the first
   year of the producer's v1.1 annual release, and a year-2026 update should be checked for
   revisions.

The spike screen (robust z > 10 against the same calendar month) fires mostly where a basin's
median is zero — dry-season precipitation in the lowlands, snow in marginal months — and is not a
finding by itself.

## 2. Portal browser pass

`python qa/deep_dive/data_quality/browse_portal.py [base-url] [--basin-only]` → [browse.json](browse.json)

30 pages at desktop (1366 px) and phone (390 px) width against the live site, then basin
4121292070 opened through the finder on a phone and each of its tabs clicked.

| Check | Result |
|---|---|
| Page status, JavaScript errors, failed or HTML-instead-of-data requests | None, apart from the four `/agents` and `/admin` loads below |
| Leaked programming values (NaN, undefined, [object Object]) | None anywhere |
| Basin window: 7 tabs opened in turn | Every tab loaded; no console error, failed request or error message |
| `/agents` and `/admin` on the public site | Each logged a 404 by asking for the local operator API. **Changed:** they ask only on localhost (`INTERFACE/localServer.js`). |
| Phone width: page scrolls sideways | 8 pages — reservoir monitoring 390 px, hydrography 385, catalogue 274, review 164, trends 148, examples 56, relationships 40, dry spells 12. Causes: tables without a scroll container, header navigation that did not wrap, a wide button, a code block, and a long translated heading. **Changed:** all eight measure 0 px. |

**Not fixed — machine translation changes meaning.** The portal opens in Russian through Google
Translate. The basin tabs read "Прогноз погоды: снег" ("weather forecast: snow") for *Snow
forecast*, which is a seasonal river-flow forecast from snow storage, and "Ежемесячный отчет"
("monthly report") for *Monthly record*. Scientific terms need a reviewed Russian (and Uzbek)
glossary applied by the site, with those terms marked `translate="no"` for the machine
translator, rather than translation of the English on the fly.

## 3. Measured river flow against catchment precipitation (gap 1)

`python PIPELINES/build_gauge_precipitation_response.py` →
`PUBLISHED/data/research/gauge-precipitation-response.json`

CA-discharge records (Marti et al. 2023, CC BY 4.0) against TerraClimate v1.1 precipitation over
each gauge's own delineated catchment, water year by water year (1992–2021 overlap). 45 gauges
have 10+ paired years; 35 lie outside the Amu/Syr frame and 53 have too few complete years.

| Result | Value |
|---|---|
| Correlation of water-year flow with catchment precipitation | median r = 0.74; 31 gauges r ≥ 0.6; 6 below 0.3 (glacier-fed: Sokh, Kyzylsu West, Akbura …) |
| Precipitation elasticity of flow (median estimator) | 1.17 — a 10% precipitation shortfall has gone with about 12% less flow |
| Measured runoff ÷ TerraClimate precipitation | median 0.82; above 1 at a quarter of gauges (Pskem 1.39, Nauvalisoy 1.87) — **TerraClimate underestimates mountain precipitation**; volumes are lower bounds there |
| TerraClimate v1.1 modelled runoff ÷ measured | median 0.43 over 45 gauges — underestimates by more than half |
| ERA5-Land modelled runoff ÷ measured | median 1.23 over 44 gauges; 22 within a factor 1.5 — the closer of the two |

**Changed in the portal.** Basin reports join these results to the gauges in each catchment: a
column and sentences on how flow has followed precipitation, and a basin-assessment answer on
discharge that states the historical relation, applies it to the latest anomaly only as an
indication (gauge covers a quarter of the catchment or more, r ≥ 0.6), and says that no record
reaches the current year. Catchment statistics cite the gauge ratios for both runoff products.

**Limits.** Most records end by 2021, so this describes response, not current flow. Reservoir
operation and withdrawals are not separated. The precipitation is TerraClimate's, whose mountain
totals are too low; the relation holds for anomalies better than for volumes.

## 4. Follow-up: one version, citable releases, glossary, snow (2026-09-30)

- **Version gate:** `qa/version_consistency.py` runs before every `publish:r2`. Its first real
  catch: the MODIS extension below changed the cube, and the gate refused to publish until a
  release described it.
- **Citable releases:** schema-2 releases fingerprint content (text normalised to LF) and name
  each file's immutable object `data/atlas/objects/<sha256>`; `verify_served_release.py`
  downloads every object from the site and only then promotes (see `docs/ADMIN.md`).
- **Glossary:** `INTERFACE/glossary.js` renders tab names, variables and evidence labels in
  English, Russian and Uzbek, shielded from Google Translate. Draft; needs review by a
  hydrologist fluent in both languages.
- **Snow:** where glacier carry-over is 5%+ of peak storage, reports judge each winter by what it
  added. MODIS snow cover extended from 2024-12 to 2026-08 (148,900 values); `diagnose_snow_gaps.py`
  shows the gaps are summer months in 262 small lowland basins, winter 99.9% complete. Trend use
  stays withdrawn pending a reviewed trend method.
