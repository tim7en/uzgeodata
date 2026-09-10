"""The regional run's shape: batching, grid alignment, retries and resumability.

The extraction itself needs Earth Engine and is exercised by running it. What is
tested here is everything around it that decides whether a three-hour job can be
trusted: that no basin is dropped or counted twice when the work is cut up, that a
batch is reduced on the same lattice whatever subset it belongs to, that a failure
is recorded rather than swallowed, and that a rerun resumes instead of restarting.
"""
import json
import math
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIPELINES import extract_regional_snow as regional
from PIPELINES.extract_dated_snow import month_period


def frame(basins=530):
    """A stand-in for the level-12 frame: the same interface, a fraction of the size."""
    geopandas = pytest.importorskip("geopandas")
    from shapely.geometry import box
    ids = [4120000000 + index for index in range(basins)]
    boxes = [box(58 + index * 0.01, 40, 58 + index * 0.01 + 0.008, 40.008) for index in range(basins)]
    return geopandas.GeoDataFrame({"HYBAS_ID": ids}, geometry=boxes, crs="EPSG:4326")


def test_batching_covers_every_basin_exactly_once():
    source = frame(530)
    produced = list(regional.batches(source, 250))
    assert [index for index, _ in produced] == [0, 1, 2]
    assert [len(features) for _, features in produced] == [250, 250, 30]

    seen = [feature["properties"]["HYBAS_ID"] for _, features in produced for feature in features]
    assert len(seen) == len(source), "no basin is dropped when the work is cut up"
    assert len(set(seen)) == len(seen), "and none is counted twice"
    assert seen == sorted(source.HYBAS_ID.tolist()), "batches follow the frame's stable order"


def test_a_batch_carries_its_identity_and_its_geometry():
    _, features = next(iter(regional.batches(frame(3), 250)))
    assert {"geometry", "properties"} == set(features[0])
    assert isinstance(features[0]["properties"]["HYBAS_ID"], int)
    assert features[0]["geometry"]["type"] == "Polygon"


def test_every_subset_is_reduced_on_the_same_lattice():
    """Why a checkpoint from one run is valid in another: the origin moves with the
    subset, but always to a multiple of the cell size, so cell centres never shift."""
    whole = frame(530)
    for subset in (whole, whole.iloc[:100], whole.iloc[250:], whole.iloc[7:9]):
        transform = regional.regional_grid(subset)
        assert transform[0] == regional.CELL and transform[4] == -regional.CELL
        for origin in (transform[2], transform[5]):
            steps = origin / regional.CELL
            assert math.isclose(steps, round(steps), abs_tol=1e-6), f"{origin} is off-lattice"


def test_geometry_version_identifies_the_basin_set():
    whole = frame(20)
    assert regional.geometry_version(whole) == regional.geometry_version(whole), "deterministic"
    assert regional.geometry_version(whole) != regional.geometry_version(whole.iloc[:19]), \
        "a different set of basins is a different geometry version"
    assert regional.geometry_version(whole).startswith("reg-")


def test_a_transient_failure_is_retried_and_a_persistent_one_is_recorded(monkeypatch):
    monkeypatch.setattr(regional.time, "sleep", lambda seconds: None)
    ledger = {"retries": [], "failures": []}

    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError("Earth Engine is busy")
        return "recovered"

    value, error = regional.with_retries(flaky, "year-2003/batch-0", ledger)
    assert value == "recovered" and error is None
    assert len(ledger["retries"]) == 2, "each attempt that failed is recorded"
    assert not ledger["failures"], "a run that recovered did not fail"

    def broken():
        raise RuntimeError("quota exhausted")

    value, error = regional.with_retries(broken, "year-2004/batch-1", ledger)
    assert value is None and "quota exhausted" in error
    assert len(ledger["failures"]) == 1
    assert ledger["failures"][0]["target"] == "year-2004/batch-1"


def test_a_failure_is_never_silently_a_success():
    ledger = {"retries": [], "failures": []}
    value, error = regional.with_retries(lambda: (_ for _ in ()).throw(ValueError("nope")),
                                         "year-2003/batch-9", ledger)
    assert value is None and error, "the caller can tell the difference"
    assert ledger["failures"], "and the ledger says so"


