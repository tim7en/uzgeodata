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

`python qa/deep_dive/data_quality/browse_portal.py [base-url]` → [browse.json](browse.json)

Every page at desktop and phone width, then basin 4121292070 opened through the finder and each
tab clicked. Results are summarised in the research log entry for this date.
