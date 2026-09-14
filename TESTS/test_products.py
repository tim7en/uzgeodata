"""Derived products are where a number stops being an observation and becomes a claim.

Each test here is a way that claim can be confidently wrong while looking right: a
gap counted as a zero, a season summed short of its months, a state given an annual
total, an anomaly judged against itself, a trend drawn through a thinning record.
None of those produce an error. They produce a number, a chart and a conclusion.
"""
import pytest

from ATLAS_MODULES.core import observations, products, query, variables

pytest.importorskip("duckdb")

MONTHLY = dict(
    geometry_version="reg-1", basin_level=12, recipe_version="dated@abc",
    mode="annual_extension", spatial_support="s", time_kind="observation",
    temporal_statistic="monthly_mean", unit="millimetres per month",
    source_release_id="terraclimate@IDAHO_EPSCOR/TERRACLIMATE", run_id="done")


def rain(basin, year, month, value, attribute="uzgeodata.dated.v1.pre_mm_s", **extra):
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


def steady(tmp_path, years=range(2003, 2025), value=10.0):
    return store_with(tmp_path, [rain("4120000001", year, month, value)
                                 for year in years for month in range(1, 13)])


def test_an_anomaly_is_judged_against_the_record_not_against_itself(tmp_path):
    rows = [rain("4120000001", year, month, 10.0)
            for year in range(2003, 2025) for month in range(1, 13)]
    # One extreme July, in the middle of an otherwise flat record.
    rows = [r for r in rows if not (r["year"] == 2011 and r["month"] == 7)]
    rows.append(rain("4120000001", 2011, 7, 90.0))
    store = store_with(tmp_path, rows)

    [july] = [row for row in products.anomalies(store, "precipitation",
                                                start="2011-07", end="2011-07")
              if row["month"].month == 7]
    assert july["baseline_years"] > 20, "the baseline comes from the whole record"
    assert july["anomaly"] > 70, "an extreme month reads as extreme"

    # Judged against only itself, the same month is unremarkable by construction.
    [narrow] = products.anomalies(store, "precipitation", start="2011-07", end="2011-07",
                                  baseline=("2011-07", "2011-07"))
    assert narrow["withheld"] == "baseline too short", "a one-year baseline is refused"


def test_a_baseline_with_no_spread_yields_no_standardised_score(tmp_path):
    store = steady(tmp_path)
    [row] = [r for r in products.anomalies(store, "precipitation",
                                           start="2010-05", end="2010-05")]
    assert row["anomaly"] == pytest.approx(0.0)
    assert row["z"] is None, "a constant baseline makes every score infinite, not significant"
    assert row["withheld"] == "baseline has no spread"


def test_a_season_short_of_a_month_yields_no_total(tmp_path):
    rows = [rain("4120000001", 2010, month, 10.0) for month in (6, 7)]
    rows.append(rain("4120000001", 2010, 8, None))
    store = store_with(tmp_path, rows)

    [summer] = products.seasonal(store, "precipitation", months=[6, 7, 8])
    assert summer["observed"] == 2 and summer["expected"] == 3
    assert summer["total"] is None, "a summer total short of August is not a summer total"
    assert summer["withheld"] == "the season is incomplete"
    assert summer["mean"] == pytest.approx(10.0), "the mean of what was observed is still reported"


def test_a_state_is_never_given_an_annual_total(tmp_path):
    rows = [observations.build(**{**MONTHLY, "basin_id": "4120000001", "year": 2010,
                                  "month": month, "valid_start": f"2010-{month:02d}-01",
                                  "valid_end": f"2010-{month + 1:02d}-01" if month < 12 else "2011-01-01",
                                  "attribute_id": "uzgeodata.dated.v1.tmp_dc_s",
                                  "unit": "degrees Celsius", "value": 20.0})
            for month in range(1, 13)]
    store = store_with(tmp_path, rows)

    [year] = products.seasonal(store, "mean temperature")
    assert year["kind"] == "state"
    assert year["total"] is None, "twelve monthly temperatures do not sum to a year"
    assert year["mean"] == pytest.approx(20.0)


