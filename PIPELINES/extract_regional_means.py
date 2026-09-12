"""Take the band-mean adapters regional, on both spatial supports.

python PIPELINES/extract_regional_means.py gpw ghsl dmsp_lights human_modification surface_water

After the class-fraction families, most of what remains is simpler: select a band,
apply the source's own conversion, and average it over the basin. The bands and the
conversions here are the reviewed ones from `surrogates`, unchanged.

Two upstream rules, not one, and the difference matters. An index or a share is
averaged over the upstream area, weighted by basin area. A count is not: the
population upstream of a basin is the sum of the people in every basin above it, and
area-weighting it would answer a different question. Getting this wrong produces
numbers that look entirely reasonable, so the rule travels with each column rather
than being assumed.
"""
from __future__ import annotations
import argparse
import collections
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import observations
from ATLAS_MODULES.core.runtime import sha256, utc_now, write_json
from PIPELINES.extract_dated_snow import PROJECT
from PIPELINES.extract_regional_landcover import order_and_areas
from PIPELINES.extract_regional_snow import (
    batches, geometry_version, load_frame, regional_grid, with_retries)
from PIPELINES.stage_pilot_observations import BASIN_LEVEL, STORE

CHECKPOINTS = ROOT / "WORKSPACE/atlas_runs/regional_means"
# Below this a refused span is reported rather than split further: the refusal has
# stopped being about how many basins the request carries.
SMALLEST_SPAN = 8

