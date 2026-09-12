"""What the upstream accumulation reads before it routes anything downstream.

An upstream value is the area-weighted mean of the basin and everything above it, so
whatever is fed into the routing decides what the published attribute means. Two
things can go wrong before the first basin is walked: two sources derived under one
column name can be averaged into a number that is neither of them, and an abandoned
run's value can be preferred to a finished one. Both are tested here.
"""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import observations
from PIPELINES import accumulate_upstream_annuals as upstream

ANNUAL = dict(
    basin_id="4120380180", geometry_version="reg-1", basin_level=12,
    recipe_version="derive@abc", mode="annual_extension", spatial_support="s",
    time_kind="climatology", temporal_statistic="annual_climatological_figure",
    valid_start="2003-01-01", valid_end="2023-01-01", unit="degrees Celsius")


def stage(store, rows, runs):
    observations.append_partitioned(store, rows)
    observations.merge_table(store / "run.csv", runs, "run_id")


def value(column, release, run_id, number, **overrides):
    return observations.build(**{**ANNUAL, "attribute_id": f"hydrosheds.basinatlas.v1.{column}",
                                 "source_release_id": release, "run_id": run_id,
                                 "value": number, **overrides})


def run(run_id, started, status="complete"):
    return {"run_id": run_id, "started_at": started, "status": status}


def test_two_temperature_sources_are_routed_apart_not_averaged_together(tmp_path):
    stage(tmp_path, [value("tmp_dc_syr", "era5_temperature@x", "run-1", 8.0),
                     value("tmp_dc_syr", "terraclimate_temperature@y", "run-1", 9.5)],
          [run("run-1", "2026-09-12T00:00:00Z")])

    found, meta = upstream.local_values(tmp_path)
    basin = found["4120380180"]
    assert len(basin) == 2, "one column, two measurements, two things to accumulate"
    assert basin[("tmp_dc_syr", "era5_temperature@x")] == 8.0
    assert basin[("tmp_dc_syr", "terraclimate_temperature@y")] == 9.5
    assert {column for column, _ in meta} == {"tmp_dc_syr"}
    assert all(detail["unit"] == "degrees Celsius" for detail in meta.values())


def test_a_finished_run_is_accumulated_over_one_that_was_abandoned(tmp_path):
    # A re-run under a corrected method carries its own recipe, so both stay current.
    stage(tmp_path, [value("pre_mm_syr", "terraclimate@x", "partial", 300.0,
                           unit="millimetres per month", recipe_version="derive@old"),
                     value("pre_mm_syr", "terraclimate@x", "finished", 412.0,
                           unit="millimetres per month", recipe_version="derive@new")],
          [run("partial", "2026-09-11T00:00:00Z", status="incomplete"),
           run("finished", "2026-09-12T00:00:00Z")])

    found, _ = upstream.local_values(tmp_path)
    assert found["4120380180"][("pre_mm_syr", "terraclimate@x")] == 412.0


def test_a_column_with_no_upstream_counterpart_is_not_carried_downstream(tmp_path):
    stage(tmp_path, [value("tmp_dc_s01", "era5_temperature@x", "run-1", -6.0, month=1,
                           temporal_statistic="monthly_climatological_mean"),
                     value("tmp_dc_syr", "era5_temperature@x", "run-1", 8.0)],
          [run("run-1", "2026-09-12T00:00:00Z")])

    found, meta = upstream.local_values(tmp_path)
    assert {column for column, _ in meta} == {"tmp_dc_syr"}, "a January normal has no upstream pair"
    assert len(found["4120380180"]) == 1


def test_every_pair_names_an_upstream_column_of_the_same_family():
    for local, target in upstream.PAIRS.items():
        assert local[:3] == target[:3], f"{local} and {target} are different families"
        assert local[7] == "s" and target[7] == "u", "a local support feeds an upstream one"
    assert "pre_mm_uyr" in upstream.PAIRS.values(), "precipitation accumulates like the rest"