def test_a_trend_reports_the_record_it_was_drawn_through(tmp_path):
    # A record with holes: a slope exists, and how much of the span it rests on matters.
    rows = []
    for year in range(2003, 2025):
        if year in (2016, 2017, 2018):
            continue
        for month in range(1, 13):
            rows.append(rain("4120000001", year, month, 10.0 + (year - 2003)))
    store = store_with(tmp_path, rows)

    [entry] = products.trend(store, "precipitation")
    assert entry["slope"] > 0
    assert entry["gaps"] == 3, "the missing years are counted, not silently skipped"
    assert entry["thinning"] is True
    assert entry["span"] == [2003, 2024]


def test_a_trend_needs_more_than_two_points(tmp_path):
    rows = [rain("4120000001", year, month, 5.0)
            for year in (2003, 2004) for month in range(1, 13)]
    store = store_with(tmp_path, rows)
    [entry] = products.trend(store, "precipitation")
    assert entry["slope"] is None
    assert "too few" in entry["withheld"]


def test_the_snow_caution_reaches_anything_derived_from_it(tmp_path):
    rows = [rain("4120000001", year, month, 50.0, attribute="uzgeodata.dated.v1.snw_pc_s")
            for year in range(2003, 2025) for month in range(1, 13)]
    store = store_with(tmp_path, [observations.build(**{**r, "unit": "percent"}) for r in rows])
    [entry] = products.trend(store, "snow cover")
    assert entry["caution"] and "trend" in entry["caution"].lower(), \
        "a variable withdrawn from trend use says so on its own trend"


def test_the_water_balance_says_what_it_is_not(tmp_path):
    rows = []
    for month in range(1, 13):
        rows.append(rain("4120000001", 2010, month, 30.0))
        rows.append(rain("4120000001", 2010, month, 12.0,
                         attribute="uzgeodata.dated.v1.aet_mm_s"))
    store = store_with(tmp_path, rows)

    balance = products.water_balance(store, start="2010-01", end="2010-12")
    assert len(balance) == 12
    assert balance[0]["balance"] == pytest.approx(18.0)
    assert "not a routed catchment balance" in balance[0]["meaning"], \
        "a crude difference must not be read as a closed water balance"


def test_a_missing_term_leaves_the_balance_undefined(tmp_path):
    rows = [rain("4120000001", 2010, 1, 30.0),
            rain("4120000001", 2010, 1, None, attribute="uzgeodata.dated.v1.aet_mm_s")]
    store = store_with(tmp_path, rows)
    [entry] = products.water_balance(store)
    assert entry["balance"] is None, "a balance with one term missing is not zero"


def test_products_refuse_a_concept_the_project_does_not_answer_for(tmp_path):
    store = steady(tmp_path)
    with pytest.raises(variables.Unavailable):
        products.seasonal(store, "vegetation")


def test_an_accumulation_window_refuses_to_span_a_gap(tmp_path):
    """A three-month window over January, February and April is not a three-month window."""
    rows = [rain("4120000001", 2010, month, 10.0) for month in (1, 2, 4, 5, 6)]
    store = store_with(tmp_path, rows)
    series = query.observations(store, basins=["4120000001"],
                               variables=["uzgeodata.dated.v1.pre_mm_s"])
    totals = products.accumulate(series, 3)
    assert (("4120000001", (2010, 4))) not in totals, "Jan+Feb+Apr is not a quarter"
    assert totals[("4120000001", (2010, 6))] == pytest.approx(30.0)


def test_an_accumulation_refuses_to_treat_a_null_as_no_rain(tmp_path):
    rows = [rain("4120000001", 2010, 1, 10.0), rain("4120000001", 2010, 2, None),
            rain("4120000001", 2010, 3, 10.0)]
    store = store_with(tmp_path, rows)
    series = query.observations(store, basins=["4120000001"],
                               variables=["uzgeodata.dated.v1.pre_mm_s"])
    assert products.accumulate(series, 3) == {}, "an unobserved month is not a dry one"


