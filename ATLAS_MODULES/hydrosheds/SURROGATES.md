# Open-data surrogates for the Pskem pilot

`surrogates.json` plans one open-data estimate for every BasinATLAS attribute in
the 20-unit Pskem pilot. `functions/surrogates.py` executes the plan and
`PIPELINES/update_pskem_atlas.py` runs it beside the original-vintage pass.

## What a surrogate is, and is not

A surrogate is an independent estimate of the same quantity, built from an open
dataset that is retrievable today. It is **not** a reproduction of the atlas
attribute, and it never replaces the original value. The original value is
imported from the intact BasinATLAS geodatabase and stays authoritative.

The consequence is a deliberate asymmetry in how differences are read. Reported
divergences are diagnostics: agreement cannot certify a reproduction, and
disagreement cannot invalidate the original. No surrogate carries a tolerance,
a pass flag, or a release gate. `surrogate_is_reproduction` is false everywhere.

## Fidelity classes

Each family declares how far its surrogate sits from the original source. The
class is part of the record, so a later reader does not have to infer it:

| Class | Meaning |
| --- | --- |
| `original_source` | Same dataset and version as the atlas source. |
| `original_source_family` | Same lineage, a different release or epoch. |
| `open_surrogate` | A different open dataset measuring the same quantity. |
| `derived_surrogate` | Derived from open inputs by an explicit formula. |
| `method_reimplementation` | The atlas index formula recomputed from other open inputs. |
| `crosswalk_surrogate` | Legends differ and are mapped by an explicit, imperfect crosswalk. |
| `weak_surrogate` | The closest open dataset measures a related but materially different quantity. |
| `units_mismatch_surrogate` | An open dataset exists, but its units are not convertible. |
| `method_not_implemented` | Inputs available; the method is not implemented in this pass. |
| `pending_open_source` | No open, programmatically retrievable source was in place. |

## Resolution, recorded for the future geodatabase

Every family records the native scale in metres and, where the source is a
geographic grid, in arc-seconds; the native grid description; the shared 15
arc-second processing grid; the resampling rule; and how the spatial support
changed. `surrogate-registry.csv` denormalises all of this to one row per
attribute, so a geodatabase can carry resolution alongside the value rather than
recovering it from prose later.

Support changes in both directions here. Copernicus land cover at 100 m, JRC
surface water at 30 m and GHSL at 100 m are averaged **down** to 15 arc-seconds,
which is a genuine aggregation. TerraClimate at 150 arc-seconds and ERA5-Land at
0.1 degrees are resampled **up**, which creates no detail: at 0.1 degrees a
level-12 basin spans only a handful of cells, and the registry says so.

Class fractions are computed at the source's native resolution before
aggregation, never by classifying an already-resampled grid. Polygon sources are
handled two ways: glacier and protected-area shares are painted at 30 m and then
aggregated, while lake shares and ecoregion majorities use exact geodesic polygon
intersection, which avoids discretisation entirely.

## Units and conversion

Builders return values in the surrogate's own physical units. The runner applies
the family conversion factor to reach stored units only when the registry marks
the units convertible. Where it does not — soil-water content in millimetres
against a stored percentage, night lights as a raw digital number against an
undocumented index transformation, human modification against the Human Footprint
index — the surrogate is published in its own units and no difference is computed.

## Crosswalks

Two class crosswalks are executed and both are lossy. Copernicus discrete classes
map to the 22 GLC2000 legend positions, leaving six positions unreachable; shrubs
are assigned to the deciduous shrub class on the regional grounds that deciduous
shrubland dominates the Western Tien Shan, because the Copernicus legend does not
resolve shrub phenology. BIOME 6000 potential biomes map to the 15 EarthStat PNV
classes. Both tables are stored in the run's source lock, so a reviewer can
disagree with a specific assignment rather than with the result as a whole.

## Excluded source

`WWF/HydroATLAS/v1/Basins/level12` is an Earth Engine copy of the atlas itself.
It is never used to build a candidate or a surrogate, because deriving a value
from the atlas and then comparing it with the atlas would prove nothing.

## What remains without an estimate

Families marked `pending_open_source` name the dataset that would satisfy them
and the reason it is not in place: a registered or on-request download (GLiM,
carbonate outcrops, the erosion grid, GRanD, GEnS), a bulk download and
reprojection step that was not implemented (GLWD, gridded GDP and HDI, the
groundwater table, permafrost zonation, GRIP road density, FEOW), a
release-specific identifier that a later release would not reproduce (GADM), or
an unimplemented method rather than a missing source (stream gradient, river area
and volume, degree of regulation). Naming the obstacle keeps each one actionable.
