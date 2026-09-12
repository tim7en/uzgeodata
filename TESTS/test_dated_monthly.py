"""One pass carries several variables, and each must stay its own measurement.

The science of these adapters is checked by reproducing the published climatology
over its own window, which the pipeline does before a regional run. What is checked
here is the bookkeeping around it: that a band keeps its own attribute, unit and
scale, that a null keeps its reason, and that nothing quietly inherits another
band's identity when they travel together in one image.
"""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core.observations import ContractError
from ATLAS_MODULES.hydrosheds.functions import dated_monthly
from PIPELINES import extract_regional_monthly as regional


def extracted(band, value=10.0, basin="4120380180", year=2003, month=1, valid=947, expected=947):
    return {"hybas_id": basin, "band": band, "year": year, "month": month,
            "value": value, "valid_count": valid, "expected_count": expected}


def test_every_declared_band_carries_its_own_attribute_unit_and_scale():
    seen = {}
    for source, spec in dated_monthly.SOURCES.items():
        assert spec["asset"] and spec["bands"], source
        for band, definition in spec["bands"].items():
            for field in ("scale", "unit", "attribute", "label"):
                assert definition.get(field), f"{source}/{band} has no {field}"
            assert definition["scale"] > 0
            assert definition["attribute"].startswith("uzgeodata.dated.v1.")
            assert definition["attribute"] not in seen, "two bands claim one attribute"
            seen[definition["attribute"]] = (source, band)
    assert len(seen) == 8, ("four TerraClimate variables, ERA5 runoff, and the two "
                            "temperature adapters that stand against each other")


def test_each_band_becomes_its_own_series_when_they_travel_together():
    rows = [extracted("aet", 10.0), extracted("pet", 20.0),
            extracted("soil", 30.0), extracted("pr", 40.0)]
    built = regional.observation_rows("terraclimate", rows, "geom-1", "recipe@1", "run-1", "2026-01-01T00:00:00Z")
    assert len(built) == 4

    by_value = {row["value"]: row for row in built}
    assert by_value[10.0]["attribute_id"] == "uzgeodata.dated.v1.aet_mm_s"
    assert by_value[30.0]["attribute_id"] == "uzgeodata.dated.v1.soil_mm_s"
    assert len({row["attribute_id"] for row in built}) == 4, "no band inherits another's identity"
    assert len({row["observation_id"] for row in built}) == 4, "nor another's observation"


def test_the_two_temperature_adapters_stay_separable_in_the_store():
    """Both are extracted; neither is named the answer by taking the other's place."""
    terra = dated_monthly.SOURCES["terraclimate_temperature"]["bands"]
    era5 = dated_monthly.SOURCES["era5_temperature"]["bands"]

    assert set(terra) == {"tmmx", "tmmn"}, "the extremes are kept apart, not averaged in the source"
    assert [b["attribute"] for b in terra.values()] == ["uzgeodata.dated.v1.tmx_dc_s",
                                                        "uzgeodata.dated.v1.tmn_dc_s"]
    assert era5["temperature_2m"]["attribute"] == "uzgeodata.dated.v1.tmp_dc_s"
    assert {b["unit"] for b in list(terra.values()) + list(era5.values())} == {"degrees Celsius"}
    assert regional.release_id("terraclimate_temperature") != regional.release_id("era5_temperature")


def test_a_temperature_in_kelvin_is_converted_by_an_offset_not_a_factor():
    """Multiplying a kelvin reading by a factor would put freezing point anywhere but zero."""
    era5 = dated_monthly.SOURCES["era5_temperature"]["bands"]["temperature_2m"]
    assert era5["offset"] == -273.15 and era5["scale"] == 1.0

    def converted(raw, band):
        return raw * band["scale"] + band.get("offset", 0.0)

    assert converted(273.15, era5) == pytest.approx(0.0), "freezing point is zero Celsius"
    assert converted(300.0, era5) == pytest.approx(26.85)
    # The sources that need no zero point are unaffected by the offset arriving.
    assert converted(125, dated_monthly.SOURCES["terraclimate"]["bands"]["aet"]) == pytest.approx(12.5)
    assert converted(-45, dated_monthly.SOURCES["terraclimate_temperature"]["bands"]["tmmn"]) == pytest.approx(-4.5)


