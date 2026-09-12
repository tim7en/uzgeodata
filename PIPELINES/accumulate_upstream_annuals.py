"""Form the upstream annual attributes from the local ones already in the store.

python PIPELINES/accumulate_upstream_annuals.py

Six attributes are the upstream counterparts of annual figures that were derived
locally from the dated series. Nothing needs fetching for them: an upstream value is
the area-weighted mean of the basin and everything draining through it, which the
routing graph already answers.

Aggregating area-weighted basin means by area gives the same result as the
cell-level area-weighted mean, so this matches what the pilot computes rather than
approximating it. That holds for the ratios too -- moisture index and aridity are
averaged as fields here, exactly as the pilot averages them, and not recomputed as a
ratio of upstream totals. Those are different quantities, and the one the published
attribute means is this one.
"""
from __future__ import annotations
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
from PIPELINES.extract_regional_landcover import order_and_areas
from PIPELINES.extract_regional_means import Weighted, walk
from PIPELINES.extract_regional_snow import geometry_version, load_frame
from PIPELINES.stage_pilot_observations import BASIN_LEVEL, STORE

# local annual column -> the upstream column it feeds
PAIRS = {
    "aet_mm_syr": "aet_mm_uyr",
    "pet_mm_syr": "pet_mm_uyr",
    "swc_pc_syr": "swc_pc_uyr",
    "cmi_ix_syr": "cmi_ix_uyr",
    "ari_ix_sav": "ari_ix_uav",
    "snw_pc_syr": "snw_pc_uyr",
}


def local_values(store):
    """The derived local annual figures, with the metadata they were written under."""
    found, meta = collections.defaultdict(dict), {}
    for row in observations.read_partitions(store / "time_kind=climatology"):
        column = row["attribute_id"].split(".")[-1]
        if column not in PAIRS or not row["geometry_version"].startswith("reg-"):
            continue
        found[row["basin_id"]][column] = row["value"]
        meta[column] = {"unit": row["unit"], "valid_start": row["valid_start"],
                        "valid_end": row["valid_end"], "source": row["source_release_id"]}
    return found, meta


def build(store=STORE):
    frame = load_frame()
    version = geometry_version(frame)
    below, areas = order_and_areas(frame)
    local, meta = local_values(store)
    if not local:
        raise ValueError("no derived local annual values found; run the derivation first")

    missing_inputs = sorted(set(PAIRS) - set(meta))
    upstream = walk(local, below, areas, Weighted)

    identifier = f"upstream-annuals-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}Z"
    recipe = f"upstream_annuals@{sha256(Path(__file__))[:12]}"
    started, at = time.perf_counter(), utc_now()

    built, empty = [], 0
    for basin, values in upstream.items():
        for source_column, target in PAIRS.items():
            if source_column not in meta:
                continue
            value = values.get(source_column)
            empty += value is None
            detail = meta[source_column]
            built.append(observations.build(
                basin_id=basin, geometry_version=version, basin_level=BASIN_LEVEL,
                attribute_id=f"hydrosheds.basinatlas.v1.{target}", recipe_version=recipe,
                mode="annual_extension", spatial_support="u", time_kind="climatology",
                temporal_statistic="annual_climatological_figure",
                valid_start=detail["valid_start"], valid_end=detail["valid_end"],
                value=value, unit=detail["unit"],
                quality_flag="derived_from_dated_observations",
                missing_reason=None if value is not None else "no_upstream_value_available",
                source_release_id=detail["source"], run_id=identifier,
                retrieved_at=at, recorded_at=at))
    added, _ = observations.append_partitioned(store, built)

    summary = {
        "run_id": identifier, "recipe_version": recipe, "generated_at": at,
        "basins": len(upstream), "rows": len(built), "new_rows": added,
        "without_value": empty,
        "attributes": sorted({r["attribute_id"].split(".")[-1] for r in built}),
        "inputs_missing": missing_inputs,
        "wall_seconds": time.perf_counter() - started,
        "method": "Area-weighted mean over the basin and everything draining into it, "
                  "accumulated through the published routing so each basin is counted once. "
                  "Ratios are averaged as fields, matching the published attribute, not "
                  "recomputed from upstream totals.",
    }
    write_json(store / "regional-upstream-annuals.json", summary)
    observations.merge_table(store / "run.csv", [{
        "run_id": identifier, "started_at": at, "finished_at": utc_now(),
        "wall_seconds": summary["wall_seconds"], "status": "complete",
        "scientific_release": "not_eligible"}], "run_id")
    observations.merge_table(store / "recipe.csv", [
        {"recipe_version": recipe, "mode": "annual_extension"}], "recipe_version")
    return summary


def main():
    print(json.dumps(build(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
