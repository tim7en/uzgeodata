# Scientific Research Replicator — first pass

**Verdict: NOT ASSESSABLE / BLOCKED for numerical reproduction.** One open full-text, peer-reviewed paper was verified, but its original input archive has not been acquired and inspected. No published number is presented as independently reproduced.

## Selected study and target

Siegfried, T., Mujahid, A. U. H., Marti, B., Molnar, P., Karger, D. N. & Yakovlev, A. (2024), *Unveiling the future water pulse of central asia: a comprehensive 21st century hydrological forecast from stochastic water balance modeling*, *Climatic Change* 177, 141. [Publisher full text](https://link.springer.com/article/10.1007/s10584-024-03799-y), DOI [10.1007/s10584-024-03799-y](https://doi.org/10.1007/s10584-024-03799-y). The [author data and scripts record](https://zenodo.org/records/10125163) has DOI [10.5281/zenodo.10125163](https://doi.org/10.5281/zenodo.10125163).

The candidate target is the reported **−2.7% regional median change in modeled specific discharge** for 2071–2100 under SSP5-8.5, relative to the *modeled* 1979–2011 baseline (article §3.3, Fig. 5/Table 2 context). This is a model projection, not a measured future discharge trend. It is relevant to UZGEODATA's Amu/Syr Darya model and climate claims, but the paper covers 221 high-mountain catchments across five large basins rather than UZGEODATA's 7,445 level-12 HydroBASINS units.

## Verified method and data access

The [full methods, §2](https://link.springer.com/article/10.1007/s10584-024-03799-y) state that catchments are filtered to area >200 km²; baseline climate is CHELSA V2.1 daily data for 1 January 1979–31 December 2011. Four CMIP6 GCMs drive four SSP scenarios for 2011–2040, 2041–2070 and 2071–2100. The steady-state stochastic soil moisture model derives a runoff coefficient from aridity and storage indices, then adds glacier imbalance ablation; the paper says coefficients were evaluated with Mathematica at 200-digit precision. The published result ensembles GCM outcomes and reports the median across catchments. Zenodo lists code (327.4 kB), methods (25.4 kB) and data (2.5 GB) archives. Listing establishes availability at the record level, not successful retrieval, complete contents or a usable licence for every upstream input.

## Reproduction gate

The exact missing evidence is a locally retrieved, hash-verified and inspected `DATA_ZENODO.zip` and `CODE_ZENODO.zip`, plus an identified script path from inputs to the −2.7% result. The 2.5 GB author archive was not downloaded for this bounded first pass. A standalone arithmetic manipulation of the published percentage would reuse the conclusion and is not a reproduction. Accordingly there is no independent numerical script or discrepancy estimate yet.

To move to L2, pin the Zenodo file checksums and versions, inspect archive licences and code, run its original calculation, then separately implement the 221-catchment calculation without importing the author's derived outputs. Record the ensemble order, median definition, precision settings, excluded basins and exact target table row. UZGEODATA comparison is a later analysis requiring matched mountain catchments, baseline years, CHELSA/CMIP6 and glacier inputs, and model definitions; its 2003–2024 gridded historical record cannot be compared numerically with this end-century projection as-is.

Machine-readable catalogue and status: [`literature.json`](literature.json).