def test_soil_moisture_is_published_as_millimetres_not_as_a_percentage():
    """TerraClimate soil is millimetres. The HydroATLAS attribute it substitutes for
    is a percentage, and this series does not claim to be it."""
    soil = dated_monthly.SOURCES["terraclimate"]["bands"]["soil"]
    assert soil["unit"] == "millimetres of soil moisture"
    assert "pc" not in soil["attribute"], "not relabelled as the percentage attribute"
    built = regional.observation_rows("terraclimate", [extracted("soil", 30.0)],
                                      "geom-1", "recipe@1", "run-1", "2026-01-01T00:00:00Z")
    assert built[0]["unit"] == "millimetres of soil moisture"


def test_a_month_without_a_value_keeps_its_reason():
    built = regional.observation_rows("era5_runoff", [extracted("runoff_sum", None, valid=0)],
                                      "geom-1", "recipe@1", "run-1", "2026-01-01T00:00:00Z")
    assert built[0]["value"] is None
    assert built[0]["missing_reason"] == "no_value_in_source_for_month"
    assert built[0]["unit"], "a null still belongs to a series with a unit"
    assert built[0]["coverage_fraction"] == 0.0


def test_a_dated_row_carries_the_month_it_covers_and_its_denominators():
    built = regional.observation_rows("terraclimate", [extracted("pr", 40.0, month=12, valid=900)],
                                      "geom-1", "recipe@1", "run-1", "2026-01-01T00:00:00Z")
    row = built[0]
    assert row["time_kind"] == "observation" and row["year"] == 2003 and row["month"] == 12
    assert (row["valid_start"], row["valid_end"]) == ("2003-12-01", "2004-01-01")
    assert row["temporal_statistic"] == "monthly_mean"
    assert row["valid_count"] == 900 and row["expected_count"] == 947
    assert row["coverage_fraction"] == pytest.approx(900 / 947)


def test_a_measured_zero_is_a_value_and_not_a_missing_month():
    built = regional.observation_rows("terraclimate", [extracted("pr", 0.0)],
                                      "geom-1", "recipe@1", "run-1", "2026-01-01T00:00:00Z")
    assert built[0]["value"] == 0.0
    assert not built[0]["missing_reason"], "a dry month is measured, not missing"


def test_a_basin_with_no_cells_cannot_report_coverage():
    built = regional.observation_rows("terraclimate", [extracted("pr", None, valid=0, expected=0)],
                                      "geom-1", "recipe@1", "run-1", "2026-01-01T00:00:00Z")
    assert built[0]["coverage_fraction"] is None, "no denominator, no fraction"
    assert built[0]["missing_reason"]


def test_the_release_names_the_collection_it_came_from():
    assert regional.release_id("terraclimate").endswith("IDAHO_EPSCOR/TERRACLIMATE")
    assert regional.release_id("era5_runoff").endswith("ECMWF/ERA5_LAND/MONTHLY_AGGR")
    assert regional.release_id("terraclimate") != regional.release_id("era5_runoff")


def test_the_contract_still_refuses_a_value_without_its_unit():
    """The mapping cannot smuggle an unlabelled number into the store."""
    rows = [extracted("aet", 10.0)]
    broken = dict(dated_monthly.SOURCES["terraclimate"]["bands"]["aet"])
    try:
        dated_monthly.SOURCES["terraclimate"]["bands"]["aet"] = {**broken, "unit": None}
        with pytest.raises(ContractError, match="requires its unit"):
            regional.observation_rows("terraclimate", rows, "geom-1", "r@1", "run-1", "2026-01-01T00:00:00Z")
    finally:
        dated_monthly.SOURCES["terraclimate"]["bands"]["aet"] = broken
