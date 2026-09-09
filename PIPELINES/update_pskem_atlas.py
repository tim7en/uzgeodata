"""Import all 281 original Pskem attributes and compare available source candidates.

python PIPELINES/update_pskem_atlas.py [--offline]
Never promotes numerical agreement to independent scientific reproduction.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core.runtime import RunTimer, sha256, write_json


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def csv_out(path, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(offline=False):
    run_id = "pskem-all281-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory = ROOT / "WORKSPACE/atlas_runs/hydrosheds" / run_id
    published = ROOT / "PUBLISHED/data/atlas"
    timer = RunTimer(run_id, directory, published / "batch-status.json")
    try:
        with timer.stage("original_reference_and_pilot_validation"):
            import numpy as np
            import pyogrio
            from ATLAS_MODULES.hydrosheds.functions.pilot_batch import (
                clean_value, physical_encoding, upstream_members, zones_for, reduce_field,
                climate_fields, worldclim_source, elevation_source, cell_areas,)
            from ATLAS_MODULES.hydrosheds.functions.pilot_batch import compare_candidate
            recipes = read(ROOT / "ATLAS_MODULES/hydrosheds/recipes.json")
            attributes = recipes["attributes"]
            assert len(attributes) == len({a["column"] for a in attributes}) == 281
            columns = [a["column"] for a in attributes]
            pilot_path = ROOT / "PUBLISHED/data/case-studies/pskem-candidate-catchment.geojson"
            pilot = read(pilot_path)
            ids = {int(f["properties"]["HYBAS_ID"]) for f in pilot["features"]}
            assert len(ids) == 20 and 4121289400 in ids
            gdb = ROOT / "GEODATA/BasinATLAS_Data_v10.gdb/BasinATLAS_Data_v10.gdb/BasinATLAS_v10.gdb"
            frame = pyogrio.read_dataframe(gdb, layer="BasinATLAS_v10_lev12", bbox=(69.7, 41.4, 71.5, 42.7))
            frame = frame[frame.HYBAS_ID.isin(ids)].sort_values("HYBAS_ID")
            assert len(frame) == 20 and set(frame.HYBAS_ID) == ids
            assert all(c in frame.columns for c in columns)
            if frame.crs.to_epsg() != 4326 or not frame.geometry.is_valid.all():
                raise ValueError("Original pilot geometry CRS or validity failed")
            # GeoDataFrame JSON retains Python numeric precision; do not round via GeoJSON drivers.
            features = json.loads(frame.to_json())["features"]
            write_json(directory / "pilot-basins.geojson", {"type": "FeatureCollection", "features": features})
            with (ROOT / "PUBLISHED/data/hydroclimate/basin-routing-level12.csv").open(encoding="utf-8") as stream:
                members = upstream_members(features, list(csv.DictReader(stream)))
            references = {c: {str(int(r.HYBAS_ID)): clean_value(r[c]) for _, r in frame.iterrows()} for c in columns}
            csv_out(directory / "reference-wide.csv", [{"hybas_id": bid, **{c: references[c][bid] for c in columns}} for bid in sorted(references[columns[0]])])
            spec_path = ROOT / "ATLAS_MODULES/hydrosheds/validation/pskem-batch.json"
            spec = read(spec_path)
            write_json(directory / "tolerance.json", spec)
            timer.event("Selected exactly 20 Pskem units and all 281 original attributes; upstream closure checked")

        with timer.stage("source_and_code_provenance"):
            catalogue = gdb.parent / "BasinATLAS_Catalog_v10.pdf"
            # Pin the complete original local database, including table/index files.
            database_files = [{"name": p.name, "bytes": p.stat().st_size, "sha256": sha256(p)}
                              for p in sorted(gdb.iterdir()) if p.is_file() and not p.name.endswith(".lock")]
            code = [Path(__file__), ROOT / "ATLAS_MODULES/core/runtime.py",
                    ROOT / "ATLAS_MODULES/hydrosheds/functions/pilot_batch.py",
                    ROOT / "ATLAS_MODULES/hydrosheds/functions/elevation.py",
                    ROOT / "ATLAS_MODULES/hydrosheds/recipes.json", ROOT / "ATLAS_MODULES/hydrosheds/sources.json"]
            code_hashes = {}
            for path in code:
                rel = path.relative_to(ROOT)
                target = directory / "code" / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                code_hashes[rel.as_posix()] = sha256(path)
            freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True, check=True)
            (directory / "requirements.freeze.txt").write_text(freeze.stdout, encoding="utf-8")
            lock = {"original_database": str(gdb.relative_to(ROOT)), "database_files": database_files,
                    "catalogue_sha256": sha256(catalogue), "pilot_selection_sha256": sha256(pilot_path),
                    "selected_geometry_sha256": sha256(directory / "pilot-basins.geojson"),
                    "reference_sha256": sha256(directory / "reference-wide.csv"),
                    "tolerance_sha256": sha256(spec_path), "code": code_hashes, "candidate_sources": {}}
            write_json(directory / "source-lock.json", lock)

        candidates, comparisons, attribute_seconds, failures = {}, {}, {}, {}
        for family in ("elevation", "worldclim"):
            try:
                with timer.stage(f"{family}_source_preparation"):
                    if family == "elevation":
                        cache = ROOT / "GEODATA/atlas_sources/earthenv_dem90_v1"
                        if offline and not (cache / "EarthEnv-DEM90_N40E070.tar.gz").exists():
                            raise FileNotFoundError("Original elevation archive not cached")
                        field, transform, source_record = elevation_source(features, cache, directory, timer)
                        fields = {c: field for c in columns if c.startswith("ele_")}
                    else:
                        monthly, transform, source_record, _ = worldclim_source(features, ROOT / "GEODATA/atlas_sources/worldclim_v1_pskem", timer, offline)
                        fields = climate_fields(monthly)
                    zones = zones_for(features, transform, next(iter(fields.values())).shape)
                    areas = np.broadcast_to(cell_areas(transform, zones.shape[0])[:, None], zones.shape)
                    lock["candidate_sources"][family] = source_record
                    write_json(directory / "source-lock.json", lock)
                with timer.stage(f"{family}_attributes_one_by_one"):
                    for column, field in sorted(fields.items()):
                        start = time.perf_counter()
                        support = column.split("_")[2][0]
                        statistic = "minimum" if column == "ele_mt_smn" else "maximum" if column == "ele_mt_smx" else "mean"
                        result = reduce_field(field, features, zones, areas, members, support, statistic)
                        comparison = compare_candidate(references[column], result, spec["comparison_rules"][column[:3]]["absolute_tolerance_raw"])
                        candidates[column], comparisons[column] = result, comparison
                        attribute_seconds[column] = time.perf_counter() - start
                        timer.event(f"{column}: {comparison['within_tolerance']}/20 within tolerance", attribute=column,
                                    attribute_wall_seconds=attribute_seconds[column])
            except Exception as error:
                failures[family] = f"{type(error).__name__}: {error}"
                timer.event(f"{family} candidates unavailable; reference baseline retained", reason=failures[family])

        with timer.stage("all_281_attribute_audit_and_export"):
            rows, ledger = [], []
            functions = {f["id"]: f for f in recipes["functions"]}
            for attribute in attributes:
                c = attribute["column"]
                factor, physical_unit = physical_encoding(c, attribute["units"])
                candidate = candidates.get(c)
                reason = ("Original vector zones rasterized at 15 arc-seconds need equivalence review against the native atlas zone grid. "
                          + ("WorldClim V1 mirror needs exact v1.4 vintage review. " if c.startswith(("tmp_", "pre_")) else "")
                          + ("Upstream union of unique basin zones needs comparison with original pixel flow accumulation. " if attribute["spatial_support"] == "u" else "")
                          + "Independent operator rerun pending.") if candidate else "Original raw inputs not acquired in this pass; source preparation and validation remain pending."
                entry = {**attribute, "source_dataset": functions[attribute["function"]]["source"]["dataset"],
                         "source_citation": functions[attribute["function"]]["source"]["citation"],
                         "reference_status": "original_reference_import", "reference_values": references[c],
                         "reference_nonmissing": sum(v is not None for v in references[c].values()),
                         "candidate_status": "computed_candidate" if candidate else "pending_original_inputs",
                         "comparison": comparisons.get(c), "candidate_values": candidate,
                         "scientifically_reproduced": False, "review_required": reason,
                         "physical_factor": factor, "physical_unit": physical_unit,
                         "calculation_wall_seconds": attribute_seconds.get(c)}
                ledger.append(entry)
                for bid, value in references[c].items():
                    result = candidate.get(bid) if candidate else None
                    rows.append({"run_id": run_id, "hybas_id": bid, "attribute": c,
                                 "reference_raw": value, "stored_unit": attribute["units"],
                                 "reference_physical": value * factor if value is not None else None,
                                 "physical_unit": physical_unit, "physical_factor": factor,
                                 "candidate_raw": result["raw_value"] if result else None,
                                 "candidate_status": entry["candidate_status"],
                                 "coverage_fraction": result["coverage_fraction"] if result else None,
                                 "reference_period": attribute["reference_period"], "observation_year": None,
                                 "spatial_support": attribute["spatial_support"], "source_url": attribute["source_url"],
                                 "scientifically_reproduced": False})
            assert len(rows) == 5620
            csv_out(directory / "observations.csv", rows)
            csv_out(directory / "attribute-audit.csv", [{k: a[k] for k in ("column", "source_dataset", "source_citation", "source_url", "units", "reference_period", "spatial_support", "reference_nonmissing", "candidate_status", "review_required", "calculation_wall_seconds")} for a in ledger])
            summary = {"run_id": run_id, "pilot": "pskem", "basin_count": 20, "attribute_count": 281,
                       "reference_records": len(rows), "reference_nonmissing": sum(r["reference_raw"] is not None for r in rows),
                       "candidate_attributes": len(candidates), "numerical_pass_attributes": sum(c["pass"] for c in comparisons.values()),
                       "pending_attributes": 281 - len(candidates), "independently_reproduced": 0,
                       "scope_note": "Pskem candidate catchment: 20 complete level-12 units, outlet 4121289400. Gauge-to-reach placement still requires review.",
                       "status_note": "Original-vintage reference import plus independent source candidates. Numerical agreement is not scientific reproduction. No annual observations are inferred.",
                       "failures": failures, "attributes": ledger, "basin_ids": sorted(str(i) for i in ids),
                       "download_base": f"/data/atlas/runs/{run_id}/"}
            write_json(directory / "batch.json", summary)
            write_json(directory / "manifest.json", {"run_id": run_id, "python": platform.python_version(),
                       "platform": platform.platform(), "command": "python PIPELINES/update_pskem_atlas.py" + (" --offline" if offline else ""),
                       "mode": spec["mode"], "scientific_release": "not_eligible", "files": {
                           p.name: sha256(p) for p in directory.iterdir() if p.is_file() and p.name not in ("timing.json", "processing.jsonl")}})
        timing = timer.finish("complete_with_pending_reproduction" if not failures else "partial_source_failure")
        destination = published / "runs" / run_id
        destination.mkdir(parents=True, exist_ok=False)
        for name in ("batch.json", "observations.csv", "reference-wide.csv", "attribute-audit.csv", "pilot-basins.geojson", "manifest.json", "source-lock.json", "tolerance.json", "timing.json", "requirements.freeze.txt"):
            shutil.copy2(directory / name, destination / name)
        summary["timing"] = timing
        write_json(published / "batch-latest.json", summary)
        from PIPELINES.run_atlas_attribute import publish_history
        publish_history()
        print(json.dumps({k: summary[k] for k in ("run_id", "reference_records", "candidate_attributes", "numerical_pass_attributes", "pending_attributes", "failures")}, indent=2))
        print(f"Full scientific processing wall time: {timing['wall_seconds']:.3f}s")
        return summary
    except BaseException:
        timer.finish("failed")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Require cached candidate source rasters")
    run(parser.parse_args().offline)