# Each column: (local name, upstream name, upstream rule, unit).
# "mean" is area-weighted over the upstream area; "total" sums a per-area density
# into a count and then sums those counts downstream.
SOURCES = {
    "gpw": {
        "asset": "CIESIN/GPWv411/GPW_Population_Density", "kind": "collection",
        "index": "gpw_v4_population_density_rev11_2015_30_sec", "band": 0,
        "epoch": "2015", "time_kind": "source_epoch",
        "bands": {"ppd": {"columns": [("ppd_pk_sav", "ppd_pk_uav", "mean", "people per km2"),
                                      ("pop_ct_ssu", "pop_ct_usu", "total", "people")]}},
        "note": "Population density for the 2015 epoch. Counts are the density integrated over "
                "basin area, so they inherit the density surface's assumptions about where "
                "people are within a cell.",
    },
    "ghsl": {
        "asset": "JRC/GHSL/P2023A/GHS_BUILT_S", "kind": "collection", "index": "2015",
        "band": "built_surface", "divide": 100.0,
        "epoch": "2015", "time_kind": "source_epoch",
        "bands": {"urb": {"columns": [("urb_pc_sse", "urb_pc_use", "mean", "percent cover")]}},
        "note": "Built surface in square metres per 100 m cell, divided by 100 to give percent.",
    },
    "dmsp_lights": {
        "asset": "NOAA/DMSP-OLS/NIGHTTIME_LIGHTS", "kind": "collection", "index": "F182010",
        "band": "stable_lights", "epoch": "2010", "time_kind": "source_epoch",
        "bands": {"nli": {"columns": [("nli_ix_sav", "nli_ix_uav", "mean", "digital number 0-63")]}},
        "note": "DMSP-OLS stable lights for 2010 as the raw digital number; the atlas index "
                "transformation is not applied.",
    },
    "human_modification": {
        "asset": "CSP/HM/GlobalHumanModification", "kind": "collection", "index": None,
        "band": "gHM", "epoch": "2016", "time_kind": "source_epoch",
        "bands": {"hft": {"columns": [("hft_ix_s09", "hft_ix_u09", "mean", "modification index 0-1")]}},
        "note": "Global Human Modification 2016. This is not the Human Footprint index, and no "
                "1993 surface exists, so it stands against the 2009 dimension only.",
    },
    "gfsad": {
        "asset": "USGS/GFSAD1000_V1", "kind": "image", "band": "landcover",
        "epoch": "2010", "time_kind": "source_epoch",
        "bands": {"ire": {"select": "landcover", "eq": [1, 2], "multiply": 100.0,
                          "columns": [("ire_pc_sse", "ire_pc_use", "mean", "percent cover")]}},
        "note": "Irrigated cropland share from GFSAD1000 classes 1 and 2, 2010 epoch.",
    },
    "openlandmap_soil": {
        "asset": "OpenLandMap/SOL", "kind": "custom", "image": "soil_profile",
        "epoch": None, "time_kind": "static",
        "bands": {
            "cly": {"columns": [("cly_pc_sav", "cly_pc_uav", "mean", "percent by weight")]},
            "snd": {"columns": [("snd_pc_sav", "snd_pc_uav", "mean", "percent by weight")]},
            "slt": {"columns": [("slt_pc_sav", "slt_pc_uav", "mean", "percent by weight")]},
            "soc": {"columns": [("soc_th_sav", "soc_th_uav", "mean", "tonnes per hectare")]},
        },
        "note": "Texture and organic-carbon stock integrated over 0-100 cm with trapezoidal "
                "depth weights, as the pilot builder does. Silt is closed as 100 minus clay "
                "minus sand rather than measured, and the carbon stock carries no "
                "coarse-fragment correction.",
    },
    "glims": {
        "asset": "GLIMS/current", "kind": "painted", "paint": "glims",
        "epoch": None, "time_kind": "source_epoch",
        "bands": {"gla": {"columns": [("gla_pc_sse", "gla_pc_use", "mean", "percent cover")]}},
        "spatial_batches": 100,
        "note": "Glacier outlines painted at 30 m and mean-aggregated. Outline dates vary "
                "between glaciers, so this is not a single epoch.",
    },
    "wdpa": {
        "asset": "WCMC/WDPA/current/polygons", "kind": "painted", "paint": "wdpa",
        "epoch": None, "time_kind": "source_epoch",
        "bands": {"pac": {"columns": [("pac_pc_sse", "pac_pc_use", "mean", "percent cover")]}},
        "spatial_batches": 100,
        "note": "Protected areas from the current WDPA release, later than the 2014 snapshot "
                "the atlas cites.",
    },
    "surface_water": {
        "asset": "JRC/GSW1_4/GlobalSurfaceWater", "kind": "image",
        "epoch": None, "time_kind": "climatology",
        "period": ["1984-01-01", "2022-01-01"],
        "bands": {
            "inu_lt": {"select": "occurrence", "unmask": 0,
                       "columns": [("inu_pc_slt", "inu_pc_ult", "mean", "percent cover")]},
            "inu_mn": {"select": "seasonality", "unmask": 0, "gte": 12, "multiply": 100.0,
                       "columns": [("inu_pc_smn", "inu_pc_umn", "mean", "percent cover")]},
            "inu_mx": {"select": "max_extent", "unmask": 0, "multiply": 100.0,
                       "columns": [("inu_pc_smx", "inu_pc_umx", "mean", "percent cover")]},
        },
        "note": "Optical surface water from JRC occurrence, seasonality and maximum extent, "
                "1984-2021. Optical products see open water, not wetland under vegetation.",
    },
}


DEPTHS = (0, 10, 30, 60, 100)


def depth_weights():
    """Trapezoidal weights over the 0-100 cm profile, matching the pilot builder."""
    weights = [0.0] * len(DEPTHS)
    for index in range(len(DEPTHS) - 1):
        span = DEPTHS[index + 1] - DEPTHS[index]
        weights[index] += span / 2
        weights[index + 1] += span / 2
    total = sum(weights)
    return [w / total for w in weights]


