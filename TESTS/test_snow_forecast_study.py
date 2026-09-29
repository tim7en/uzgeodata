"""Guards for the snow-based seasonal flow forecast study."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from PIPELINES import build_snow_forecast_study as study

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
