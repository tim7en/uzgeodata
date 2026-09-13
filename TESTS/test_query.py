"""The analytical layer must answer with the store's rules, not around them.

A query engine applies no judgement of its own: it returns what the SQL asked for,
and a wrong answer is indistinguishable from a right one at the point of use. So what
is tested here is not that the filters work -- it is that the readings the store
exists to prevent stay prevented once a question is asked in SQL. A superseded value
is not current, an unfinished run is not evidence, a null is not a zero, and the two
spatial supports are never mixed.
"""
import json

import pytest

from ATLAS_MODULES.core import observations, query

pytest.importorskip("duckdb")

MONTHLY = dict(
    geometry_version="reg-1", basin_level=12, recipe_version="dated@abc",
    mode="annual_extension", spatial_support="s", time_kind="observation",
    temporal_statistic="monthly_mean", unit="millimetres per month",
    source_release_id="terraclimate@IDAHO_EPSCOR/TERRACLIMATE", run_id="done")


def month(basin, year, index, value, **overrides):
    end = (f"{year}-{index + 1:02d}-01" if index < 12 else f"{year + 1}-01-01")
    return observations.build(**{**MONTHLY, "basin_id": basin, "year": year, "month": index,
                                 "valid_start": f"{year}-{index:02d}-01", "valid_end": end,
                                 "attribute_id": "uzgeodata.dated.v1.pre_mm_s",
                                 "value": value,
                                 "missing_reason": None if value is not None else "no_value_in_source_for_month",
                                 **overrides})


def store_with(tmp_path, rows, runs=(("done", "complete"),), ledgers=()):
    observations.append_partitioned(tmp_path, rows)
    observations.merge_table(tmp_path / "run.csv", [
        {"run_id": name, "status": status, "started_at": "2026-01-01"} for name, status in runs],
        "run_id")
    for name, ledger in ledgers:
        (tmp_path / f"regional-{name}-ledger.json").write_text(
            json.dumps(ledger), encoding="utf-8")
    return tmp_path


def test_a_question_is_answered_for_the_basins_variables_and_months_it_names(tmp_path):
    rows = [month(basin, year, index, 10.0)
            for basin in ("4120000001", "4120000002")
            for year in (2003, 2004) for index in range(1, 13)]
    store = store_with(tmp_path, rows)

    everything = query.observations(store)
    assert len(everything) == 48

    one = query.observations(store, basins=["4120000001"])
    assert len(one) == 24 and {row[0] for row in one} == {"4120000001"}

    window = query.observations(store, start="2004-01", end="2004-06")
    assert len(window) == 12, "six months of two basins"
    assert all(row[2].year == 2004 and row[2].month <= 6 for row in window)

    assert query.observations(store, variables=["no.such.variable"]) == []


def test_a_null_month_is_returned_with_its_reason_and_never_as_a_zero(tmp_path):
    rows = [month("4120000001", 2003, index, None if index == 7 else 4.0) for index in range(1, 13)]
    store = store_with(tmp_path, rows)

    answered = query.observations(store)
    assert len(answered) == 12, "the gap is returned, not omitted"
    july = [row for row in answered if row[2].month == 7][0]
    assert july[3] is None, "a month with no observation must not arrive as a number"
    assert july[7] == "no_value_in_source_for_month", "and it says why"
    assert sum(1 for row in answered if row[3] == 0) == 0, "nothing was coalesced to zero"


def test_a_superseded_value_is_not_current(tmp_path):
    first = month("4120000001", 2003, 1, 5.0)
    corrected = observations.build(**{**first, "value": 9.0, "revision": 2,
                                      "supersedes": observations.row_key(first),
                                      "run_id": "done"})
    store = store_with(tmp_path, observations.append([first], [corrected]))

    answered = query.observations(store)
    assert [row[3] for row in answered] == [9.0], "the correction answers, the original does not"


def test_an_unfinished_run_is_not_evidence(tmp_path):
    rows = [month("4120000001", 2003, 1, 5.0),
            month("4120000002", 2003, 1, 6.0, run_id="halfway")]
    store = store_with(tmp_path, rows, runs=(("done", "complete"), ("halfway", "incomplete")))

    answered = query.observations(store)
    assert {row[0] for row in answered} == {"4120000001"}, "the abandoned run is excluded"


def test_a_finished_run_vouches_for_the_years_its_ledger_covered(tmp_path):
    # The resumed-extraction case: rows established by the interrupted run carry its
    # id, and only the ledger of the run that finished says the year was covered.
    rows = [month("4120000001", 2003, 1, 5.0, run_id="interrupted"),
            month("4120000001", 2004, 1, 6.0, run_id="finished")]
    store = store_with(
        tmp_path, rows,
        runs=(("finished", "complete"), ("interrupted", "incomplete")),
        ledgers=[("terraclimate", {"source": "terraclimate", "asset": "IDAHO_EPSCOR/TERRACLIMATE",
                                   "years": [2003, 2004], "complete": True})])

    answered = query.observations(store)
    assert len(answered) == 2, "the ledger covers 2003, so the earlier rows stand"
    assert {row[2].year for row in answered} == {2003, 2004}


def test_the_two_supports_are_never_mixed(tmp_path):
    local = month("4120000001", 2003, 1, 5.0)
    upstream = observations.build(**{**MONTHLY, "basin_id": "4120000001", "year": 2003, "month": 1,
                                     "valid_start": "2003-01-01", "valid_end": "2003-02-01",
                                     "attribute_id": "uzgeodata.dated.v1.pre_mm_s",
                                     "spatial_support": "u", "value": 40.0})
    store = store_with(tmp_path, [local, upstream])

    assert [row[3] for row in query.observations(store, support="s")] == [5.0]
    assert [row[3] for row in query.observations(store, support="u")] == [40.0]
    both = query.observations(store) + query.observations(store, support="u")
    assert len(both) == 2, "a caller must ask for one or the other, never a blend"


def test_the_store_reports_what_it_can_answer_for(tmp_path):
    rows = [month("4120000001", year, index, None if (year, index) == (2004, 5) else 3.0)
            for year in (2003, 2004) for index in range(1, 13)]
    store = store_with(tmp_path, rows)

    [entry] = query.available(store)
    attribute, unit, support, first, last, basins, observed, missing = entry
    assert attribute.endswith("pre_mm_s") and support == "s"
    assert (first.year, first.month) == (2003, 1)
    assert (last.year, last.month) == (2004, 12)
    assert basins == 1 and observed == 23 and missing == 1, "the gap is counted, not hidden"


def test_a_pilot_geometry_is_not_answered_as_a_regional_one(tmp_path):
    regional = month("4120000001", 2003, 1, 5.0)
    pilot = observations.build(**{**MONTHLY, "basin_id": "4120000001", "year": 2003, "month": 1,
                                  "valid_start": "2003-01-01", "valid_end": "2003-02-01",
                                  "attribute_id": "uzgeodata.dated.v1.pre_mm_s",
                                  "geometry_version": "pilot-1", "value": 99.0})
    store = store_with(tmp_path, [regional, pilot])

    assert [row[3] for row in query.observations(store)] == [5.0]
    assert [row[3] for row in query.observations(store, basins=None) if row[3] == 99.0] == []
