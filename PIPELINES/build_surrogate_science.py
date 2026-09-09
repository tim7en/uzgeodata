"""Publish the scientific record of the open-data surrogates.

python PIPELINES/build_surrogate_science.py

Every number here is measured or read from a published run. Projections to the full
Amu Darya and Syr Darya domain are labelled as extrapolations and carry the
measurement they were extrapolated from, so nothing reads as an observed result.
"""
from __future__ import annotations
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core.runtime import write_json

GDB = ROOT / "GEODATA/BasinATLAS_Data_v10.gdb/BasinATLAS_Data_v10.gdb/BasinATLAS_v10.gdb"
# MAIN_BAS is level encoded: the Amu Darya and Syr Darya systems as written at level 12.
MAIN_BASINS = {4120050220: "Amu Darya", 4120050240: "Syr Darya"}
CELL = 15 / 3600
REDUCTION_PASSES = 250  # one per computed attribute plus the monthly and class intermediates


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def measure_domain(timings):
    """Load the full Amu + Syr level-12 frame and benchmark the reduction kernels on it."""
    import numpy as np
    import pyogrio
    from rasterio.features import rasterize
    from rasterio.transform import from_origin

    started = time.perf_counter()
    frame = pyogrio.read_dataframe(GDB, layer="BasinATLAS_v10_lev12", bbox=(57.0, 33.5, 79.5, 48.0))
    frame = frame[frame.MAIN_BAS.astype("int64").isin(MAIN_BASINS)].reset_index(drop=True)
    timings["load_seconds"] = time.perf_counter() - started

    west, south, east, north = frame.total_bounds
    west, south = [math.floor(v / CELL) * CELL for v in (west, south)]
    east, north = [math.ceil(v / CELL) * CELL for v in (east, north)]
    width, height = round((east - west) / CELL), round((north - south) / CELL)

    started = time.perf_counter()
    zones = rasterize(((geometry, index + 1) for index, geometry in enumerate(frame.geometry)),
                      out_shape=(height, width), transform=from_origin(west, north, CELL, CELL),
                      fill=0, dtype="int32", all_touched=False)
    timings["rasterise_seconds"] = time.perf_counter() - started
    inside = int((zones > 0).sum())

    field = np.random.default_rng(0).random(zones.shape) * 100
    started = time.perf_counter()
    labels, values = zones.ravel(), field.ravel()
    keep = labels > 0
    counts = np.bincount(labels[keep], minlength=len(frame) + 1)
    totals = np.bincount(labels[keep], weights=values[keep], minlength=len(frame) + 1)
    np.divide(totals, counts, out=np.full(counts.shape, np.nan), where=counts > 0)
    timings["bincount_pass_seconds"] = time.perf_counter() - started

    sample = 100
    started = time.perf_counter()
    for index in range(1, sample + 1):
        mask = zones == index
        valid = mask & np.isfinite(field)
        _ = (int(valid.sum()), float(field[valid].sum()))
    timings["per_basin_mask_seconds"] = (time.perf_counter() - started) / sample

    counts_by_system = {name: int((frame.MAIN_BAS.astype("int64") == key).sum())
                        for key, name in MAIN_BASINS.items()}
    latitude = math.radians((south + north) / 2)
    bbox_km2 = (east - west) * 111.32 * math.cos(latitude) * (north - south) * 110.57
    grids = {}
    for arcsec in (15, 3, 1):
        cell = arcsec / 3600
        columns, rows = math.ceil((east - west) / cell), math.ceil((north - south) / cell)
        grids[f"{arcsec}_arcsec"] = {"arcsec": arcsec, "columns": columns, "rows": rows,
                                     "megacells": round(columns * rows / 1e6, 1),
                                     "gigabytes_per_float32_band": round(columns * rows * 4 / 1e9, 2)}
    return {
        "systems": counts_by_system, "level": 12, "basins": int(len(frame)),
        "total_area_km2": round(float(frame.SUB_AREA.sum())),
        "median_unit_km2": round(float(frame.SUB_AREA.median()), 1),
        "bounds": [round(float(v), 3) for v in (west, south, east, north)],
        "bbox_area_km2": round(bbox_km2),
        "basin_share_of_bbox": round(inside / zones.size, 3),
        "cells_inside_basins_15arcsec": inside,
        "grids": grids,
    }


