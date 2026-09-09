"""Run one HydroATLAS attribute for the Pskem pilot, with full wall/CPU timings.

python PIPELINES/run_atlas_attribute.py --attribute ele_mt_sav --pilot pskem
Source downloads are restricted to the single pilot tile; no full-basin batch runs.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core.runtime import RunTimer, sha256, write_json


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_csv(path, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def compare(rows, specification):
    pairs = [r for r in rows if r["value_m"] is not None and r["reference_m"] is not None]
    diffs = [r["value_m"] - r["reference_m"] for r in pairs]
    n = len(pairs)
    tolerance = specification["absolute_tolerance_m"]
    passed = sum(abs(d) <= tolerance for d in diffs)
    return {"count": n, "missing_pairs": len(rows) - n,
            "bias_m": sum(diffs) / n if n else None,
            "mae_m": sum(abs(d) for d in diffs) / n if n else None,
            "rmse_m": (sum(d*d for d in diffs) / n)**0.5 if n else None,
            "max_absolute_error_m": max(map(abs, diffs)) if n else None,
            "absolute_tolerance_m": tolerance, "within_tolerance": passed,
            "all_pairs_pass": n == len(rows) and n > 0 and passed == n}


def publish_history():
    """Keep failed attempts visible so download/retry time is not hidden."""
    records = [read(path) for path in (ROOT / "WORKSPACE/atlas_runs/hydrosheds").glob("*/timing.json")]
    records.sort(key=lambda r: r["started_at"], reverse=True)
    write_json(ROOT / "PUBLISHED/data/atlas/run-history.json", {"runs": records,
               "recorded_wall_seconds": sum(r["wall_seconds"] for r in records if r["status"] != "running"),
               "note": "Sum of recorded sequential processing attempts, including failures. Excludes development, source research, UI publication and tests."})


def run(args):
    run_id = f"pskem-{args.attribute}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    directory = ROOT / "WORKSPACE/atlas_runs/hydrosheds" / run_id
    progress = ROOT / "PUBLISHED/data/atlas/processing-status.json"
    timer = RunTimer(run_id, directory, progress)
    try:
        with timer.stage("setup_and_input_validation"):
            import numpy as np
            import rasterio
            from rasterio.features import rasterize
            from rasterio.enums import MergeAlg
            from shapely.geometry import shape
            from ATLAS_MODULES.hydrosheds.functions.elevation import (
                required_tiles, acquire_tile, unpack_tile, aggregate_tile,
                cell_areas, make_zones, zonal_statistics, merge_statistics)

            pilot_path = ROOT / "PUBLISHED/data/case-studies/pskem-candidate-catchment.geojson"
            geometry_path = ROOT / "GEODATA/transboundary_basins_v2/hydroatlas-level12-full-basins.geojson"
            reference_path = ROOT / "PUBLISHED/data/hydroclimate/reference-basin-attributes.csv"
            tolerance_path = ROOT / "ATLAS_MODULES/hydrosheds/validation/ele_mt_sav.json"
            spec = read(tolerance_path)
            pilot = read(pilot_path)
            ids = {str(int(f["properties"]["HYBAS_ID"])) for f in pilot["features"]}
            source_features = read(geometry_path)["features"]
            features = sorted([f for f in source_features if str(int(f["properties"]["HYBAS_ID"])) in ids],
                              key=lambda f: int(f["properties"]["HYBAS_ID"]))
            if len(features) != len(ids) or len(ids) != 20:
                raise ValueError("Pskem pilot identity changed; review the 20-unit selection before extending scope")
            if any(not shape(f["geometry"]).is_valid for f in features):
                raise ValueError("Invalid source geometry; do not repair it silently")
            tiles = required_tiles(features)
            if len(tiles) != 1:
                raise ValueError("Pilot now needs more than one tile; review scope before downloading")
            with reference_path.open(encoding="utf-8", newline="") as stream:
                references = {str(int(r["hybas_id"])): r[args.attribute] for r in csv.DictReader(stream) if str(int(r["hybas_id"])) in ids}
            selected = {"type": "FeatureCollection", "features": features}
            write_json(directory / "pilot-basins.geojson", selected)
            write_json(directory / "reference-values.json", references)
            write_json(directory / "tolerance.json", spec)
            versions = {name: importlib.metadata.version(name) for name in ("numpy", "rasterio", "pyproj", "shapely", "requests")}
            freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True, check=True)
            (directory / "requirements.freeze.txt").write_text(freeze.stdout, encoding="utf-8")
            code_paths = [Path(__file__).resolve(), ROOT / "ATLAS_MODULES/core/runtime.py", ROOT / "ATLAS_MODULES/hydrosheds/functions/elevation.py"]
            code = []
            for path in code_paths:
                relative = path.relative_to(ROOT)
                snapshot = directory / "code" / relative
                snapshot.parent.mkdir(parents=True, exist_ok=True)
                snapshot.write_bytes(path.read_bytes())
                code.append({"path": relative.as_posix(), "sha256": sha256(snapshot)})
            git_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
            input_identity = {"pilot_ids": sorted(ids), "geometry_sha256": sha256(directory / "pilot-basins.geojson"),
                              "reference_sha256": sha256(directory / "reference-values.json"),
                              "tolerance_sha256": sha256(directory / "tolerance.json")}
            locked = read(args.source_lock) if args.source_lock else None
            if locked and locked["input_identity"] != input_identity:
                raise ValueError("Pinned pilot geometry/reference/tolerance changed")
            timer.event(f"Pilot Pskem: {len(features)} native level-12 units; {len(tiles)} DEM tile; attribute {args.attribute}")

        with timer.stage("source_download_or_cache_verification", shared=True):
            inputs = []
            for south, west in tiles:
                expected = None
                if locked:
                    expected = next((r for r in locked["tiles"] if r["south"] == south and r["west"] == west), None)
                    if expected is None:
                        raise ValueError("Required tile absent from source lock")
                inputs.append(acquire_tile(south, west, ROOT / "GEODATA/atlas_sources/earthenv_dem90_v1", timer, sha256, expected))
            source_lock = {"source": "EarthEnv-DEM90 v1", "licence": "CC-BY-4.0", "input_identity": input_identity,
                           "citation": "Robinson, Regetz & Guralnick (2014), doi:10.1016/j.isprsjprs.2013.11.002",
                           "tiles": [{k: v for k, v in r.items() if k not in {"path", "wall_seconds", "cache_hit"}} for r in inputs]}
            write_json(directory / "source-lock.json", source_lock)

        with timer.stage("dem_unpack_and_15arcsecond_mean", shared=True):
            prepared = []
            for record in inputs:
                native_path = unpack_tile(record, directory / "native")
                values, native_counts, transform = aggregate_tile(native_path, record)
                raster_path = directory / f"{record['name']}-15s-mean.tif"
                with rasterio.open(raster_path, "w", driver="GTiff", height=values.shape[0], width=values.shape[1],
                                   count=1, dtype="float64", crs="EPSG:4326", transform=transform,
                                   nodata=float("nan"), compress="deflate") as output:
                    output.write(values, 1)
                prepared.append((record, values, native_counts, transform, raster_path))
                timer.event(f"Prepared {record['name']}: arithmetic 5x5 native-cell means on the 15 arc-second grid")

        with timer.stage("pilot_zone_rasterization", shared=True):
            zoned = []
            for record, values, native_counts, transform, raster_path in prepared:
                zones = make_zones(features, transform, values.shape)
                overlap = rasterize([(f["geometry"], 1) for f in features], out_shape=values.shape,
                                    transform=transform, fill=0, dtype="uint16", all_touched=False, merge_alg=MergeAlg.add)
                if np.any(overlap > 1):
                    raise ValueError("Native basin polygons overlap at selected cell centers")
                zoned.append((values, native_counts, transform, zones))
                timer.event(f"Rasterized {int(np.count_nonzero(zones)):,} pilot cells; no overlapping zones")

        with timer.stage("calculate_ele_mt_sav", attribute=args.attribute):
            totals = None
            for values, native_counts, transform, zones in zoned:
                stats = zonal_statistics(values, zones, cell_areas(transform, values.shape[0]), len(features), native_counts)
                totals = merge_statistics(totals, stats)
            observations = []
            for index, feature in enumerate(features, 1):
                basin_id = str(int(feature["properties"]["HYBAS_ID"]))
                valid, count = int(totals["valid_cells"][index]), int(totals["total_cells"][index])
                value = float(totals["sum_m"][index] / valid) if valid else None
                raw_reference = references.get(basin_id)
                reference = float(raw_reference) if raw_reference not in (None, "", "-9999") else None
                complete = count > 0 and valid == count and int(totals["partial_native_cells"][index]) == 0
                observations.append({"basin_id": basin_id, "basin_level": 12, "attribute": args.attribute,
                                     "value_m": value, "reference_m": reference,
                                     "difference_m": value - reference if value is not None and reference is not None else None,
                                     "valid_cells": valid, "total_cells": count,
                                     "coverage_fraction": valid / count if count else 0,
                                     "partial_native_cells": int(totals["partial_native_cells"][index]),
                                     "sum_m": float(totals["sum_m"][index]),
                                     "valid_area_m2": float(totals["valid_area_m2"][index]),
                                     "weighted_sum_m_m2": float(totals["weighted_sum_m_m2"][index]),
                                     "quality_flag": "candidate_complete" if complete else "incomplete_source_support",
                                     "time_kind": "static_reference", "year": None, "month": None,
                                     "mode": "baseline_reproduction_candidate", "run_id": run_id})
            timer.event(f"Calculated {args.attribute} for {len(observations)} pilot units")

        with timer.stage("reference_comparison_and_quality_checks"):
            metrics = compare(observations, spec)
            coverage_pass = all(r["quality_flag"] == "candidate_complete" for r in observations)
            report = {"attribute": args.attribute, "pilot": "pskem", "run_id": run_id,
                      "implementation_status": "implemented", "scientific_status": "candidate_not_independently_reproduced",
                      "basin_count": len(observations), "metrics": metrics, "coverage_pass": coverage_pass,
                      "numerical_gate_pass": metrics["all_pairs_pass"] and coverage_pass,
                      "limitations": spec["limitations"], "input_identity": input_identity,
                      "method": "EarthEnv-DEM90 v1 -> 5x5 arithmetic mean -> native-polygon cell-center zones -> unweighted local cell mean. No spatial extrema or upstream attributes computed.",
                      "source_catalogue": "https://data.hydrosheds.org/file/technical-documentation/BasinATLAS_Catalog_v10.pdf#page=12",
                      "methods_paper": "https://pmc.ncbi.nlm.nih.gov/articles/PMC6901482/",
                      "scope_note": "Pskem candidate catchment IDs; gauge snapping remains unresolved. These are local native sub-basin values, not an exact gauge-catchment statistic."}
            timer.event(f"Comparison: {metrics['within_tolerance']}/{len(observations)} within {metrics['absolute_tolerance_m']} m; MAE={metrics['mae_m']:.3f} m")

        with timer.stage("export_and_provenance"):
            write_csv(directory / "observations.csv", observations)
            write_json(directory / "comparison.json", report)
            manifest = {"run_id": run_id, "attribute": args.attribute, "pilot": args.pilot,
                        "code_commit": git_commit, "code_snapshot": code, "python": sys.version,
                        "platform": platform.platform(), "package_versions": versions,
                        "command": ["python", "PIPELINES/run_atlas_attribute.py", "--attribute", args.attribute, "--pilot", args.pilot],
                        "source_lock": "source-lock.json", "source_lock_sha256": sha256(directory / "source-lock.json"),
                        "inputs": input_identity, "downloads": inputs,
                        "artifacts": [{"path": name, "sha256": sha256(directory / name)} for name in
                                      ("pilot-basins.geojson", "reference-values.json", "tolerance.json", "observations.csv", "comparison.json", "requirements.freeze.txt")],
                        "prepared_rasters": [{"path": str(p.relative_to(directory)), "sha256": sha256(p)} for *_, p in prepared],
                        "timing": "timing.json", "log": "processing.jsonl", "scientific_status": report["scientific_status"]}
            write_json(directory / "manifest.json", manifest)
        timing = timer.finish()
        # Publishing a small UI projection follows the measured scientific run.
        published = ROOT / "PUBLISHED/data/atlas/runs" / run_id
        published.mkdir(parents=True, exist_ok=False)
        for name in ("observations.csv", "comparison.json", "manifest.json", "timing.json", "source-lock.json", "tolerance.json"):
            (published / name).write_bytes((directory / name).read_bytes())
        summary = {**report, "timing": timing, "downloads": [{k: r[k] for k in ("name", "bytes", "cache_hit", "wall_seconds")} for r in inputs],
                   "report_url": f"/data/atlas/runs/{run_id}/comparison.json", "observations_url": f"/data/atlas/runs/{run_id}/observations.csv",
                   "timing_url": f"/data/atlas/runs/{run_id}/timing.json", "manifest_url": f"/data/atlas/runs/{run_id}/manifest.json",
                   "source_lock_url": f"/data/atlas/runs/{run_id}/source-lock.json"}
        write_json(ROOT / "PUBLISHED/data/atlas/latest-run.json", summary)
        publish_history()
        print(f"FULL PROCESSING WALL TIME: {timing['wall_seconds']:.3f} seconds; CPU: {timing['cpu_seconds']:.3f} seconds", flush=True)
        print(f"Run package: {directory}", flush=True)
        return summary
    except BaseException as error:
        timer.event(f"FAILED: {type(error).__name__}: {error}")
        timer.finish("failed")
        publish_history()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attribute", choices=["ele_mt_sav"], default="ele_mt_sav")
    parser.add_argument("--pilot", choices=["pskem"], default="pskem")
    parser.add_argument("--source-lock", type=Path, help="Verify exact inputs from an earlier run")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
