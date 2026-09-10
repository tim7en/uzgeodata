# Atlas modules

Each thematic atlas owns a folder containing `module.json`, source references,
recipes, validation rules and (later) computation functions. Shared scientific
contracts live in `core/`; scripts in `PIPELINES/` orchestrate modules; the
interface only presents their outputs. HydroSHEDS / BasinATLAS is the first module.
Other atlas products must adopt this contract before implementation begins.

- [Scientific requirements](core/REPRODUCIBILITY.md) — and `core/observations.py`, the
  executable observation/revision contract every atlas value enters through
- [HydroSHEDS methodology](hydrosheds/METHODOLOGY.md)
- [Attribute recipes](hydrosheds/RECIPES.md)
- [Open-data surrogates](hydrosheds/SURROGATES.md) — published as a page at `/surrogates.html`
  via `npm run atlas:science`
- [Project roadmap](roadmap.json)
- [Project updates and source news](updates.json)

Run `npm run atlas:publish` after changing module specifications, roadmap or news.
The same publisher runs before development and production builds. The roadmap at
`/roadmap.html` refreshes its published JSON every 60 seconds and on demand.
News is a curated, dated feed: append an item with a source and affected phase;
external announcements never automatically mark scientific work complete.
To publish a change to an already running production instance, regenerate the
data, build and deploy the resulting distribution through the normal workflow.

Roadmap phases are dependency ordered, with explicit acceptance gates. Status
changes require evidence links. Recipe counts are calculated from the module
registry; a catalogue entry is not evidence of scientific reproduction.

The current batch covers all 281 original reference attributes for the 20-unit
Pskem pilot, with 34 independently calculated candidates, 196 open-data surrogate
estimates, 51 attributes with no estimate and scientific release still pending.
Run `npm run atlas:pskem`; see [batch evidence](hydrosheds/PSKEM_BATCH.md).
Surrogate values carry their source, release, licence, native resolution and
processing resolution, so a future geodatabase keeps resolution beside value.
No annual history is generated. Raw rasters stay in GEODATA/object storage; runs go in
`WORKSPACE/atlas_runs/<module>/<run_id>/`. Frozen publication manifests reference
those assets and their hashes, rather than duplicating static data for every year.

Run one attribute: `npm run atlas:attribute -- --attribute ele_mt_sav --pilot pskem`.
Each invocation saves wall time by stage, CPU time, download/cache details,
values, comparison, source lock, code snapshot and environment record. Failed
attempts remain in the timing history. The roadmap processing panel polls every
five seconds. Use the existing development server to see an active run; a static
deployment shows the last published run until the updated data is deployed.
