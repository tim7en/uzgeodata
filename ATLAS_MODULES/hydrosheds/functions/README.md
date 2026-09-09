# Computation functions

`pilot_batch.py` implements 34 source-based candidates (4 elevation, 16 temperature,
14 precipitation) for the 20 Pskem units. Run `npm run atlas:pskem` to capture all
281 original reference attributes and calculate these candidates one at a time.
See [batch methods and results](../PSKEM_BATCH.md). Remaining methods are specified
but not independently reconstructed; scientific release remains pending.

`elevation.py` also supports the earlier **mean elevation (`ele_mt_sav`)** runner for the current
Pskem pilot. Run `npm run atlas:attribute -- --attribute ele_mt_sav --pilot pskem`.
The runner rejects other attributes and expanded pilot selections, preventing an
accidental full-region batch. Other function contracts remain specifications in
`../RECIPES.md` and `../recipes.json`.

The pilot comprises 20 native level-12 units selected by the existing Pskem
candidate catchment. The runner reads unsimplified GEODATA geometry rather than
display polygons, downloads one original EarthEnv-DEM90 tile and caches its archive.
OGC:CRS84 and EPSG:4326 both describe WGS84 here; their axis-order distinction is
checked explicitly when validating the source grid. Source hashes are pinned in
each run's lockfile. A later rerun can pass `--source-lock <previous lockfile>`.

The first comparison passes 15 of 20 pairs at the predeclared 1 m tolerance.
The largest difference is 10.055 m in an eight-cell basin. Zone reconstruction
and original preprocessing require further review; the tolerance has not changed.
Do not advance the scientific status without the required review evidence.
All functions must return values, sufficient statistics and provenance separately
from map styling. Importing official BasinATLAS values is a separate mode.
