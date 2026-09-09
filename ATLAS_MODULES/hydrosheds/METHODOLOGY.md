# HydroSHEDS basin atlas methodology — specification v0.1

Scope: the complete Amu Darya and Syr Darya drainage systems and their nested
HydroBASINS units; BasinATLAS v1 attributes only. RiverATLAS and LakeATLAS need
their own reviewed recipes before being calculated. HydroSHEDS is the hydrographic
framework; HydroATLAS supplies the environmental attribute methodology.

The existing project catalogue has 56 variable/unit families and 281 columns.
`recipes.json` binds every column to a source-based draft function, catalogue page,
temporal policy and validation gates. `RECIPES.md` is the readable function library.
Most entries remain specifications. Mean elevation (`ele_mt_sav`) is now executable
for the 20-unit Pskem candidate catchment; see `functions/README.md`. All other
attributes remain unimplemented. Proceed one attribute at a time on this pilot.

The mean-elevation candidate uses 5x5 native DEM averages and an **unweighted**
local zonal mean, following the paper's local-statistics method. Area-weighted
statistics are retained for later work but are not substituted for the local mean.
The original native zone raster is approximated by cell-center rasterization of
unsimplified polygons. The first comparison does not pass all declared tolerances;
its status is implemented, not validated. This is explicitly recorded as
`baseline_reproduction_candidate`, an interim mode with no reproduction claim.

Primary references:

- [BasinATLAS catalogue v1.0](https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf)
- [HydroATLAS technical documentation](https://data.hydrosheds.org/file/technical-documentation/HydroATLAS_TechDoc_v10_1.pdf)
- [Linke et al. 2019](https://doi.org/10.1038/s41597-019-0300-6)
- [HydroBASINS documentation](https://www.hydrosheds.org/products/hydrobasins)

Source audit: the outer local catalogue failed PDF parsing; the intact nested copy
was read instead. Its fingerprint and page references are retained in `sources.json`.
The existing parsed vocabulary sometimes reports only the HydroATLAS licence;
consult the source-page licence too. Original inputs can have different conditions.

## Function contract and processing order

```text
generate_attribute(attribute_id, basin_id, geometry_version,
                   mode, period=None, source_lock, recipe_version):
    recipe = registry.require(attribute_id, recipe_version)
    reject annual period for static/reference/climatological baseline
    require all recipe review gates resolved before scientific execution
    validate source hashes, licence, period, units and native nodata
    graph = load_complete_drainage_graph(geometry_version)
    check unique IDs, no cycles, downstream links and endorheic outlets
    support = local cells if suffix s else unique upstream cells if u else outlet p
    field = variable_function(source_lock)  # see RECIPES.md
    field = reproduce_original_grid_mask_and_temporal_reduction(field)
    result, sufficient_statistics = reduce(field, support, attribute.dimension)
    encode original scale only at export; retain physical units internally
    compare against matching official attribute and report diagnostics
    persist observation + statistics + manifest + checks + provenance
    return data, metadata, processing_log, validation_report
```

For a modern extension, area-weighted raster means use `sum(x_i*A_i)/sum(A_i)`
over valid cell intersections; percentages use explicit class area and denominator;
counts use conservative allocation of per-cell totals, never a mean. Categorical
data require class-preserving resampling. Exact baseline reproduction must first
resolve the original 15 arc-second grid, polygon-to-cell assignment, coastal masks,
small-basin treatment and rounding from technical documentation and reference
comparisons. Modern fractional intersections are not assumed to match that method.

The `s/u/p` suffix defines spatial support. Other suffixes are variable-dependent:
elevation `mn/mx` are spatial extrema, climate extremes have temporal meanings,
GLC/PNV/wetland digits are classes, and human-footprint 93/09 are epochs.
Do not infer all operations from the last two characters alone.

Whole-basin values must use complete transboundary drainage, not polygons clipped
at Uzbekistan's border. Preserve local and accumulated values separately. Catchment
topology describes natural drainage; canals, transfers and operational water use
need distinct future relationships and do not alter the reference graph silently.

## History, 2000–2026

The requested years form an availability ledger, not fabricated observations.
Every attribute/year is initially `not_assessed`, `requires_extension`,
`reference_only` or `source_epoch_only`, with null values. A recipe implementation
must inventory source assets and assess basin coverage before changing this state.

Original WaterGAP discharge/runoff describes 1971–2000; WorldClim is a historical
climatology. Their annual suffix means an annual climatological statistic. GLC2000
describes 2000, GPW in the atlas describes 2010, irrigation 2005, lights 2008 and
GDP/HDI 2015. These do not populate 27 annual observations.

Snow requires a specific audit: catalogue C09 names MYD10CM in the heading, but
describes and cites Aqua MYD10A1 v6 daily data, July 2002–April 2015. Resolve the
aggregation chain with source assets/authors before asserting exact reproduction.
The existing Terra MOD10A1 service is a candidate extension, not an identical
baseline. Aqua cannot provide 2000/2001; sensor substitutions need separate IDs,
overlap comparisons and explicit harmonization. Cloud/polar-night gaps are missing.

Implement in this order: elevation and precipitation pilot; class extents and
population; soils and inventories; snow after source-resolution audit; then
discharge, river dimensions and regulation once downscaling parameters are pinned.
Test representative mountain, arid, small, nested and terminal basins in both systems.
For annual extensions, retain one geometry version, compare overlap with baseline,
record source transitions, and release only complete years after source latency.
As of 2026-09-09, a full-year 2026 edition cannot yet be frozen.

## Future module layout

Current implementation scope is restricted to the 20 Pskem pilot units. See
[the all-281 batch evidence](PSKEM_BATCH.md) for authoritative reference imports,
34 source-based candidates, unresolved comparisons and complete processing times.
An implemented candidate is not an independently reproduced scientific result.

```text
ATLAS_MODULES/<theme>/
  module.json          identity, scope, dependencies and status
  sources.json         exact releases, licences, citations and hashes
  recipes.json         one entry per attribute
  functions/           future implemented computations
  validation/          future fixtures, tolerances and comparison reports
  METHODOLOGY.md        decisions and limitations
```

Modules expose computation separately from map styling. Annual partitions may use
`module/geometry_version/attribute/year/revision` in Parquet, with a relational
catalogue indexing them. Keep static and climatological baselines once. A snapshot
is a manifest of observations and baseline references, enabling later geodatabase
and ontology migration without redefining scientific identity.
