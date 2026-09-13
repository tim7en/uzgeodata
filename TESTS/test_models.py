"""A model is where a number stops being evidence, so these test the refusals.

Every case here is a way a model can report skill it has not earned: scored on what it
was fitted to, scored on a handful of months, scored against nothing, fitted to a
catchment two thirds of which was missing, or credited for reproducing a seasonal cycle
a calendar could have supplied. None of them raise on their own. Each produces a
plausible number and a chart to go with it.
"""
import math

import pytest

from ATLAS_MODULES.core import models, observations

pytest.importorskip("duckdb")
pytest.importorskip("numpy")

MONTHLY = dict(
    geometry_version="reg-1", basin_level=12, recipe_version="dated@abc",
    mode="annual_extension", spatial_support="s", time_kind="observation",
    temporal_statistic="monthly_mean", unit="millimetres per month",
    source_release_id="terraclimate@IDAHO_EPSCOR/TERRACLIMATE", run_id="done")


def observation(basin, year, month, value, attribute="uzgeodata.dated.v1.pre_mm_s", **extra):
    end = f"{year}-{month + 1:02d}-01" if month < 12 else f"{year + 1}-01-01"
    return observations.build(**{**MONTHLY, "basin_id": basin, "year": year, "month": month,
                                 "valid_start": f"{year}-{month:02d}-01", "valid_end": end,
                                 "attribute_id": attribute, "value": value,
                                 "missing_reason": None if value is not None
                                                   else "no_value_in_source_for_month",
                                 **extra})


def store_with(tmp_path, rows):
    observations.append_partitioned(tmp_path, rows)
    observations.merge_table(tmp_path / "run.csv",
                             [{"run_id": "done", "status": "complete", "started_at": "2026-01-01"}],
                             "run_id")
    return tmp_path


def seasonal_record(tmp_path, basins=("4120000001",), years=range(2003, 2018)):
    """A record with a strong, clean annual cycle in rain and temperature."""
    rows = []
    for basin in basins:
        for year in years:
            for month in range(1, 13):
                swing = math.cos((month - 1) / 12 * 2 * math.pi)
                rows.append(observation(basin, year, month, 60.0 - 40.0 * swing))
                rows.append(observation(basin, year, month, 15.0 - 15.0 * swing,
                                        attribute="uzgeodata.dated.v1.tmx_dc_s",
                                        unit="degrees Celsius"))
    return store_with(tmp_path, rows)


def target_from(years, function):
    return {(year, month): function(year, month)
            for year in years for month in range(1, 13)}


def test_a_score_on_the_training_period_is_refused(tmp_path):
    store = seasonal_record(tmp_path)
    target = target_from(range(2003, 2018), lambda year, month: 10.0 + month)
    with pytest.raises(models.NotEnoughEvidence, match="overlaps"):
        models.fit(store, ["4120000001"], target, ["precipitation"],
                   train=("2003-01", "2012-12"), evaluate=("2010-01", "2017-12"))


def test_an_open_ended_period_cannot_be_checked_and_is_refused(tmp_path):
    store = seasonal_record(tmp_path)
    target = target_from(range(2003, 2018), lambda year, month: 10.0 + month)
    with pytest.raises(models.NotEnoughEvidence, match="explicit"):
        models.fit(store, ["4120000001"], target, ["precipitation"],
                   train=(None, "2012-12"), evaluate=("2013-01", "2017-12"))


def test_too_few_held_out_months_yield_no_score(tmp_path):
    store = seasonal_record(tmp_path)
    target = target_from(range(2003, 2018), lambda year, month: 10.0 + month)
    with pytest.raises(models.NotEnoughEvidence, match="months held out"):
        models.fit(store, ["4120000001"], target, ["precipitation"],
                   train=("2003-01", "2012-12"), evaluate=("2013-01", "2013-12"))


def test_a_model_that_only_learned_the_seasons_is_caught_by_the_climatology_score(tmp_path):
    """The failure this whole layer exists to catch.

    The target is the seasonal cycle plus noise that no predictor carries. A fit on the
    cycle reproduces it well, so Nash-Sutcliffe against the evaluation mean looks
    respectable -- and against the calendar-month means, which needed no model at all,
    it has added nothing.
    """
    store = seasonal_record(tmp_path)
    wobble = [0.0, 6.0, -6.0, 3.0, -3.0, 5.0, -5.0, 2.0, -2.0, 4.0, -4.0, 1.0, 0.0, 7.0, -7.0]
    target = {(year, month): 100.0 - 80.0 * math.cos((month - 1) / 12 * 2 * math.pi)
                             + wobble[year - 2003]
              for year in range(2003, 2018) for month in range(1, 13)}

    report = models.fit(store, ["4120000001"], target, ["precipitation", "maximum temperature"],
                        train=("2003-01", "2012-12"), evaluate=("2013-01", "2017-12"))
    assert report["skill"]["nash_sutcliffe"] > 0.8, "against the mean it looks like a model"
    assert report["skill"]["skill_against_climatology"] < 0.05, \
        "against the calendar it has added nothing, and that is the number that matters"