def test_spi_is_withheld_where_the_record_cannot_fit_a_distribution(tmp_path):
    rows = [rain("4120000001", year, month, 10.0 + month)
            for year in range(2003, 2009) for month in range(1, 13)]
    store = store_with(tmp_path, rows)
    entries = products.spi(store, basins=["4120000001"], window=3)
    assert entries and all(entry["spi"] is None for entry in entries)
    assert all("too few years" in entry["withheld"] for entry in entries)


def test_spi_is_a_gamma_fit_and_not_a_z_score(tmp_path):
    """The distinction that matters: rainfall is skewed and bounded at zero.

    Over a record of mostly modest quarters with a few very wet ones, a normal
    assumption misreads both tails and in opposite directions. It understates the
    droughts, because the bulk of the distribution sits below a mean that a few wet
    years have dragged upwards, and it overstates the wet extremes, because it has no
    long right tail to put them in. Reading the driest quarter in twenty-two years as
    an unremarkable -0.8 is the failure that matters here.
    """
    pytest.importorskip("scipy")
    import statistics as arithmetic

    amounts = [12.0, 14.0, 15.0, 16.0, 18.0, 19.0, 21.0, 22.0, 24.0, 26.0,
               28.0, 31.0, 35.0, 40.0, 48.0, 60.0, 75.0, 95.0, 130.0, 180.0, 20.0, 17.0]
    rows = [rain("4120000001", year, month, amounts[offset] / 3)
            for offset, year in enumerate(range(2003, 2025)) for month in range(1, 13)]
    store = store_with(tmp_path, rows)

    entries = [entry for entry in products.spi(store, basins=["4120000001"], window=3)
               if entry["withheld"] is None]
    assert entries, "twenty-two years is enough to fit"

    totals = [entry["accumulation"] for entry in entries]
    mean, spread = arithmetic.fmean(totals), arithmetic.pstdev(totals)
    naive = lambda entry: (entry["accumulation"] - mean) / spread

    driest = min(entries, key=lambda entry: entry["accumulation"])
    assert driest["spi"] < -1.0, "the driest quarter of the record reads as a real shortfall"
    assert driest["spi"] < naive(driest) - 0.25,         "a normal score would have called this drought unremarkable"

    wettest = max(entries, key=lambda entry: entry["accumulation"])
    assert wettest["spi"] > 1.5, "the wettest quarter still reads wet"
    assert wettest["spi"] < naive(wettest) - 0.25,         "a normal score has no right tail and inflates the wet extreme instead"


def test_spi_reports_the_baseline_it_was_fitted_on(tmp_path):
    pytest.importorskip("scipy")
    rows = [rain("4120000001", year, month, 5.0 + (year % 7) * 3 + month)
            for year in range(2003, 2025) for month in range(1, 13)]
    store = store_with(tmp_path, rows)
    # The window has to hold the three months it accumulates over; asking for June
    # alone yields nothing, which is the contiguity rule doing its job.
    [entry] = products.spi(store, basins=["4120000001"], window=3,
                           start="2015-04", end="2015-06")
    assert entry["baseline_years"] == 22, "the fit rests on the whole record, not the window"
    assert entry["window"] == 3 and entry["month"] == 6
    assert "not a statement about water availability" in entry["meaning"]


def test_spi_withholds_where_the_record_has_no_spread(tmp_path):
    """A constant record has no distribution to fit, and scipy says so unreadably."""
    pytest.importorskip("scipy")
    rows = [rain("4120000001", year, month, 12.0)
            for year in range(2003, 2025) for month in range(1, 13)]
    store = store_with(tmp_path, rows)
    entries = products.spi(store, basins=["4120000001"], window=3)
    assert entries, "the months are still reported"
    assert all(entry["spi"] is None for entry in entries)
    assert all("no spread" in entry["withheld"] for entry in entries), \
        "withheld with a reason, rather than raising from inside a solver"
