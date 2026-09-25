# Drought and wet years across the Amu Darya and Syr Darya

**Build date:** 2026-09-25. **Page:** `/drought.html`. **Per-basin view:** the
**Drought 1961–2025** tab on any level-12 basin in the basin explorer.

## Question

Which basins suffer drought most often and most severely, and when a drought
happens, do the regions of Uzbekistan that depend on river water lose more from
their own dry weather or from a shortfall in the mountains upstream?

## Data

TerraClimate v1.1, the producer's June 2026 release, which covers 1950–2025 in
one product version. Monthly precipitation, PDSI, runoff generation `q` and PET
for 1960–2025 are reduced to all 7,445 level-12 basins by fractional grid overlap
(`extract_regional_climate_grids.py terraclimate-v11 --family
terraclimate-v1.1-history`). The atlas cube (TerraClimate v1.0) and the ERA-based
2025–2026 estimates are not used, so no series mixes product versions.

## Method

- **Water year** runs October to September and is labelled by the year it ends,
  from WY1961 to WY2025.
- **Norms** are computed for each unit: the WMO 1991–2020 normal, the previous
  1961–1990 normal, and the mean of the 10, 20 and 30 water years before each
  year. The trailing norms start in 1971, 1981 and 1991.
- **SPI-12** fits a gamma distribution to each unit's own 1991–2020 water-year
  totals. The thresholds are −1 for moderate, −1.5 for severe and −2 for extreme
  drought. Level-7 units, systems and regions are aggregated by area before
  fitting; their SPI is never an average of SPIs.
- **PDSI** is the water-year mean of TerraClimate's monthly Palmer index.
- **Upstream supply** accumulates precipitation and `q` over every basin's whole
  upstream catchment. For each Uzbek region, the reach with the largest upstream
  area is taken as the river that supplies it.

## Results

| Documented year | Amu Darya SPI (rank) | Syr Darya SPI (rank) | In the data |
| --- | ---: | ---: | --- |
| 1969 flood | +2.40 (wettest) | +2.77 (wettest) | Wettest water year of 65 in both |
| 1998 high water | +1.63 (2nd wettest) | +1.61 (5th wettest) | Wet in both |
| 2000 drought | −1.91 (2nd driest) | −0.97 | An Amu Darya drought |
| 2001 drought | −1.80 (3rd driest) | −0.86 | An Amu Darya drought, PDSI −3.1 |
| 2008 drought | −1.57 (6th driest) | −1.95 (6th driest) | Both systems |
| 2021 drought | −1.59 (5th driest) | −2.07 (3rd driest) | Worst in the Syr Darya |

Every documented event shows in the data, and none was used to fit anything.
2025 was also dry in both systems: SPI −1.20 in the Amu Darya and −1.45 in the
Syr Darya, with precipitation 18–19% below the 1991–2020 normal.

**Downstream.** In 2001 the lower Amu Darya regions (Karakalpakstan, Khorezm and
Bukhara) had 23–25% less local precipitation than normal, while runoff generated
upstream was 44% below normal. The shortfall came mainly from upstream. In 2021
the pattern reversed: local precipitation fell 50–52% and upstream generation
22%. Kashkadarya and Jizzakh show the largest upstream swings (−66% to −71%),
because their rivers drain smaller, rain-fed catchments, not the glaciated
Pamir and Tien Shan.

**Exposure.** 206 of 438 sub-basins had four or more severe drought water years
from 1991 to 2025. The most frequent are in the lowland Amu Darya around 64–66°E.
Between the two normals, 68 sub-basins became more than 5% drier and 54 more than
5% wetter.

## Limits

- TerraClimate is a gridded model product, not station observations.
- `q` comes from a one-bucket water balance with no glacier melt or reservoir
  regulation. In hot, dry years glacier melt and reservoir releases sustain the
  real rivers, so the upstream anomaly overstates the flow deficit. Read it as a
  rain and snow supply signal, not a discharge estimate.
- The region's supplying reach is the largest river passing through it, which
  ignores canal transfers between systems.

## Files

`PUBLISHED/data/atlas/drought-study/` is gitignored and published to R2:

| File | Content |
| --- | --- |
| `summary.json`, `geometry.json` | Everything the study page draws. |
| `basins/{HYBAS_ID}.json` | One basin's 65 water years, for the map tab and its CSV. |
| `basin-wateryear.parquet` | 483,925 level-12 rows with all norms, SPI, PDSI and upstream supply. |
| `level07-wateryear.parquet` | 438 sub-basins × 65 water years. |
| `regions-wateryear.parquet` | Uzbekistan's 14 regions × 65 water years. |

Rebuild with:

```bash
python PIPELINES/extract_regional_climate_grids.py terraclimate-v11 --years 1960-2025 \
  --variables ppt,PDSI,q,pet --family terraclimate-v1.1-history
python PIPELINES/build_drought_study.py
python -m pytest TESTS/test_drought_study.py -q
```

When the producer publishes a new v1.1 year, extract it with the same command and
rebuild. The norms and SPI fit stay on 1991–2020, so earlier values do not change.

Sources for the documented years:
[CAWater PEER Amu Darya key findings](https://www.cawater-info.net/projects/peer-amudarya/key_findings_e.htm),
[2021 Central Asia drought](https://en.wikipedia.org/wiki/2021_Central_Asia_drought),
[RSAA: Remembering the Amu Darya](https://rsaa.org.uk/blog/remembering-the-amu-darya/),
[Lower Amu Darya water quality](https://www.researchgate.net/publication/352087422_Assessment_of_water_quality_in_the_downstream_of_the_Amu_Darya_basin).