def soil_profile(transform):
    """Clay, sand, closed silt and organic-carbon stock over 0-100 cm."""
    import ee
    weights = depth_weights()

    def integrate(asset, scale, name):
        image = ee.Image(asset)
        total = image.select(f"b{DEPTHS[0]}").multiply(scale * weights[0])
        for depth, weight in zip(DEPTHS[1:], weights[1:]):
            total = total.add(image.select(f"b{depth}").multiply(scale * weight))
        return total.rename(name)

    clay = integrate("OpenLandMap/SOL/SOL_CLAY-WFRACTION_USDA-3A1A1A_M/v02", 1.0, "cly")
    sand = integrate("OpenLandMap/SOL/SOL_SAND-WFRACTION_USDA-3A1A1A_M/v02", 1.0, "snd")
    carbon = integrate("OpenLandMap/SOL/SOL_ORGANIC-CARBON_USDA-6A1C_M/v02", 5.0, "orgc")
    density = integrate("OpenLandMap/SOL/SOL_BULKDENS-FINEEARTH_USDA-4A1H_M/v02", 10.0, "bulk")
    # g/kg times kg/m3 over a one-metre column gives g/m2; 1 g/m2 is 0.01 t/ha.
    stock = carbon.multiply(density).multiply(0.01).rename("soc")
    silt = ee.Image.constant(100.0).subtract(clay).subtract(sand).rename("slt")
    return ee.Image.cat([clay, sand, silt, stock]).reduceResolution(
        ee.Reducer.mean(), maxPixels=4096).reproject(crs="EPSG:4326", crsTransform=transform)


def painted_fraction(collection, transform):
    """Polygons burned at 30 m, then averaged to the analysis grid as a percentage.

    Painting before aggregating is what makes a share of a basin rather than a count
    of polygons: a glacier covering a tenth of a cell contributes a tenth, not one.
    """
    import ee
    painted = (ee.Image().byte().paint(collection, 1).unmask(0)
               .setDefaultProjection(crs="EPSG:4326", scale=30))
    return (painted.reduceResolution(ee.Reducer.mean(), maxPixels=4096)
            .reproject(crs="EPSG:4326", crsTransform=transform).multiply(100))


def glims_outlines(bounds):
    """Most recent analysis of each glacier; repeat submissions would inflate the area."""
    import ee
    outlines = (ee.FeatureCollection("GLIMS/current").filterBounds(bounds)
                .filter(ee.Filter.eq("line_type", "glac_bound")))
    return outlines.sort("anlys_time", False).distinct("glac_id")


def wdpa_polygons(bounds):
    import ee
    return ee.FeatureCollection("WCMC/WDPA/current/polygons").filterBounds(bounds)


PAINTED = {"glims": glims_outlines, "wdpa": wdpa_polygons}
CUSTOM = {"soil_profile": soil_profile}


def stack(spec, transform):
    import ee
    if spec["kind"] == "custom":
        return CUSTOM[spec["image"]](transform)
    if spec["kind"] == "painted":
        name = next(iter(spec["bands"]))
        # Selecting features to the batch's own extent keeps the painted collection
        # small; painting the whole domain for every batch would repeat that work
        # thirty times over.
        west, south, east, north = spec["_bounds"]
        region = ee.Geometry.Rectangle([west, south, east, north], None, False)
        return painted_fraction(PAINTED[spec["paint"]](region), transform).rename(name)
    if spec["kind"] == "collection":
        collection = ee.ImageCollection(spec["asset"])
        if spec.get("index"):
            collection = collection.filter(ee.Filter.eq("system:index", spec["index"]))
        base = ee.Image(collection.first())
    else:
        base = ee.Image(spec["asset"])

    layers = []
    for name, band in spec["bands"].items():
        image = base.select(band["select"]) if "select" in band else (
            base.select(spec["band"]) if spec.get("band") is not None else base)
        if "unmask" in band:
            image = image.unmask(band["unmask"])
        if "gte" in band:
            image = image.gte(band["gte"])
        if "eq" in band:
            codes = band["eq"]
            mask = image.eq(codes[0])
            for code in codes[1:]:
                mask = mask.Or(image.eq(code))
            image = mask
        if spec.get("divide"):
            image = image.divide(spec["divide"])
        if band.get("multiply"):
            image = image.multiply(band["multiply"])
        layers.append(image.reduceResolution(ee.Reducer.mean(), maxPixels=4096)
                      .reproject(crs="EPSG:4326", crsTransform=transform).rename(name))
    return ee.Image.cat(layers)


