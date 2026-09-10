"""Measure a regional batch instead of extrapolating one.

python PIPELINES/benchmark_regional_batch.py [--sample 250]

The roadmap's regional figures were linear extrapolations from a 20-basin pilot,
and the two that mattered most — how long a regional reduction takes and how long
acquisition takes — were the least certain numbers in the plan. This measures them
on the real level-12 frame of both systems.

Three things are timed separately, because they scale differently:

* loading and rasterising the real 7,445-basin frame, which happens once per run;
* the reduction kernel over the full regional grid, which is what the grouped pass
  in `core.zonal` replaced, measured against the per-basin scan it replaced;
* a server-side reduction over a representative sample of basins, cold and warm,
  which is the acquisition path that does not download a raster at all.

The kernel timings use a synthetic field: the cost of a reduction depends on the
size of the grid and the number of basins, not on the values in it. The server-side
timings use real MODIS imagery. Both are labelled as such in the output, and the
extrapolation from the sample to the full domain is labelled as an extrapolation.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core.runtime import utc_now, write_json
from ATLAS_MODULES.core.zonal import grouped_statistics
from ATLAS_MODULES.hydrosheds.functions import dated_snow

GDB = ROOT / "GEODATA/BasinATLAS_Data_v10.gdb/BasinATLAS_Data_v10.gdb/BasinATLAS_v10.gdb"
LAYER = "BasinATLAS_v10_lev12"
BBOX = (57.0, 33.5, 79.5, 48.0)
SYSTEMS = {4120050220: "Amu Darya", 4120050240: "Syr Darya"}
CELL = 15 / 3600
OUT = ROOT / "PUBLISHED/data/atlas/regional-benchmark.json"
SCAN_SAMPLE = 40          # basins masked individually to price the old kernel
# A full atlas run reduces the grid many times over: one pass per computed attribute
# plus the monthly and per-class intermediates. The published projection this
# benchmark supersedes used the same count, so the two are directly comparable.
REDUCTION_PASSES = 250
PROJECT = "ee-sabitovty"


def load_domain(timings):
    """The real level-12 frame of both systems, as a regional run would load it."""
    import pyogrio
    started = time.perf_counter()
    frame = pyogrio.read_dataframe(GDB, layer=LAYER, bbox=BBOX)
    frame = frame[frame.MAIN_BAS.astype("int64").isin(SYSTEMS)].reset_index(drop=True)
    timings["geometry_load_seconds"] = time.perf_counter() - started
    return frame


def rasterise(frame, timings):
    """One aligned 15 arc-second label grid for the whole domain."""
    from rasterio.features import rasterize
    from rasterio.transform import from_origin

    west, south, east, north = frame.total_bounds
    west, south = [math.floor(v / CELL) * CELL for v in (west, south)]
    east, north = [math.ceil(v / CELL) * CELL for v in (east, north)]
    width, height = round((east - west) / CELL), round((north - south) / CELL)
    transform = from_origin(west, north, CELL, CELL)

    started = time.perf_counter()
    zones = rasterize(((geometry, index + 1) for index, geometry in enumerate(frame.geometry)),
                      out_shape=(height, width), transform=transform, fill=0,
                      dtype="int32", all_touched=False)
    timings["rasterise_seconds"] = time.perf_counter() - started
    return zones, transform, (width, height)


def measure_kernels(zones, transform, basins, timings):
    """The grouped pass against the per-basin scan it replaced, on the same grid."""
    from ATLAS_MODULES.hydrosheds.functions.elevation import cell_areas
    areas = np.broadcast_to(cell_areas(transform, zones.shape[0])[:, None], zones.shape)
    field = np.random.default_rng(0).random(zones.shape) * 100

    started = time.perf_counter()
    grouped_statistics(field, zones, areas, basins)
    timings["grouped_pass_seconds"] = time.perf_counter() - started

    started = time.perf_counter()
    for index in range(1, SCAN_SAMPLE + 1):
        mask = zones == index
        valid = mask & np.isfinite(field)
        float(field[valid].sum())
        float(areas[valid].sum())
    scan = time.perf_counter() - started
    timings["scan_seconds_per_basin"] = scan / SCAN_SAMPLE
    timings["scan_seconds_projected_full_domain"] = scan / SCAN_SAMPLE * basins
    timings["scan_basins_measured"] = SCAN_SAMPLE
    return timings


def choose_sample(frame, size, seed=0):
    """A representative sample: each system in proportion to the basins it holds."""
    rng = np.random.default_rng(seed)
    chosen = []
    for main_basin, name in SYSTEMS.items():
        rows = frame.index[frame.MAIN_BAS.astype("int64") == main_basin].to_numpy()
        take = max(1, round(size * len(rows) / len(frame)))
        chosen.extend(rng.choice(rows, size=min(take, len(rows)), replace=False).tolist())
    return frame.loc[sorted(chosen)]


def measure_server(sample, transform, year, month, project=PROJECT):
    """The acquisition path that returns numbers instead of a raster, cold then warm."""
    import ee
    ee.Initialize(project=project)
    grid = [transform.a, transform.b, transform.c, transform.d, transform.e, transform.f]
    features = [{"geometry": geometry.__geo_interface__, "properties": {"HYBAS_ID": int(hybas)}}
                for geometry, hybas in zip(sample.geometry, sample.HYBAS_ID)]

    measured = {"basins": len(features), "year": year, "month": month, "crs_transform": grid}
    for pass_name in ("cold", "warm"):
        started = time.perf_counter()
        try:
            rows, _ = dated_snow.extract(features, grid, [year])
            measured[f"{pass_name}_seconds"] = time.perf_counter() - started
            measured[f"{pass_name}_values"] = sum(1 for row in rows if row["value"] is not None)
            measured[f"{pass_name}_rows"] = len(rows)
            measured[f"{pass_name}_payload_bytes"] = len(json.dumps(rows).encode("utf-8"))
        except Exception as error:  # a real regional constraint is a result, not a crash
            measured[f"{pass_name}_seconds"] = time.perf_counter() - started
            measured[f"{pass_name}_failure"] = f"{type(error).__name__}: {str(error)[:400]}"
            break
    return measured


def benchmark(sample_size=250, year=2022, month=1):
    timings = {}
    frame = load_domain(timings)
    basins = len(frame)
    zones, transform, (width, height) = rasterise(frame, timings)
    measure_kernels(zones, transform, basins, timings)

    sample = choose_sample(frame, sample_size)
    server = measure_server(sample, transform, year, month)

    grouped, scan = timings["grouped_pass_seconds"], timings["scan_seconds_projected_full_domain"]
    per_basin_month = (server.get("cold_seconds", 0) / server["basins"] / 12) if server.get("cold_seconds") else None
    result = {
        "generated_at": utc_now(),
        "domain": {"basins": basins, "level": 12,
                   "systems": {name: int((frame.MAIN_BAS.astype("int64") == key).sum())
                               for key, name in SYSTEMS.items()},
                   "grid": {"cell_arcsec": 15, "columns": width, "rows": height,
                            "megacells": round(width * height / 1e6, 1)}},
        "measured_frame": {k: timings[k] for k in ("geometry_load_seconds", "rasterise_seconds")},
        "measured_reduction": {
            "basis": "Synthetic field on the real regional label grid. A reduction's cost follows "
                     "the grid size and basin count, not the values, so the timing transfers; the "
                     "numbers reduced here are not scientific results.",
            "grouped_pass_seconds": grouped,
            "scan_seconds_per_basin": timings["scan_seconds_per_basin"],
            "scan_basins_measured": SCAN_SAMPLE,
            "scan_seconds_projected_full_domain": scan,
            "speedup_over_scan": scan / grouped if grouped else None,
            "reduction_passes_per_run": REDUCTION_PASSES,
            "grouped_hours_full_run": grouped * REDUCTION_PASSES / 3600,
            "scan_hours_full_run": scan * REDUCTION_PASSES / 3600,
            "note": "The grouped pass is one sweep over the grid for every basin at once. The scan "
                    "it replaced masked the whole grid once per basin, and is projected here from "
                    f"{SCAN_SAMPLE} measured basins because running all {basins} would take hours.",
        },
        "measured_server_side": {
            **server,
            "basis": "Real MODIS MYD10A1 imagery reduced on the server over the sampled basins, "
                     "twelve months in one call. No raster is downloaded.",
            "seconds_per_basin_month": per_basin_month,
            "note": "Cold is the first call for this sample; warm repeats it. Earth Engine caches "
                    "and queues on its own schedule, so warm is not a guaranteed second-run cost, "
                    "and a repeated benchmark inherits that cache: only the first benchmark of a "
                    "given sample, month and year is genuinely cold. Observed cold times for this "
                    "sample have varied by roughly a factor of three between benchmark runs.",
        },
        "extrapolated": {
            "server_side_hours_full_domain_one_month":
                per_basin_month * basins / 3600 if per_basin_month else None,
            "server_side_hours_full_domain_twenty_years":
                per_basin_month * basins * 12 * 20 / 3600 if per_basin_month else None,
            "basis": f"Linear in basin count from the {server['basins']}-basin sample. Earth Engine "
                     "does not scale linearly under quota, queueing or retry, so treat these as "
                     "planning allowances, not delivery times.",
        },
        "supersedes": {
            "published_extrapolation_hours": 17.6,
            "measured_equivalent_hours": scan * REDUCTION_PASSES / 3600,
            "replacement_hours": grouped * REDUCTION_PASSES / 3600,
            "meaning": "The published 17.6 hours extrapolated the per-basin scan over "
                       f"{REDUCTION_PASSES} reduction passes. Measuring that same scan on the real "
                       "frame gives the middle figure; the grouped pass that replaced it gives the "
                       "last. Acquisition is a separate cost and is measured above.",
        },
    }
    write_json(OUT, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=int, default=250, help="representative basins to acquire")
    parser.add_argument("--year", type=int, default=2022)
    arguments = parser.parse_args()
    print(json.dumps(benchmark(arguments.sample, arguments.year), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
