"""Independent numeric fixtures for the first pilot attribute and run accounting."""
import importlib.util
from pathlib import Path
import sys
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.hydrosheds.functions.elevation import aggregate_5x5, zonal_statistics, merge_statistics
from ATLAS_MODULES.core.runtime import RunTimer


def test_native_mean_before_basin_mean_and_missing_support():
    native = np.zeros((5, 10))
    native[:, :5] = 100
    native[:, 5:] = 300
    native[0, 0] = 200
    means, counts = aggregate_5x5(native)
    assert means.tolist() == [[104, 300]]
    assert counts.tolist() == [[25, 25]]
    native[0, 0] = np.nan
    means, counts = aggregate_5x5(native)
    assert means.tolist() == [[100, 300]]
    assert counts.tolist() == [[24, 25]]
    native[:, :5] = np.nan
    means, counts = aggregate_5x5(native)
    assert np.isnan(means[0, 0]) and counts[0, 0] == 0


def test_local_mean_is_not_latitude_weighted_and_nodata_is_not_zero():
    # Two rows of different area: local mean 200; weighted mean 250.
    stats = zonal_statistics(np.array([[100., 999.], [300., np.nan]]),
                             np.array([[1, 0], [1, 2]]), np.array([1., 3.]), 2)
    assert stats["sum_m"][1] / stats["valid_cells"][1] == 200
    assert stats["weighted_sum_m_m2"][1] / stats["valid_area_m2"][1] == 250
    assert stats["valid_cells"][2] == 0 and stats["total_cells"][2] == 1
    assert stats["sum_m"][1] == 400  # outside-of-zone 999 was excluded


def test_cross_tile_aggregation_uses_counts_not_mean_of_means():
    first = zonal_statistics(np.array([[10.]]), np.array([[1]]), np.array([1.]), 1)
    second = zonal_statistics(np.array([[40., 40.]]), np.array([[1, 1]]), np.array([1.]), 1)
    total = merge_statistics(first, second)
    assert total["sum_m"][1] / total["valid_cells"][1] == 30


def test_timing_failure_and_nonoverlapping_stages(tmp_path):
    timer = RunTimer("test-run", tmp_path / "run")
    with timer.stage("first"):
        with pytest.raises(RuntimeError, match="overlap"):
            with timer.stage("nested"):
                pass
    with pytest.raises(ValueError):
        with timer.stage("second"):
            raise ValueError("test failure")
    timing = timer.finish("failed")
    assert timing["status"] == "failed"
    assert timing["stages"][1]["status"] == "failed"
    assert sum(s["wall_seconds"] for s in timing["stages"]) <= timing["wall_seconds"]
    assert timing["overhead_seconds"] >= 0


def test_comparison_rejects_missing_and_out_of_tolerance():
    spec = importlib.util.spec_from_file_location("run_atlas", ROOT / "PIPELINES/run_atlas_attribute.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    comparison = runner.compare([{"value_m": 10, "reference_m": 10}, {"value_m": 12, "reference_m": 10},
                                 {"value_m": None, "reference_m": 10}], {"absolute_tolerance_m": 1})
    assert comparison["count"] == 2 and comparison["missing_pairs"] == 1
    assert comparison["within_tolerance"] == 1 and not comparison["all_pairs_pass"]