def test_checkpoints_are_addressed_by_batch_and_year(tmp_path, monkeypatch):
    monkeypatch.setattr(regional, "CHECKPOINTS", tmp_path)
    first = regional.checkpoint_path(3, 2007)
    assert first != regional.checkpoint_path(3, 2008)
    assert first != regional.checkpoint_path(4, 2007)
    assert first.parent.name == "batch-0003" and first.name == "year-2007.json"

    first.parent.mkdir(parents=True)
    first.write_text(json.dumps([{"hybas_id": "1", "year": 2007}]), encoding="utf-8")
    assert first.exists(), "a finished batch-year is on disk before the next is attempted"
    assert json.loads(first.read_text(encoding="utf-8"))[0]["year"] == 2007


def test_a_december_period_rolls_into_the_next_year():
    assert month_period(2003, 12) == ("2003-12-01", "2004-01-01")
    assert month_period(2003, 1) == ("2003-01-01", "2003-02-01")
    assert month_period(2004, 2) == ("2004-02-01", "2004-03-01"), "the end is exclusive"


def rows_for(basins, nulls=0):
    rows = [{"hybas_id": str(index), "year": 2003, "month": month, "value": 40.0}
            for index in range(basins) for month in range(1, 13)]
    for row in rows[:nulls]:
        row["value"] = None
    return rows


def test_a_year_is_complete_only_when_every_basin_arrived():
    """The point of the ledger: a partial region must not read as a finished one."""
    whole = regional.summarise_year(rows_for(100), 100, 12.5)
    assert whole["complete"] and whole["rows"] == 1200 and whole["basins"] == 100

    short = regional.summarise_year(rows_for(97), 100, 12.5)
    assert not short["complete"], "three missing basins is not a finished year"
    assert short["basins"] == 97 and short["expected_basins"] == 100


def test_a_null_month_is_counted_as_missing_not_as_snow_free():
    summary = regional.summarise_year(rows_for(10, nulls=7), 10, 1.0)
    assert summary["rows"] == 120
    assert summary["null_months"] == 7
    assert summary["values"] == 113
    assert summary["values"] + summary["null_months"] == summary["rows"]
    assert summary["complete"], "a null month is still an answered basin-month"


def test_a_run_is_complete_only_when_nothing_failed_and_nothing_is_short():
    def ledger(**overrides):
        base = {"failures": [], "expected_rows": 2400, "stored_rows": 2400,
                "by_year": {"2003": regional.summarise_year(rows_for(100), 100, 1.0),
                            "2004": regional.summarise_year(rows_for(100), 100, 1.0)}}
        return {**base, **overrides}

    assert regional.is_complete(ledger())
    assert not regional.is_complete(ledger(failures=[{"target": "year-2003/batch-2"}])),         "a recorded failure keeps the run partial even if the rows happen to add up"
    assert not regional.is_complete(ledger(stored_rows=2399)), "a missing row is a partial run"
    assert not regional.is_complete(ledger(by_year={})), "a run that did nothing is not complete"
    short = ledger()
    short["by_year"]["2004"] = regional.summarise_year(rows_for(99), 100, 1.0)
    assert not regional.is_complete(short), "one short year makes the whole run partial"


def test_basin_support_reports_the_thin_tail_rather_than_hiding_it():
    """Most level-12 basins hold hundreds of cells; a few hold one. Both are published."""
    expected = {0: {"a": 835, "b": 900, "c": 1}, 1: {"d": 25, "e": 100, "f": 3}}
    summary = regional.support_summary(expected)
    assert summary["basins"] == 6
    assert summary["cells_min"] == 1 and summary["cells_max"] == 900
    assert summary["basins_at_or_below"]["1"] == 1
    assert summary["basins_at_or_below"]["5"] == 2
    assert summary["basins_at_or_below"]["25"] == 3
    assert summary["basins_at_or_below"]["100"] == 4
    assert summary["basins_without_a_cell"] == 0


def test_a_basin_with_no_cell_is_counted_not_quietly_dropped():
    summary = regional.support_summary({0: {"tiny": 0, "small": 2}})
    assert summary["basins_without_a_cell"] == 1
    assert summary["cells_min"] == 0
    assert regional.support_summary({}) == {}, "nothing measured, nothing claimed"
