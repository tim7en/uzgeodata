"""Stage the frozen Pskem run into the append-only observation store.

python PIPELINES/stage_pilot_observations.py

This is the first batch of stage 5: adopt the observation/revision contract and
place the evidence that already exists inside it. It computes nothing new. Every
row is read from a published run package and carries the source release, method
and geometry it came from.

No observation year is invented. This run holds no dated observations at all: its
values are static attributes, source epochs and climatologies, and they are
written as such. A January climatology drawn from 2003-2023 MODIS imagery keeps
that window as its valid period and stays a climatology; it does not become
twenty Januaries. A land-cover class code such as `glc_pc_s01` is class 1 and is
never recorded as a calendar month.

Attributes whose family has no pinned source release in this run are left out
rather than written as sourceless nulls; the run's own coverage report already
names them, and the manifest counts them here.
"""
from __future__ import annotations
from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import observations
from ATLAS_MODULES.core.runtime import write_json

PUBLISHED = ROOT / "PUBLISHED/data/atlas"
STORE = PUBLISHED / "observations"
BASIN_LEVEL = 12

# Which pinned candidate source each independently computed variable came from.
CANDIDATE_SOURCES = {"ele": "elevation", "tmp": "worldclim", "pre": "worldclim"}

TIME_KINDS = {"static_or_reference": "static", "source_epoch": "source_epoch",
              "climatology": "climatology"}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def latest_run(published=PUBLISHED):
    batch = read(published / "batch-latest.json")
    return batch, read(published / "runs" / batch["run_id"] / "source-lock.json")


def source_period(entry):
    """Only periods the run actually pinned. An unpinned source stays undated."""
    for key in ("climatology", "period"):
        window = entry.get(key)
        if isinstance(window, list) and len(window) == 2:
            return window[0], window[1]
    epoch = entry.get("epoch")
    if epoch and str(epoch)[:4].isdigit():
        year = int(str(epoch)[:4])
        return f"{year:04d}-01-01", f"{year + 1:04d}-01-01"
    return None, None


def release_id(name, digest):
    return f"{name}@{digest[:12]}" if digest else f"{name}@unpinned"


def temporal_statistic(time_kind, month):
    if time_kind == "climatology":
        return "monthly_climatological_mean" if month else "long_term_climatological_mean"
    return "epoch_snapshot" if time_kind == "source_epoch" else "time_invariant"


def calendar_month(attribute, time_kind):
    """A two-digit dimension is a month only in a climatology; elsewhere it is a class."""
    dimension = attribute["dimension"]
    if time_kind == "climatology" and dimension.isdigit() and 1 <= int(dimension) <= 12:
        return int(dimension)
    return None


def recipe_version(name, code):
    digest = code.get("ATLAS_MODULES/hydrosheds/functions/pilot_batch.py", "")
    return f"{name}@{digest[:12]}" if digest else name


def measured(entry):
    """A per-basin result carries its value and its own QA denominators."""
    return {"value": entry.get("raw_value"), "coverage_fraction": entry.get("coverage_fraction"),
            "valid_count": entry.get("valid_cells"), "expected_count": entry.get("expected_cells")}


def build_rows(batch, lock):
    """One row per basin, attribute and value role, from the frozen run only."""
    geometry_version = lock["selected_geometry_sha256"][:16]
    code, recorded_at = lock.get("code", {}), batch["timing"]["updated_at"]
    reference_release = release_id("basinatlas_v10", lock.get("catalogue_sha256", ""))
    families, rows, skipped = batch["surrogate_families"], [], []

    def common(attribute, time_kind, month):
        return {"geometry_version": geometry_version, "basin_level": BASIN_LEVEL,
                "attribute_id": attribute["id"], "spatial_support": attribute["spatial_support"],
                "time_kind": time_kind, "month": month,
                "temporal_statistic": temporal_statistic(time_kind, month),
                "run_id": batch["run_id"], "recorded_at": recorded_at}

    for attribute in batch["attributes"]:
        time_kind = TIME_KINDS[attribute["time_kind"]]
        month = calendar_month(attribute, time_kind)
        shared = common(attribute, time_kind, month)

        # The published atlas value, imported exactly as released.
        for basin_id, value in attribute["reference_values"].items():
            rows.append(observations.build(
                **shared, basin_id=basin_id, mode="reference_import",
                recipe_version=recipe_version("import.basinatlas.v10", code),
                source_release_id=reference_release, value=value, unit=attribute["units"],
                quality_flag=attribute["reference_status"],
                missing_reason=None if value is not None else "missing_in_published_atlas"))

        # Independently recomputed originals, still candidates until reproduced.
        if attribute["candidate_values"]:
            source = CANDIDATE_SOURCES.get(attribute["variable"])
            entry = lock.get("candidate_sources", {}).get(source, {})
            for basin_id, result in attribute["candidate_values"].items():
                rows.append(observations.build(
                    **shared, basin_id=basin_id, mode="baseline_reproduction_candidate",
                    recipe_version=recipe_version(attribute["function"], code),
                    source_release_id=release_id(source or "unresolved", entry.get("sha256", "")),
                    unit=attribute["physical_unit"], quality_flag=attribute["candidate_status"],
                    missing_reason=None, **measured(result)))

        # Open-data estimates. Only families with a pinned source release qualify.
        family = families[attribute["surrogate_family"]]
        entry = lock.get("surrogate_sources", {}).get(family.get("builder"))
        if entry is None:
            skipped.append(attribute["column"])
            continue
        valid_start, valid_end = source_period(entry)
        pending = attribute["surrogate_pending_reason"] or attribute["surrogate_status"]
        for basin_id in batch["basin_ids"]:
            result = (attribute["surrogate_values"] or {}).get(basin_id)
            values = measured(result) if result else {"value": None}
            rows.append(observations.build(
                **shared, basin_id=basin_id, mode="annual_extension",
                recipe_version=recipe_version(family["builder"], code),
                source_release_id=release_id(family["builder"], entry.get("sha256", "")),
                valid_start=valid_start, valid_end=valid_end,
                unit=family["units"]["surrogate"], quality_flag=attribute["surrogate_status"],
                retrieved_at=entry.get("retrieved_at"),
                missing_reason=None if values["value"] is not None else pending, **values))
    return rows, sorted(skipped)