def test_a_month_missing_one_predictor_is_dropped_rather_than_filled(tmp_path):
    rows = []
    for year in range(2003, 2006):
        for month in range(1, 13):
            rows.append(observation("4120000001", year, month, 20.0))
            # Temperature is absent for one month only.
            if not (year == 2004 and month == 6):
                rows.append(observation("4120000001", year, month, 12.0,
                                        attribute="uzgeodata.dated.v1.tmx_dc_s",
                                        unit="degrees Celsius"))
    store = store_with(tmp_path, rows)

    block = models.predictors(store, ["4120000001"], ["precipitation", "maximum temperature"])
    assert block["dropped_months"] == 1
    assert (2004, 6) not in block["months"], "a half-observed month is not a row"
    assert len(block["matrix"]) == 35


def test_a_null_predictor_is_not_read_as_a_zero(tmp_path):
    rows = [observation("4120000001", 2003, month, None if month == 4 else 20.0)
            for month in range(1, 13)]
    store = store_with(tmp_path, rows)
    block = models.predictors(store, ["4120000001"], ["precipitation"])
    assert block["dropped_months"] == 1
    assert all(value != [0.0] for value in block["matrix"]), "no month entered the fit as zero"


def test_a_catchment_mean_weights_by_area(tmp_path):
    rows = []
    for month in range(1, 13):
        rows.append(observation("4120000001", 2003, month, 100.0))
        rows.append(observation("4120000002", 2003, month, 0.0))
    store = store_with(tmp_path, rows)

    block = models.predictors(store, ["4120000001", "4120000002"], ["precipitation"],
                              weights={"4120000001": 900.0, "4120000002": 100.0})
    assert block["matrix"][0][0] == pytest.approx(90.0), \
        "the basin covering nine tenths of the area carries nine tenths of the mean"

    even = models.predictors(store, ["4120000001", "4120000002"], ["precipitation"])
    assert even["matrix"][0][0] == pytest.approx(50.0), "unweighted, they count alike"


def test_a_basin_with_no_area_is_refused_rather_than_dropped(tmp_path):
    store = seasonal_record(tmp_path, basins=("4120000001", "4120000002"))
    with pytest.raises(models.NotEnoughEvidence, match="no weight"):
        models.predictors(store, ["4120000001", "4120000002"], ["precipitation"],
                          weights={"4120000001": 1.0})


def test_a_catchment_month_missing_a_basin_is_dropped(tmp_path):
    """Two thirds of a catchment is not a catchment, and the mean would not say so."""
    rows = []
    for month in range(1, 13):
        rows.append(observation("4120000001", 2003, month, 30.0))
        if month != 7:
            rows.append(observation("4120000002", 2003, month, 60.0))
    store = store_with(tmp_path, rows)

    block = models.predictors(store, ["4120000001", "4120000002"], ["precipitation"])
    assert block["dropped_months"] == 1
    assert (2003, 7) not in block["months"]
    assert all(row[0] == pytest.approx(45.0) for row in block["matrix"]), \
        "no month averaged over only the basin that reported"


def test_more_parameters_than_observations_is_refused(tmp_path):
    store = seasonal_record(tmp_path)
    target = {(2003, month): 10.0 for month in (1, 2)}
    target.update({(year, month): 10.0 for year in range(2013, 2018) for month in range(1, 13)})
    with pytest.raises(models.NotEnoughEvidence, match="training months"):
        models.fit(store, ["4120000001"], target, ["precipitation", "maximum temperature"],
                   train=("2003-01", "2012-12"), evaluate=("2013-01", "2017-12"))


def test_skill_refuses_a_reference_with_a_hole_in_it(tmp_path):
    with pytest.raises(models.NotEnoughEvidence, match="every evaluation month"):
        models.skill([1.0, 2.0, 3.0], [1.0, 2.0, 3.0], reference=[1.0, None, 3.0])
