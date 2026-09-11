"""Take the land-cover attributes regional, local support and upstream.

python PIPELINES/extract_regional_landcover.py

This is the largest single block of the pilot still confined to twenty basins:
twenty-two GLC2000 class percentages, a majority class, and forest, crop and pasture
fractions, each published for the basin itself and for everything draining through it.
Fifty-one attributes from one adapter.

The class definitions, the crosswalk from the Copernicus legend and the 2015 epoch are
the pilot's, unchanged. What changes is the route: class masks are reduced on the
server and returned as numbers, so the region needs no raster download.

Upstream values are accumulated through the routing graph rather than re-reduced over
a merged mask. A basin's upstream figure is the area-weighted mean of itself and every
basin draining into it, formed by walking the graph from the headwaters down, which
sums each basin exactly once. Averaging basin means without their areas, or summing
figures that are already accumulated, would both be wrong, and the second is the
easier mistake to make.

The weight is the basin area BasinATLAS publishes, so an upstream mean here is
area-weighted the way the atlas defines it, not weighted by the count of cells that
happened to carry a value.
"""
from __future__ import annotations
import argparse
import collections
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import observations
from ATLAS_MODULES.core.runtime import sha256, utc_now, write_json
from ATLAS_MODULES.hydrosheds.functions.surrogates import GLC2000_FROM_COPERNICUS
from PIPELINES.extract_dated_snow import PROJECT
from PIPELINES.extract_regional_snow import (
    batches, geometry_version, load_frame, regional_grid, with_retries)
from PIPELINES.stage_pilot_observations import BASIN_LEVEL, STORE

ROUTING = ROOT / "PUBLISHED/data/hydroclimate/basin-routing-level12.csv"
CHECKPOINTS = ROOT / "WORKSPACE/atlas_runs/regional_landcover"
LEDGER = STORE / "regional-landcover-ledger.json"
ASSET = "COPERNICUS/Landcover/100m/Proba-V-C3/Global"
EPOCH = "2015"
RELEASE = f"copernicus_lc@{ASSET}#{EPOCH}"
FRACTIONS = (("tree-coverfraction", "for"), ("crops-coverfraction", "crp"),
             ("grass-coverfraction", "pst"))
CLASSES = range(1, 23)


def class_image(transform):
    """One band per GLC2000 class plus the three cover fractions, all as percentages."""
    import ee
    image = ee.Image(ee.ImageCollection(ASSET)
                     .filter(ee.Filter.eq("system:index", EPOCH)).first())
    discrete = image.select("discrete_classification")
    layers = []
    for target in CLASSES:
        codes = sorted(code for code, mapped in GLC2000_FROM_COPERNICUS.items() if mapped == target)
        mask = discrete.eq(codes[0]) if codes else discrete.multiply(0)
        for code in codes[1:]:
            mask = mask.Or(discrete.eq(code))
        layers.append(mask.reduceResolution(ee.Reducer.mean(), maxPixels=1024)
                      .reproject(crs="EPSG:4326", crsTransform=transform)
                      .multiply(100).rename(f"glc_{target:02d}"))
    for band, alias in FRACTIONS:
        layers.append(image.select(band).reduceResolution(ee.Reducer.mean(), maxPixels=1024)
                      .reproject(crs="EPSG:4326", crsTransform=transform).rename(alias))
    return ee.Image.cat(layers)


def batch_rows(features, transform):
    import ee
    points = ee.FeatureCollection([
        ee.Feature(ee.Geometry(f["geometry"]), {"hybas_id": str(int(f["properties"]["HYBAS_ID"]))})
        for f in features])
    table = class_image(transform).reduceRegions(
        collection=points, reducer=ee.Reducer.mean().unweighted(),
        crs="EPSG:4326", crsTransform=transform).getInfo()
    out = {}
    for feature in table["features"]:
        properties = feature["properties"]
        out[properties["hybas_id"]] = {
            band: properties.get(band)
            for band in [f"glc_{t:02d}" for t in CLASSES] + [a for _, a in FRACTIONS]}
    return out


def order_and_areas(frame):
    """Downstream links and areas, keyed by basin, from the published routing."""
    areas = {str(int(h)): float(a) for h, a in zip(frame.HYBAS_ID, frame.SUB_AREA)}
    below = {}
    with ROUTING.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["level"] != str(BASIN_LEVEL):
                continue
            basin, downstream = row["hybas_id"], row["next_down"]
            below[basin] = downstream if downstream not in ("0", "", None) else None
    return below, areas


def accumulate(local, below, areas):
    """Area-weighted mean over each basin and everything draining into it.

    Walked from the headwaters down so each basin is added to its receiver exactly
    once; a basin is released only when every basin above it has already been added.
    """
    upstream = collections.defaultdict(list)
    for basin, downstream in below.items():
        if downstream in local:
            upstream[downstream].append(basin)
    waiting = {basin: len([u for u in upstream.get(basin, []) if u in local]) for basin in local}
    ready = [basin for basin, count in waiting.items() if count == 0]

    weighted = {basin: {band: (value or 0.0) * areas.get(basin, 0.0)
                        for band, value in bands.items()} for basin, bands in local.items()}
    covered = {basin: areas.get(basin, 0.0) for basin in local}
    order = []
    while ready:
        basin = ready.pop()
        order.append(basin)
        downstream = below.get(basin)
        if downstream in local:
            for band, total in weighted[basin].items():
                weighted[downstream][band] += total
            covered[downstream] += covered[basin]
            waiting[downstream] -= 1
            if waiting[downstream] == 0:
                ready.append(downstream)
    if len(order) != len(local):
        raise ValueError(f"routing did not resolve: {len(order)} of {len(local)} basins ordered")
    return {basin: {band: (total / covered[basin] if covered[basin] else None)
                    for band, total in bands.items()} for basin, bands in weighted.items()}