def spatially_ordered(frame):
    """Reorder basins so that neighbours share a batch.

    Basins arrive in identifier order, which is not a geographic order: 250 taken
    that way are scattered across the whole region, and their envelope is nearly the
    whole domain. For a band mean that costs nothing, because each basin is reduced
    against the image independently. For a painted collection it is fatal -- the
    polygons filtered to that envelope are the entire catalogue, and painting them
    exceeds what Earth Engine will build. Half-degree latitude bands, west to east
    within each, keep a batch compact enough that only nearby polygons are fetched.
    """
    centres = frame.geometry.representative_point()
    ordered = frame.assign(_lat=centres.y, _lon=centres.x)
    ordered = ordered.assign(_band=(ordered["_lat"] / 0.5).astype(int))
    ordered = ordered.sort_values(["_band", "_lon"])
    return ordered.drop(columns=["_lat", "_lon", "_band"]).reset_index(drop=True)


def bounds_of(features, pad=0.05):
    """The batch's own envelope, so a painted collection is filtered to what it covers."""
    xs, ys = [], []
    for feature in features:
        for ring in feature["geometry"]["coordinates"]:
            for point in (ring if isinstance(ring[0][0], float) else ring[0]):
                xs.append(point[0])
                ys.append(point[1])
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


def batch_rows(spec, features, transform):
    import ee
    if spec["kind"] == "painted":
        spec = {**spec, "_bounds": bounds_of(features)}
    points = ee.FeatureCollection([
        ee.Feature(ee.Geometry(f["geometry"]), {"hybas_id": str(int(f["properties"]["HYBAS_ID"]))})
        for f in features])
    table = stack(spec, transform).reduceRegions(
        collection=points, reducer=ee.Reducer.mean().unweighted(),
        crs="EPSG:4326", crsTransform=transform).getInfo()
    names = list(spec["bands"])
    # Earth Engine names a reduction after the reducer when the image carries one
    # band, and after each band when it carries several. Reading only band names
    # would silently return nothing at all for every single-band source.
    if len(names) == 1:
        return {f["properties"]["hybas_id"]: {names[0]: f["properties"].get("mean")}
                for f in table["features"]}
    return {f["properties"]["hybas_id"]: {b: f["properties"].get(b) for b in names}
            for f in table["features"]}


def walk(local, below, areas, combine):
    """Accumulate downstream, releasing a basin only once everything above it is in.

    `combine` decides what accumulating means: an area-weighted mean for an index or
    a share, a plain total for a count.
    """
    upstream = collections.defaultdict(list)
    for basin, downstream in below.items():
        if downstream in local:
            upstream[downstream].append(basin)
    waiting = {b: len([u for u in upstream.get(b, []) if u in local]) for b in local}
    ready = [b for b, n in waiting.items() if n == 0]

    carried = {b: combine.start(b, local[b], areas.get(b, 0.0)) for b in local}
    weight = {b: areas.get(b, 0.0) for b in local}
    seen = 0
    while ready:
        basin = ready.pop()
        seen += 1
        downstream = below.get(basin)
        if downstream in local:
            carried[downstream] = combine.add(carried[downstream], carried[basin])
            weight[downstream] += weight[basin]
            waiting[downstream] -= 1
            if waiting[downstream] == 0:
                ready.append(downstream)
    if seen != len(local):
        raise ValueError(f"routing did not resolve: {seen} of {len(local)}")
    return {b: combine.finish(carried[b], weight[b]) for b in local}


class Weighted:
    """Area-weighted mean over the basin and everything above it."""
    @staticmethod
    def start(_basin, bands, area):
        return {k: (v or 0.0) * area for k, v in bands.items()}

    @staticmethod
    def add(into, other):
        return {k: into[k] + other[k] for k in into}

    @staticmethod
    def finish(carried, area):
        return {k: (v / area if area else None) for k, v in carried.items()}


