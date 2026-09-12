"""Take any class-fraction adapter regional, on both spatial supports.

python PIPELINES/extract_regional_classes.py pnv_biome

Several atlas families are the same computation over a different legend: mask the
source classification to the codes that map to one target class, average the mask to
get that class's share of the basin, and repeat. Land cover was the first ported;
potential natural vegetation and freshwater ecoregions are the same shape again.

So the shape is described once here and the sources differ only by their spec. A new
class-fraction family becomes an entry in SOURCES rather than another pipeline to
keep in step, which matters because the part most easily got wrong -- upstream
accumulation -- is then written once and verified once.

Upstream values are accumulated through the published routing, area-weighted, so each
basin is counted exactly once. Re-reducing over a merged upstream mask, or averaging
basin means without their areas, would both give a different and wrong answer.
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
from ATLAS_MODULES.hydrosheds.functions.surrogates import (
    EARTHSTAT_PNV_FROM_BIOME00K, GLC2000_FROM_COPERNICUS)
from PIPELINES.extract_dated_snow import PROJECT
from PIPELINES.extract_regional_landcover import accumulate, order_and_areas
from PIPELINES.extract_regional_snow import (
    batches, geometry_version, load_frame, regional_grid, with_retries)
from PIPELINES.stage_pilot_observations import BASIN_LEVEL, STORE

CHECKPOINTS = ROOT / "WORKSPACE/atlas_runs/regional_classes"

SOURCES = {
    "pnv_biome": {
        "asset": "OpenLandMap/PNV/PNV_BIOME-TYPE_BIOME00K_C/v01",
        "kind": "image", "band": "biome_type",
        "crosswalk": EARTHSTAT_PNV_FROM_BIOME00K, "classes": range(1, 16),
        "local": "pnv_pc_s{:02d}", "upstream": "pnv_pc_u{:02d}", "majority": "pnv_cl_smj",
        "time_kind": "static", "epoch": None,
        "unit": "percent cover", "majority_unit": "classes (15)",
        "note": "EarthStat PNV legend crosswalked from BIOME 6000 potential biomes. Potential "
                "vegetation is a modelled natural state, not an observation of what grows there.",
    },
    "copernicus_lc": {
        "asset": "COPERNICUS/Landcover/100m/Proba-V-C3/Global",
        "kind": "collection", "index": "2015", "band": "discrete_classification",
        "crosswalk": GLC2000_FROM_COPERNICUS, "classes": range(1, 23),
        "local": "glc_pc_s{:02d}", "upstream": "glc_pc_u{:02d}", "majority": "glc_cl_smj",
        "time_kind": "source_epoch", "epoch": "2015",
        "unit": "percent cover", "majority_unit": "classes (22)",
        "note": "GLC2000 legend crosswalked from the 2015 Copernicus classification.",
    },
}


def source_image(spec):
    import ee
    if spec["kind"] == "collection":
        image = ee.Image(ee.ImageCollection(spec["asset"])
                         .filter(ee.Filter.eq("system:index", spec["index"])).first())
    else:
        image = ee.Image(spec["asset"])
    return image.select(spec["band"])


def class_stack(spec, transform):
    """One band per target class, as a percentage of the basin."""
    import ee
    classified = source_image(spec)
    layers = []
    for target in spec["classes"]:
        codes = sorted(code for code, mapped in spec["crosswalk"].items() if mapped == target)
        mask = classified.eq(codes[0]) if codes else classified.multiply(0)
        for code in codes[1:]:
            mask = mask.Or(classified.eq(code))
        layers.append(mask.reduceResolution(ee.Reducer.mean(), maxPixels=1024)
                      .reproject(crs="EPSG:4326", crsTransform=transform)
                      .multiply(100).rename(f"c{target:02d}"))
    return ee.Image.cat(layers)


def batch_rows(spec, features, transform):
    import ee
    points = ee.FeatureCollection([
        ee.Feature(ee.Geometry(f["geometry"]), {"hybas_id": str(int(f["properties"]["HYBAS_ID"]))})
        for f in features])
    table = class_stack(spec, transform).reduceRegions(
        collection=points, reducer=ee.Reducer.mean().unweighted(),
        crs="EPSG:4326", crsTransform=transform).getInfo()
    return {f["properties"]["hybas_id"]:
            {f"c{t:02d}": f["properties"].get(f"c{t:02d}") for t in spec["classes"]}
            for f in table["features"]}


def rows_for(spec, local, upstream):
    """Published column names on both supports, plus the majority class."""
    for basin, bands in local.items():
        up = upstream[basin]
        for target in spec["classes"]:
            band = f"c{target:02d}"
            yield basin, spec["local"].format(target), bands[band], "s", spec["unit"]
            yield basin, spec["upstream"].format(target), up[band], "u", spec["unit"]
        shares = [(bands[f"c{t:02d}"] or 0.0, t) for t in spec["classes"]]
        best = max(shares)
        yield (basin, spec["majority"], float(best[1]) if best[0] > 0 else None,
               "s", spec["majority_unit"])


def run(source, batch_size=250, store=STORE, project=PROJECT):
    import ee
    ee.Initialize(project=project)
    spec = SOURCES[source]
    frame = load_frame()
    transform, version = regional_grid(frame), geometry_version(frame)
    identifier = f"regional-{source}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}Z"
    recipe = f"{source}_regional@{sha256(Path(__file__))[:12]}"
    started, at = time.perf_counter(), utc_now()
    ledger = {"run_id": identifier, "started_at": at, "source": source, "asset": spec["asset"],
              "geometry_version": version, "basins": len(frame),
              "classes": len(list(spec["classes"])), "retries": [], "failures": []}

    local, plan = {}, list(batches(frame, batch_size))
    for index, features in plan:
        cache = CHECKPOINTS / source / f"batch-{index:04d}.json"
        if cache.exists():
            local.update(json.loads(cache.read_text(encoding="utf-8")))
            continue
        rows, error = with_retries(lambda f=features: batch_rows(spec, f, transform),
                                   f"batch-{index}", ledger)
        if error:
            continue
        write_json(cache, rows)
        local.update(rows)
        print(f"{source} batch {index + 1}/{len(plan)}: {len(local):,} basins "
              f"({time.perf_counter() - started:.0f}s)", flush=True)

    below, areas = order_and_areas(frame)
    upstream = accumulate(local, below, areas)

    period = ({"valid_start": f"{spec['epoch']}-01-01",
               "valid_end": f"{int(spec['epoch']) + 1}-01-01"} if spec["epoch"] else {})
    built, missing = [], 0
    for basin, column, value, support, unit in rows_for(spec, local, upstream):
        missing += value is None
        built.append(observations.build(
            basin_id=basin, geometry_version=version, basin_level=BASIN_LEVEL,
            attribute_id=f"hydrosheds.basinatlas.v1.{column}", recipe_version=recipe,
            mode="annual_extension", spatial_support=support, time_kind=spec["time_kind"],
            temporal_statistic="epoch_snapshot" if spec["epoch"] else "time_invariant",
            value=value, unit=unit, quality_flag="open_surrogate_estimate",
            missing_reason=None if value is not None else "no_class_share_in_basin",
            source_release_id=f"{source}@{spec['asset']}", run_id=identifier,
            retrieved_at=at, recorded_at=at, **period))
    added, _ = observations.append_partitioned(store, built)

    ledger.update({"finished_at": utc_now(), "wall_seconds": time.perf_counter() - started,
                   "basins_extracted": len(local), "rows": len(built), "new_rows": added,
                   "without_value": missing,
                   "attributes": sorted({r["attribute_id"].split(".")[-1] for r in built}),
                   "complete": len(local) == len(frame) and not ledger["failures"],
                   "note": spec["note"],
                   "upstream_method": "Area-weighted over the basin and everything draining into "
                                      "it, accumulated through the published routing."})
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
        "asset": spec["asset"], "sha256": "", "epoch": spec["epoch"] or "",
        "valid_start": period.get("valid_start", ""), "valid_end": period.get("valid_end", ""),
        "retrieved_at": at, "pinned": False}], "source_release_id")
    return ledger


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", choices=sorted(SOURCES))
    parser.add_argument("--batch", type=int, default=250)
    arguments = parser.parse_args()
    ledger = run(arguments.source, arguments.batch)
    print(json.dumps({k: v for k, v in ledger.items() if k != "retries"},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