def columns(local, upstream):
    """The published attribute names, for both supports, plus the majority class."""
    for basin, bands in local.items():
        up = upstream[basin]
        for target in CLASSES:
            yield basin, f"glc_pc_s{target:02d}", bands[f"glc_{target:02d}"], "s"
            yield basin, f"glc_pc_u{target:02d}", up[f"glc_{target:02d}"], "u"
        for _, alias in FRACTIONS:
            yield basin, f"{alias}_pc_sse", bands[alias], "s"
            yield basin, f"{alias}_pc_use", up[alias], "u"
        shares = [(bands[f"glc_{t:02d}"] or 0.0, t) for t in CLASSES]
        best = max(shares)
        yield basin, "glc_cl_smj", float(best[1]) if best[0] > 0 else None, "s"


def run(batch_size=250, store=STORE, project=PROJECT):
    import ee
    ee.Initialize(project=project)
    frame = load_frame()
    transform, version = regional_grid(frame), geometry_version(frame)
    identifier = f"regional-landcover-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}Z"
    recipe = f"copernicus_lc_regional@{sha256(Path(__file__))[:12]}"
    started, at = time.perf_counter(), utc_now()
    ledger = {"run_id": identifier, "started_at": at, "asset": ASSET, "epoch": EPOCH,
              "geometry_version": version, "basins": len(frame),
              "retries": [], "failures": []}

    local = {}
    plan = list(batches(frame, batch_size))
    for index, features in plan:
        cache = CHECKPOINTS / f"batch-{index:04d}.json"
        if cache.exists():
            local.update(json.loads(cache.read_text(encoding="utf-8")))
            continue
        rows, error = with_retries(lambda f=features: batch_rows(f, transform),
                                   f"batch-{index}", ledger)
        if error:
            continue
        write_json(cache, rows)
        local.update(rows)
        print(f"batch {index + 1}/{len(plan)}: {len(local):,} basins "
              f"({time.perf_counter() - started:.0f}s)", flush=True)

    below, areas = order_and_areas(frame)
    upstream = accumulate(local, below, areas)

    built, missing = [], 0
    for basin, column, value, support in columns(local, upstream):
        unit = "classes (22)" if column == "glc_cl_smj" else "percent cover"
        missing += value is None
        built.append(observations.build(
            basin_id=basin, geometry_version=version, basin_level=BASIN_LEVEL,
            attribute_id=f"hydrosheds.basinatlas.v1.{column}", recipe_version=recipe,
            mode="annual_extension", spatial_support=support, time_kind="source_epoch",
            temporal_statistic="epoch_snapshot",
            valid_start=f"{EPOCH}-01-01", valid_end=f"{int(EPOCH) + 1}-01-01",
            value=value, unit=unit, quality_flag="open_surrogate_estimate",
            missing_reason=None if value is not None else "no_class_share_in_basin",
            source_release_id=RELEASE, run_id=identifier, retrieved_at=at, recorded_at=at))
    added, _ = observations.append_partitioned(store, built)

    ledger.update({"finished_at": utc_now(), "wall_seconds": time.perf_counter() - started,
                   "basins_extracted": len(local), "rows": len(built), "new_rows": added,
                   "without_value": missing,
                   "attributes": sorted({r["attribute_id"].split(".")[-1] for r in built}),
                   "complete": len(local) == len(frame) and not ledger["failures"],
                   "upstream_method": "Area-weighted over the basin and everything draining "
                                      "into it, accumulated through the published routing so "
                                      "each basin is counted once.",
                   "epoch_note": "A 2015 land-cover epoch. It is not a 2026 state, and nothing "
                                 "here describes change since 2015."})
    write_json(LEDGER, ledger)
    observations.merge_table(store / "run.csv", [{
        "run_id": identifier, "started_at": at, "finished_at": ledger["finished_at"],
        "wall_seconds": ledger["wall_seconds"],
        "status": "complete" if ledger["complete"] else "incomplete",
        "scientific_release": "not_eligible"}], "run_id")
    observations.merge_table(store / "recipe.csv", [
        {"recipe_version": recipe, "mode": "annual_extension"}], "recipe_version")
    observations.merge_table(store / "source_release.csv", [{
        "source_release_id": RELEASE, "name": "Copernicus Global Land Cover, collection 3",
        "asset": ASSET, "sha256": "", "epoch": EPOCH,
        "valid_start": f"{EPOCH}-01-01", "valid_end": f"{int(EPOCH) + 1}-01-01",
        "retrieved_at": at, "pinned": False}], "source_release_id")
    return ledger


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=int, default=250)
    ledger = run(parser.parse_args().batch)
    print(json.dumps({k: v for k, v in ledger.items() if k != "retries"}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