def side_tables(batch, lock, rows):
    """The versioned tables the observations point at, written beside them."""
    geometry_version = lock["selected_geometry_sha256"][:16]
    used = {record["source_release_id"] for record in rows}
    releases = [{"source_release_id": release_id("basinatlas_v10", lock.get("catalogue_sha256", "")),
                 "name": "BasinATLAS v10", "asset": lock["original_database"],
                 "sha256": lock.get("catalogue_sha256", ""), "epoch": "", "valid_start": "",
                 "valid_end": "", "retrieved_at": "", "pinned": True}]
    for name, entry in lock.get("candidate_sources", {}).items():
        start, end = source_period(entry)
        releases.append({"source_release_id": release_id(name, entry.get("sha256", "")),
                         "name": entry.get("name", name), "asset": entry.get("url", ""),
                         "sha256": entry.get("sha256") or "", "epoch": entry.get("epoch") or "",
                         "valid_start": start or "", "valid_end": end or "",
                         "retrieved_at": entry.get("retrieved_at") or "",
                         "pinned": bool(entry.get("sha256"))})
    for name, entry in lock.get("surrogate_sources", {}).items():
        start, end = source_period(entry)
        releases.append({"source_release_id": release_id(name, entry.get("sha256", "")),
                         "name": name, "asset": entry.get("asset", ""),
                         "sha256": entry.get("sha256") or "", "epoch": entry.get("epoch") or "",
                         "valid_start": start or "", "valid_end": end or "",
                         "retrieved_at": entry.get("retrieved_at") or "",
                         "pinned": bool(entry.get("sha256"))})
    releases = [r for r in releases if r["source_release_id"] in used]

    geometry = [{"geometry_version": geometry_version, "basin_level": BASIN_LEVEL,
                 "basin_count": len(batch["basin_ids"]),
                 "sha256": lock["selected_geometry_sha256"], "scope": batch["scope_note"]}]
    runs = [{"run_id": batch["run_id"], "started_at": batch["timing"]["started_at"],
             "finished_at": batch["timing"]["updated_at"],
             "wall_seconds": batch["timing"]["wall_seconds"],
             "status": batch["timing"]["status"], "scientific_release": "not_eligible"}]
    recipes = sorted({(record["recipe_version"], record["mode"]) for record in rows})
    recipes = [{"recipe_version": version, "mode": mode} for version, mode in recipes]
    return {"source_release": releases, "basin_geometry": geometry, "run": runs, "recipe": recipes}


def stage(store=STORE, published=PUBLISHED):
    batch, lock = latest_run(published)
    rows, skipped = build_rows(batch, lock)
    # Only the partitions this run writes are read and rewritten. The store also
    # holds dated series far too large to load on every publish.
    observations.append_partitioned(store, rows)
    keys = {"source_release": "source_release_id", "basin_geometry": "geometry_version",
            "run": "run_id", "recipe": "recipe_version"}
    for name, table in side_tables(batch, lock, rows).items():
        observations.merge_table(Path(store) / f"{name}.csv", table, keys[name])

    totals = observations.summarise(store)
    counts = totals["by_mode"]
    summary = {
        "schema_version": 1,
        "generated_from_run": batch["run_id"],
        "contract": "ATLAS_MODULES/core/REPRODUCIBILITY.md",
        "fields": list(observations.FIELDS),
        "rows": totals["rows"],
        "staged_from_this_run": len(rows),
        "current_rows": totals["current_rows"],
        "by_mode": counts,
        "by_time_kind": {kind: totals["by_time_kind"].get(kind, 0) for kind in observations.TIME_KINDS},
        "dated_observations": totals["dated_observations"],
        "attribute_count": len(totals["attributes"]),
        "dated_attributes": [a for a in totals["attributes"] if a.startswith("uzgeodata.dated.")],
        "missing_values": totals["missing_values"],
        "basins": len(batch["basin_ids"]),
        "basin_level": BASIN_LEVEL,
        "attributes_without_pinned_source": len(skipped),
        "note": "Counts describe the whole store. The frozen HydroATLAS run staged here "
                "contributes no dated observation and none is invented for it: its values are "
                "static attributes, source epochs and climatologies. Dated rows come from the "
                "dated adapters, each with its own manifest. Partitioned CSV is a staging "
                "format; the production physical design stays open until benchmarked.",
    }
    write_json(Path(store) / "manifest.json", summary)
    return summary


def main():
    summary = stage()
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
