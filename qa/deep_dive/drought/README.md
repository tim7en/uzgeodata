# Drought record: basin 4121292070

Re-run with `python qa/deep_dive/drought/check_drought_basin.py` (add `--offline` to reuse
the saved copy of the served file). Evidence: [result.json](result.json); the served bytes
are kept as `served-4121292070.json` with their SHA-256 in the result.

The drought-study basin files are not in the Git checkout, so the check reads what the
portal serves and tests it three ways, with code that shares nothing with
`PIPELINES/build_drought_study.py`:

| Check | Result |
|---|---|
| Water-year totals 1992–2025 against the local TerraClimate v1.1 monthly table | 34 years, largest difference 0.0005 mm — **PASS** |
| 1991–2020 WMO normal from the served totals | 683.774 mm against 683.77 served — **PASS** |
| Percent anomaly of every water year 1961–2025 | 65 years, largest difference 0.0006 points — **PASS** |
| SPI-12 refitted with Thom's (1958) gamma approximation (McKee et al. 1993) instead of the pipeline's scipy fit | 65 years, largest difference 0.0005 — **PASS** |

Water year 2025 (October 2024–September 2025): 476.1 mm, −30.4% against 1991–2020,
SPI-12 −1.78 (severe drought).

**What this does not show.** It checks arithmetic and source consistency, not whether
TerraClimate is right: no rain gauge is compared. PDSI, runoff `q` and the upstream
columns are not checked, and water year 1991 cannot be checked against local monthly
data (October–December 1990 is not in the checkout).
