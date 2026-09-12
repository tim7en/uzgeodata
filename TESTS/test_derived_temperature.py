"""Temperature, derived from whichever dated source can form a monthly mean.

HydroATLAS carries one temperature family. ERA5-Land publishes a monthly mean of
hourly values directly; TerraClimate publishes the month's two extremes, whose
midpoint is a different measurement wearing the same name. Both are derived, neither
displaces the other, and what is tested here is that the arithmetic says what it
claims: a midpoint of extremes where that is what it is, an annual figure over the
twelve monthly normals, and no number at all where a month is missing.
"""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import observations
from ATLAS_MODULES.hydrosheds.functions import derive_climatology as derive

MONTHS = list(range(1, 13))
WARMING = [-6.0, -4.0, 2.0, 9.0, 15.0, 21.0, 24.0, 22.0, 16.0, 9.0, 2.0, -4.0]


def entries(values, valid=20, expected=20):
    """One variable's normals as `derive.normals` produces them."""
    return {month: {"value": values[month - 1], "valid": valid, "expected": expected}
            for month in MONTHS}


def test_the_terraclimate_midpoint_sits_between_the_extremes_it_came_from():
    maxima = [value + 8.0 for value in WARMING]
    minima = [value - 6.0 for value in WARMING]
    derived = derive.temperature({"tmx": entries(maxima), "tmn": entries(minima)})

    terra = derived["terraclimate_temperature"]
    assert terra["tmp_dc_s01"][0] == pytest.approx(-5.0), "the midpoint, not either extreme"
    assert [terra[f"tmp_dc_s{m:02d}"][0] for m in MONTHS] == pytest.approx(
        [value + 1.0 for value in WARMING])
    assert "era5_temperature" not in derived, "a source with no dated rows derives nothing"


def test_the_era5_mean_is_taken_as_published_rather_than_recomputed():
    derived = derive.temperature({"tmp": entries(WARMING)})
    era5 = derived["era5_temperature"]
    assert [era5[f"tmp_dc_s{m:02d}"][0] for m in MONTHS] == pytest.approx(WARMING)
    assert set(derived) == {"era5_temperature"}


def test_both_sources_produce_the_same_columns_and_stay_apart(tmp_path):
    derived = derive.temperature({"tmp": entries(WARMING),
                                  "tmx": entries([v + 8.0 for v in WARMING]),
                                  "tmn": entries([v - 6.0 for v in WARMING])})
    assert set(derived) == {"era5_temperature", "terraclimate_temperature"}
    assert derived["era5_temperature"].keys() == derived["terraclimate_temperature"].keys()
    assert len(derived["era5_temperature"]) == 15, "twelve months, an annual figure and two extremes"

    # The store keeps them apart because the release is part of an observation's
    # identity, so the same column name from two sources is two observations.
    def row(release, value):
        return observations.build(
            basin_id="4120380180", geometry_version="reg-1", basin_level=12,
            attribute_id="hydrosheds.basinatlas.v1.tmp_dc_s01", recipe_version="derive@abc",
            mode="annual_extension", spatial_support="s", time_kind="climatology", month=1,
            temporal_statistic="monthly_climatological_mean",
            valid_start="2003-01-01", valid_end="2023-01-01", value=value,
            unit="degrees Celsius", source_release_id=release, run_id="run-1")

    stored = observations.append([], [row("era5_temperature@x", -6.0),
                                      row("terraclimate_temperature@y", -5.0)])
    assert len({r["observation_id"] for r in stored}) == 2
    assert not observations.series_conflicts(stored), "one unit and one period across both"


def test_the_annual_figure_and_extremes_are_taken_over_the_monthly_normals():
    era5 = derive.temperature({"tmp": entries(WARMING)})["era5_temperature"]
    assert era5["tmp_dc_syr"][0] == pytest.approx(sum(WARMING) / 12)
    assert era5["tmp_dc_smn"][0] == pytest.approx(-6.0), "the coldest month, not the coldest night"
    assert era5["tmp_dc_smx"][0] == pytest.approx(24.0), "the warmest month, not the warmest day"

    maxima, minima = [v + 8.0 for v in WARMING], [v - 6.0 for v in WARMING]
    terra = derive.temperature({"tmx": entries(maxima), "tmn": entries(minima)})["terraclimate_temperature"]
    assert terra["tmp_dc_smx"][0] == pytest.approx(25.0), "the warmest monthly midpoint"
    assert terra["tmp_dc_smx"][0] < max(maxima), "and never the extreme it was formed from"


def test_a_month_missing_one_extreme_is_not_half_a_mean():
    maxima = [v + 8.0 for v in WARMING]
    minima = [v - 6.0 for v in WARMING]
    minima[6] = None
    terra = derive.temperature({"tmx": entries(maxima), "tmn": entries(minima)})["terraclimate_temperature"]

    assert terra["tmp_dc_s07"][0] is None, "a midpoint needs both extremes"
    assert terra["tmp_dc_s06"][0] is not None, "and the months that have both are unaffected"
    for column in ("tmp_dc_syr", "tmp_dc_smn", "tmp_dc_smx"):
        assert terra[column][0] is None, "no annual figure is computed across a gap"


def test_a_derived_month_reports_the_weaker_of_the_supports_behind_it():
    maxima = entries([v + 8.0 for v in WARMING], valid=20, expected=20)
    minima = entries([v - 6.0 for v in WARMING], valid=14, expected=20)
    terra = derive.temperature({"tmx": maxima, "tmn": minima})["terraclimate_temperature"]

    assert terra["tmp_dc_s01"][1:] == (14, 20), "fourteen Januaries contributed, not twenty"
    assert terra["tmp_dc_syr"][1:] == (14, 20)
