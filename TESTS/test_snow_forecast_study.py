"""Guards for the snow-based seasonal flow forecast study."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from PIPELINES import build_snow_forecast_study as study
from PIPELINES import build_snow_forecast_region as region
from PIPELINES import verify_snow_forecast_region as verify_region

ROOT = Path(__file__).resolve().parents[1]
PSKEM = ROOT / "PUBLISHED/data/case-studies/snow-forecast/16290/study.json"


def test_mann_kendall_detects_a_trend_and_rejects_noise():
    rising = study.mann_kendall(np.arange(40) * 2.0 + np.random.default_rng(1).normal(0, 3, 40))
    assert rising["p_value"] < 0.001 and abs(rising["sen_slope_per_decade"] - 20) < 3
    flat = study.mann_kendall(np.random.default_rng(2).normal(0, 1, 40))
    assert flat["p_value"] > 0.05


def test_operational_hindcast_never_uses_the_year_it_forecasts():
    years = np.arange(1951, 2018)
    rng = np.random.default_rng(3)
    swe = rng.normal(600, 150, len(years))
    frame = pd.DataFrame({"meanSWE": swe, "veg": 0.2 * swe + rng.normal(0, 10, len(years))}, index=years)
    before = study.operational(frame, "veg", "meanSWE")
    changed = frame.copy()
    changed.loc[2017, "veg"] += 1000  # the last year's outcome must not move its own forecast
    after = study.operational(changed, "veg", "meanSWE")
    assert before["series"][-1][2:4] == after["series"][-1][2:4]


@pytest.mark.skipif(not PSKEM.exists(), reason="run build_snow_forecast_study.py --gauge 16290")
def test_pskem_april_forecast_beats_climatology_out_of_sample():
    report = json.loads(PSKEM.read_text())
    april = report["forecasts"]["operational"]["4"]["meanSWE"]
    assert april["all"]["skill_corrected"] > 0.4
    assert april["recent"]["skill_corrected"] > 0.2
    assert report["discharge"]["overlap_agreement"]["r"] > 0.99


REGION = ROOT / "PUBLISHED/data/case-studies/snow-forecast/region/gauges.json"


@pytest.mark.skipif(not (REGION.exists() and PSKEM.exists()), reason="run the regional and Pskem builds")
def test_regional_grids_reproduce_the_single_basin_study():
    """The 40-band regional store must give Pskem the skill its daily-cell study gives."""
    region = {g["code"]: g for g in json.loads(REGION.read_text())["gauges"]}
    single = json.loads(PSKEM.read_text())["forecasts"]["operational"]["4"]["meanSWE"]["all"]["skill_corrected"]
    regional = region["16290"]["issue"]["4"]["operational"]["meanSWE"]["all"]["skill_corrected"]
    assert abs(regional - single) < .05


@pytest.mark.skipif(not REGION.exists(), reason="run build_snow_forecast_region.py")
def test_april_forecasts_beat_climatology_at_most_gauges():
    gauges = json.loads(REGION.read_text())["gauges"]
    april = [g["issue"]["4"]["operational"]["meanSWE"]["all"]["skill_corrected"] for g in gauges]
    assert len(april) >= 40
    assert np.mean(np.array(april) > 0) > .85


def test_regional_operational_inputs_refit_saved_score_and_reject_stale_cache():
    years = np.arange(1951, 2018)
    swe = 200 + np.arange(len(years)) * 2 + np.sin(years) * 30
    flow = 25 + swe * .2 + np.cos(years) * 5
    frame = pd.DataFrame({"meanSWE": swe, "veg": flow}, index=years)
    table = frame[["meanSWE"]].copy()
    table.index = pd.MultiIndex.from_arrays([years, np.full(len(years), 4)],
                                             names=["water_year", "issue_month"])
    saved = study.operational(frame, "veg", "meanSWE")
    entry = {"code": "test", "issue": {"4": {"operational": {"meanSWE": saved}}}}
    region.attach_operational_inputs(entry, table, frame.veg)
    inputs = entry["issue"]["4"]["operational_inputs"]
    assert inputs["fields"] == ["water_year", "mean_swe_mm", "april_september_mean_discharge_m3s"]
    assert len(inputs["rows"]) == len(years)
    assert inputs["rows"][0] == [1951, float(swe[0]), float(flow[0])]
    assert verify_region.verify({"gauges": [entry]}) == (1, 1)
    changed = frame.veg.copy()
    changed.loc[2017] += 100
    with pytest.raises(ValueError, match="changed"):
        region.attach_operational_inputs(entry, table, changed)


def test_independent_verifier_refits_pskem_from_published_inputs():
    path = ROOT / "PUBLISHED/data/case-studies/snow-forecast/16290/predictors-and-targets.csv"
    source = pd.read_csv(path)
    frame = (source[source.issue_month == 4]
             [["water_year", "meanSWE", "veg"]].dropna()
             .rename(columns={"meanSWE": "mean_swe_mm",
                              "veg": "april_september_mean_discharge_m3s"})
             .set_index("water_year"))
    rebuilt = verify_region.refit(frame)
    saved = json.loads(PSKEM.read_text())["forecasts"]["operational"]["4"]["meanSWE"]
    assert rebuilt["all"]["n"] == saved["all"]["n"]
    assert rebuilt["all"]["skill_corrected"] == pytest.approx(saved["all"]["skill_corrected"])
    assert rebuilt["recent"]["skill_corrected"] == pytest.approx(saved["recent"]["skill_corrected"])