class Total:
    """A per-area density integrated to a count, then summed downstream."""
    @staticmethod
    def start(_basin, bands, area):
        return {k: (v or 0.0) * area for k, v in bands.items()}

    @staticmethod
    def add(into, other):
        return {k: into[k] + other[k] for k in into}

    @staticmethod
    def finish(carried, _area):
        return dict(carried)


def once(work, label, ledger):
    """A single try, so a refusal that will not change on repetition is answered now."""
    try:
        return work(), None
    except Exception as error:
        message = f"{type(error).__name__}: {str(error)[:300]}"
        ledger["retries"].append({"at": utc_now(), "target": label,
                                  "attempt": 1, "error": message})
        return None, message


def oversized(message):
    """Earth Engine refusing the request itself, rather than failing to serve it.

    The basin outlines travel inside the request, and a level-12 basin in the
    glaciated headwaters carries far more coordinates than one on the plain. A batch
    of a hundred is therefore cheap in one place and over the limit in another, and
    waiting will not make it smaller.
    """
    return "too large" in message.lower()


def extract_span(spec, features, transform, source, index, ledger, low=0, high=None):
    """Rows for one batch, halving the span Earth Engine refuses to accept.

    Splitting only what was refused keeps the batches that already work at their
    current size: a run that lowered the batch size everywhere would pay the extra
    round trips over the whole region to fix the few places that need it.
    """
    high = len(features) if high is None else high
    whole = low == 0 and high == len(features)
    label = f"batch-{index:04d}" if whole else f"batch-{index:04d}-{low:03d}-{high:03d}"
    cache = CHECKPOINTS / source / f"{label}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8")), True

    span = features[low:high]
    rows, error = once(lambda: batch_rows(spec, span, transform), label, ledger)
    if rows is None and oversized(error) and len(span) > SMALLEST_SPAN:
        middle = low + len(span) // 2
        ledger["splits"].append({"at": utc_now(), "target": label, "at_index": middle,
                                 "error": error})
        left, _ = extract_span(spec, features, transform, source, index, ledger, low, middle)
        right, _ = extract_span(spec, features, transform, source, index, ledger, middle, high)
        merged = {**left, **right}
        if len(merged) == len(span):
            # Cached under the whole span's name as well, so the next run does not pay
            # the refusal again to discover a split it has already made. A span that
            # lost a part stays uncached, because it is not the batch it claims to be.
            write_json(cache, merged)
        return merged, False
    if rows is None:
        # Either transient, in which case waiting is the right answer, or irreducible,
        # in which case the failure belongs in the ledger rather than in a retry loop.
        rows, error = with_retries(lambda: batch_rows(spec, span, transform), label, ledger)
        if error:
            return {}, False
    write_json(cache, rows)
    return rows, False


