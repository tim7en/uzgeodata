"""Scientific guard rails: time support, no leakage, QC and spatial support."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cases", ROOT / "PIPELINES/build_chirchik_case_studies.py")
cases = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cases)


def daily(year=2020, month=2, days=29, value=10):
    return [{"station_id": "q", "year": str(year), "month": str(month), "day": str(d),
             "discharge_cms": str(value), "source_file": "test.xlsx"} for d in range(1, days + 1)]


def test_perfect_and_undefined_metrics():
    result = cases.scores([1, 2, 3], [1, 2, 3])
    assert result["nse"] == result["kge"] == 1
    assert result["rmse"] == result["bias"] == 0
    constant = cases.scores([0, 0], [1, 1])
    assert constant["kge"] is None and constant["nse"] is None
    assert constant["pbias"] is None and constant["r"] is None
    assert cases.scores([], [])["n"] == 0
    with pytest.raises(ValueError):
        cases.scores([1], [1, 2])


def test_bias_sign_and_nonperfect_scores():
    result = cases.scores([1, 2, 3], [2, 3, 4])
    assert result["bias"] == result["rmse"] == result["mae"] == 1
    assert result["pbias"] == 50
    assert result["nse"] == -0.5
    assert result["kge"] == pytest.approx(0.5)


def test_leap_month_volume_and_missing_days_are_not_extrapolated():
    full = cases.discharge_months(daily(), set())[0]
    assert full["days_expected"] == 29
    assert full["observed_volume_mcm"] == pytest.approx(10 * 29 * 86400 / 1e6)
    incomplete = cases.discharge_months(daily(days=28), set())[0]
    assert incomplete["eligible"]
    assert incomplete["observed_volume_mcm"] is None
    insufficient = cases.discharge_months(daily(days=26), set())[0]
    assert not insufficient["eligible"]


def test_calendar_quarantine_preserves_source_and_rejects_invalid_date():
    source = daily(year=2015)
    accepted, rejected = cases.calendar_audit(source)
    assert len(accepted) == 28 and len(rejected) == 1
    assert rejected[0]["day"] == "29"
    assert rejected[0]["reason"] == "invalid_calendar_date"
    assert len(source) == 29
    with pytest.raises(ValueError):
        cases.discharge_months(source, set())


def test_suspect_values_are_screened_without_changing_raw():
    source = daily()
    source[0]["discharge_cms"] = "1000"
    result = cases.discharge_months(source, {("q", 2020, 2, 1)})[0]
    assert result["screened_mean"] == 10
    assert result["raw_mean"] > 10
    assert result["suspect_days"] == 1 and result["days_valid"] == 28
    assert result["observed_volume_mcm"] is None
    assert source[0]["discharge_cms"] == "1000"


def test_duplicate_daily_observations_are_not_double_counted():
    source = daily()
    with pytest.raises(ValueError, match="Duplicate"):
        cases.discharge_months(source + source[:1], set())


def test_benchmark_cannot_learn_from_held_out_values():
    rows = [{"year": year, "month": m, "eligible": True, "screened_mean": float(m), "raw_mean": float(m)}
            for year in range(2001, 2018) for m in range(1, 13)]
    first = cases.benchmark(rows)
    for r in rows:
        if r["year"] > 2010:
            r["screened_mean"] = 99999
    second = cases.benchmark(rows)
    assert first["climatology"] == second["climatology"]
    assert first["scores"]["nse"] == 1
    assert second["scores"]["rmse"] > 99900
    assert all(r["year"] > 2010 for r in second["pairs"])


def test_upstream_trace_excludes_downstream_and_detects_cycles():
    routing = [{"hybas_id": "a", "next_down": "c"}, {"hybas_id": "b", "next_down": "c"},
               {"hybas_id": "c", "next_down": "d"}, {"hybas_id": "d", "next_down": "0"}]
    assert cases.upstream_candidate(routing, "c") == {"a", "b", "c"}
    with pytest.raises(ValueError, match="Cycle"):
        cases.upstream_candidate([{"hybas_id": "a", "next_down": "b"}, {"hybas_id": "b", "next_down": "a"}], "a")


def test_product_pairs_require_matching_time_units_and_support(tmp_path):
    obs = [{"station_id": "uz:station/meteo-419704", "year": "2020", "month": "1", "variable": "precipitation_total", "value": "0"}]
    row = {"station_id": obs[0]["station_id"], "period": "2020-01", "variable": "precipitation_total", "value": "10",
           "unit": "mm", "product": "fixture", "spatial_support": "station_grid_cell"}
    path = tmp_path / "forcing.csv"
    cases.write_csv(path, [row, {**row, "period": "2021-01", "value": "999"}], list(row))
    result = cases.product_validation(path, obs)
    assert len(result["pairs"]) == 1
    assert result["comparisons"][0]["scores"]["rmse"] == 10
    assert result["comparisons"][0]["scores"]["pbias"] is None
    for patch in [{"unit": "m"}, {"spatial_support": "basin_mean"}]:
        cases.write_csv(path, [{**row, **patch}], list(row))
        with pytest.raises(ValueError):
            cases.product_validation(path, obs)


def test_actual_delivery_builds_with_provenance_and_no_invented_validation(tmp_path):
    data = cases.build(output=tmp_path)
    assert data["summary"]["invalid_calendar_rows"] == 1
    assert data["summary"]["suspect_daily_rows"] == 3
    assert data["summary"]["joint_months"] == 93
    pskem_temperature = next(r for r in data["inventory"] if r["station"] == "Pskem" and r["variable"] == "air_temperature_mean")
    assert len(pskem_temperature["missing"]) == 3
    assert data["validation"]["comparisons"] == []
    assert data["benchmark"]["scores"]["n"] == 84
    assert all(len(r["sha256"]) == 64 for r in data["provenance"])
    assert len(data["studies"]) == 6
    for row in data["discharge_monthly"]:
        assert row["days_valid"] <= row["days_expected"]
        assert (row["observed_volume_mcm"] is not None) == (row["days_valid"] == row["days_expected"])
    stored = json.loads((tmp_path / "chirchik.json").read_text(encoding="utf-8"))
    assert stored["summary"] == data["summary"]