def family_rows(registry, run_directory):
    """One row per family, joining the plan to the divergence measured in the run."""
    with (run_directory / "surrogate-registry.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    by_family = {}
    for row in rows:
        by_family.setdefault(row["family"], []).append(row)
    families = []
    for name, entries in sorted(by_family.items()):
        plan = registry["families"][name]
        relative = [float(e["relative_mae"]) for e in entries if e["relative_mae"]]
        estimated = [e for e in entries if e["status"] == "open_surrogate_estimate"]
        # A family can be mixed: the human-footprint 1993 epoch has no open surface while 2009 does.
        status = ("open_surrogate_estimate" if len(estimated) == len(entries)
                  else "partial_surrogate" if estimated else entries[0]["status"])
        families.append({
            "family": name, "fidelity": plan["fidelity"], "status": status,
            "attributes": len(entries), "estimated_attributes": len(estimated),
            "original": plan["original"], "surrogate": plan["surrogate"],
            "resolution": plan["resolution"], "units": plan["units"], "divergence_notes": plan["divergence"],
            "pending_reason": entries[0]["pending_reason"] or plan.get("pending_reason"),
            "compared_attributes": len(relative),
            "relative_mae_mean": round(sum(relative) / len(relative), 4) if relative else None,
            "relative_mae_min": round(min(relative), 4) if relative else None,
            "relative_mae_max": round(max(relative), 4) if relative else None,
        })
    return families, rows


def temporal_basis():
    """Independent observation series that could test a surrogate through time."""
    registry = list(csv.DictReader((ROOT / "PUBLISHED/data/hydromet/station-registry.csv")
                                   .open(encoding="utf-8", newline="")))
    monthly = list(csv.DictReader((ROOT / "PUBLISHED/data/hydromet/station-monthly.csv")
                                  .open(encoding="utf-8", newline="")))
    variables = sorted({row["variable"] for row in monthly})
    years = [int(row["year"]) for row in monthly if row["year"]]
    return {"stations": len(registry), "monthly_records": len(monthly), "variables": variables,
            "first_year": min(years), "last_year": max(years),
            "testable_families": ["tmp", "pre"],
            "note": "Station air temperature and precipitation can test a surrogate through time. "
                    "The atlas attributes are static or climatological single values, so they cannot "
                    "themselves be verified temporally; only a surrogate against observations can."}


def main():
    batch = read(ROOT / "PUBLISHED/data/atlas/batch-latest.json")
    registry = read(ROOT / "ATLAS_MODULES/hydrosheds/surrogates.json")
    run_directory = ROOT / "PUBLISHED/data/atlas/runs" / batch["run_id"]
    families, rows = family_rows(registry, run_directory)
    timings = {}
    domain = measure_domain(timings)

    compared = [r for r in rows if r["relative_mae"]]
    compared.sort(key=lambda r: float(r["relative_mae"]))
    ranked = [{"attribute": r["attribute"], "family": r["family"], "fidelity": r["fidelity"],
               "relative_mae": round(float(r["relative_mae"]), 4)} for r in compared]

    pilot = {"basins": batch["basin_count"], "cells_15arcsec": 280 * 156,
             "wall_seconds": batch["timing"]["wall_seconds"],
             "cold_cache_wall_seconds": 209.562,
             "cold_cache_run_id": "pskem-all281-20260909T182641263450Z",
             "cold_surrogate_seconds": 195.539, "cold_modis_snow_seconds": 132.942}
    scale = domain["grids"]["15_arcsec"]["megacells"] * 1e6 / pilot["cells_15arcsec"]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_id": batch["run_id"],
        "release_rule": registry["release_rule"],
        "comparison_policy": registry["comparison_policy"],
        "fidelity_classes": registry["fidelity_classes"],
        "excluded_sources": registry["excluded_sources"],
        "pilot": {**pilot, "attributes": batch["attribute_count"], "records": batch["reference_records"],
                  "candidates": batch["candidate_attributes"],
                  "candidate_pass": batch["numerical_pass_attributes"],
                  "surrogates": batch["surrogate_attributes"],
                  "without_estimate": batch["attributes_without_any_estimate"],
                  "independently_reproduced": batch["independently_reproduced"],
                  "by_fidelity": batch["surrogate_by_fidelity"]},
        "domain": domain,
        "families": families,
        "verification": {
            "spatial": {"convertible_attributes": batch["surrogate_comparable_attributes"],
                        "with_reference_magnitude": len(ranked),
                        "closest": ranked[:8], "furthest": ranked[-6:],
                        "basis": "Every surrogate is reduced over the same 20 basins and the same support "
                                 "rule as the original attribute, then differenced in stored units."},
            "temporal": temporal_basis(),
        },
        "scale_projection": {
            "basis": "Measured on this machine at full Amu + Syr extent; source acquisition is extrapolated "
                     "linearly from the pilot cold run and is the least certain figure here.",
            "cell_scale_factor": round(scale),
            "basin_scale_factor": round(domain["basins"] / pilot["basins"]),
            "measured": {
                "frame_load_seconds": round(timings["load_seconds"], 2),
                "rasterise_seconds": round(timings["rasterise_seconds"], 2),
                "bincount_pass_seconds": round(timings["bincount_pass_seconds"], 3),
                "per_basin_mask_seconds": round(timings["per_basin_mask_seconds"], 4),
                "reduction_passes": REDUCTION_PASSES,
            },
            "reduction_minutes_bincount": round(timings["bincount_pass_seconds"] * REDUCTION_PASSES / 60, 1),
            "reduction_hours_current_kernel": round(timings["per_basin_mask_seconds"] * domain["basins"]
                                                    * REDUCTION_PASSES / 3600, 1),
            "kernel_speedup_required": round(timings["per_basin_mask_seconds"] * domain["basins"]
                                             / timings["bincount_pass_seconds"]),
            "acquisition_hours_linear": round(pilot["cold_surrogate_seconds"] * scale / 3600, 1),
            "acquisition_hours_linear_modis_only": round(pilot["cold_modis_snow_seconds"] * scale / 3600, 1),
            "raster_gigabytes_15arcsec": round(125 * domain["grids"]["15_arcsec"]["gigabytes_per_float32_band"], 1),
        },
    }
    out = ROOT / "PUBLISHED/data/atlas/surrogate-science.json"
    write_json(out, payload)
    print(f"Surrogate science record: {len(families)} families, {domain['basins']:,} level-12 units in scope, "
          f"{len(ranked)} attributes with a measured spatial difference -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