def run(sources, batch_size=250, store=STORE, project=PROJECT):
    import ee
    ee.Initialize(project=project)
    frame = load_frame()
    transform, version = regional_grid(frame), geometry_version(frame)
    below, areas = order_and_areas(frame)
    done = []

    for source in sources:
        spec = SOURCES[source]
        identifier = f"regional-{source}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}Z"
        recipe = f"{source}_regional@{sha256(Path(__file__))[:12]}"
        started, at = time.perf_counter(), utc_now()
        ledger = {"run_id": identifier, "started_at": at, "source": source,
                  "asset": spec["asset"], "geometry_version": version,
                  "basins": len(frame), "retries": [], "failures": [], "splits": []}

        # Painted sources are filtered to each batch's extent, so their batches have to
        # be geographically compact -- and smaller, since the polygons come with them.
        size = spec.get("spatial_batches", batch_size)
        ordered = spatially_ordered(frame) if spec.get("spatial_batches") else frame
        local, plan = {}, list(batches(ordered, size))
        for index, features in plan:
            rows, cached = extract_span(spec, features, transform, source, index, ledger)
            local.update(rows)
            if not cached:
                print(f"{source} batch {index + 1}/{len(plan)}: {len(local):,} basins "
                      f"({time.perf_counter() - started:.0f}s)", flush=True)

        averaged = walk(local, below, areas, Weighted)
        totalled = walk(local, below, areas, Total)

        period = {}
        if spec.get("period"):
            period = {"valid_start": spec["period"][0], "valid_end": spec["period"][1]}
        elif spec.get("epoch"):
            period = {"valid_start": f"{spec['epoch']}-01-01",
                      "valid_end": f"{int(spec['epoch']) + 1}-01-01"}

        built, missing = [], 0
        for basin, bands in local.items():
            for name, band in spec["bands"].items():
                for local_column, upstream_column, rule, unit in band["columns"]:
                    pairs = [(local_column, "s",
                              bands[name] if rule == "mean" else
                              (bands[name] or 0.0) * areas.get(basin, 0.0) if bands[name] is not None else None),
                             (upstream_column, "u",
                              (averaged if rule == "mean" else totalled)[basin][name])]
                    for column, support, value in pairs:
                        missing += value is None
                        built.append(observations.build(
                            basin_id=basin, geometry_version=version, basin_level=BASIN_LEVEL,
                            attribute_id=f"hydrosheds.basinatlas.v1.{column}",
                            recipe_version=recipe, mode="annual_extension",
                            spatial_support=support, time_kind=spec["time_kind"],
                            temporal_statistic="epoch_snapshot" if spec.get("epoch")
                            else ("long_term_climatological_mean" if spec.get("period")
                                  else "time_invariant"),
                            value=value, unit=unit, quality_flag="open_surrogate_estimate",
                            missing_reason=None if value is not None else "no_source_value_in_basin",
                            source_release_id=f"{source}@{spec['asset']}", run_id=identifier,
                            retrieved_at=at, recorded_at=at, **period))
        # A re-run that completes a partial one changes every upstream total below
        # the basins it adds, and those totals are already published.
        added, _ = observations.append_partitioned(
            store, observations.as_revisions(store, built))

        ledger.update({"finished_at": utc_now(), "wall_seconds": time.perf_counter() - started,
                       "basins_extracted": len(local), "rows": len(built), "new_rows": added,
                       "without_value": missing, "note": spec["note"],
                       "attributes": sorted({r["attribute_id"].split(".")[-1] for r in built}),
                       "complete": len(local) == len(frame) and not ledger["failures"],
                       "upstream_rules": {c[0]: c[2] for b in spec["bands"].values()
                                          for c in b["columns"]}})
        write_json(store / f"regional-{source}-ledger.json", ledger)
        observations.merge_table(store / "run.csv", [{
            "run_id": identifier, "started_at": at, "finished_at": ledger["finished_at"],
            "wall_seconds": ledger["wall_seconds"],
            "status": "complete" if ledger["complete"] else "incomplete",
            "scientific_release": "not_eligible"}], "run_id")
        observations.merge_table(store / "recipe.csv", [
            {"recipe_version": recipe, "mode": "annual_extension"}], "recipe_version")
        observations.merge_table(store / "source_release.csv", [{
            "source_release_id": f"{source}@{spec['asset']}", "name": source,
            "asset": spec["asset"], "sha256": "", "epoch": spec.get("epoch") or "",
            "valid_start": period.get("valid_start", ""), "valid_end": period.get("valid_end", ""),
            "retrieved_at": at, "pinned": False}], "source_release_id")
        print(f"{source}: {len(built):,} rows, {len(ledger['attributes'])} attributes, "
              f"{ledger['wall_seconds']:.0f}s", flush=True)
        done.append(ledger)
    return done


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", nargs="+", choices=sorted(SOURCES))
    parser.add_argument("--batch", type=int, default=250)
    arguments = parser.parse_args()
    ledgers = run(arguments.sources, arguments.batch)
    print(json.dumps([{k: v for k, v in l.items() if k != "retries"} for l in ledgers],
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
