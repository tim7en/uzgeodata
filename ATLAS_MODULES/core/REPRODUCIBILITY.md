# Mandatory scientific reproduction contract

Every thematic module MUST pass these gates before any result is described as
reproduced or included in a scientific atlas edition.

1. **Specification:** persistent module, recipe and attribute IDs; versioned
   formula/pseudocode; source citation and exact catalogue section/page; units,
   scaling, masks, temporal meaning, spatial support and missing-value rules.
2. **Inputs:** immutable source release, asset URI and SHA-256, retrieval date,
   observation period, original licence and redistribution decision. Record the
   geometry release/hash, HydroBASINS level, complete drainage domain and outlet.
3. **Execution:** code commit, clean source archive/hash, dependency lockfile or
   container digest, command, parameters, random seed where relevant, logs and
   machine-readable run manifest. A moving `latest` URL is not a pinned input.
4. **Scientific checks:** documented grid alignment, geographic cell areas,
   nodata/coverage, units, temporal completeness, topology, mass/area consistency,
   no double-counting and attribute-specific limits. Baseline matching requires
   the original rasterization and rounding conventions, not just a plausible mean.
5. **Comparison:** independently compare reconstructed values against the official
   BasinATLAS release for the same HYBAS_ID and level. Report bias, MAE, RMSE,
   maximum absolute difference and valid count for numeric attributes; confusion
   matrix/agreement for classes; separate missingness and local/upstream results.
   Predeclare per-attribute absolute/relative tolerances and coverage thresholds
   with scientific justification before inspecting results. No universal tolerance.
6. **Independent rerun:** a second operator/environment reruns pinned inputs and
   reports output hashes or justified numeric equivalence. Record reviewer, date,
   report and approval; numerical agreement alone is not scientific validation.
7. **Release:** an immutable snapshot manifest lists all output hashes, source and
   method versions, failures/exclusions, temporal coverage and reproduction report.
   Corrections create a new revision with `supersedes`, never overwrite an edition.

Statuses: `specified -> implemented -> validated -> reproduced -> released`.
Only evidence from the appropriate gates permits advancement. Unresolved source
details must be documented in a candidate implementation and block claims of
validated baseline reproduction. Code, tests and a real comparison are required
to mark an attribute implemented; a failed comparison remains visible.

Use three separate result modes:

- `reference_import`: exact values retrieved from the published atlas; no claim
  that upstream scientific processing has been reproduced.
- `baseline_reproduction`: original source vintages and published method.
- `annual_extension`: explicitly versioned new observations/method; never silently
  replace the original attribute or claim equivalence because column names match.

During development, `baseline_reproduction_candidate` is an explicit interim mode:
it permits test calculations with documented method uncertainties and blocks
scientific reproduction/release claims. It is not an additional final atlas product.

Scientific observations use a long table: `observation_id, basin_id,
geometry_version, basin_level, attribute_id, recipe_version, mode, spatial_support,
time_kind, valid_start, valid_end, year, month, value, unit, coverage_fraction,
quality_flag, missing_reason, source_release_id, run_id, revision, supersedes`.
Store HYBAS_ID as a string. Keep `retrieved_at`/`recorded_at` separate from valid time.
Static/climatological values have null year; annual snapshots reference them.
Monthly climatology month 07 is not July 2026. Null values require a reason.
Missing data must not become zero. Partial 2026 observations remain provisional.

Future relational tables: `basin_geometry`, `source_release`, `recipe`, `run`,
`observation`, `snapshot`, `snapshot_member`, `reproduction_report` and
`entity_link`. Use foreign keys and unique observation/revision identities; keep
COGs outside the relational database. Retain sufficient statistics (weighted sum,
valid area, class areas, totals) for lossless aggregation across non-overlapping
units. Never sum already accumulated upstream values or average basin means
without their weights. A new geometry release needs a crosswalk and new run.

Ontology bindings are proposed mappings, not inferred equivalences. Snow extent
is not snow depth, glacier area is not volume, natural discharge is not runoff
depth, and reservoir capacity is not observed water storage. Preserve distinct
concepts, units, spatial support, derivation and source identity for later review.
