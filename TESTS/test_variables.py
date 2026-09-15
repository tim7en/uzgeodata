"""The registry's job is to be opinionated, and to refuse rather than approximate.

An agent or a researcher asks for a concept. The failure that matters is not being
told "no" -- it is being handed something adjacent with confidence, because a vegetation
question answered with snow cover produces a number, a chart and a conclusion, and
nothing in the output says it was the wrong measurement. So most of what is tested
here is the refusals.
"""
import pytest

from ATLAS_MODULES.core import observations, variables


def test_a_concept_resolves_to_exactly_one_preferred_product():
    assert variables.resolve("precipitation") == "uz:pre-monthly-v1"
    assert variables.resolve("rainfall") == "uz:pre-monthly-v1", "synonyms agree"
    assert variables.resolve("PRECIPITATION") == "uz:pre-monthly-v1", "asking is case-insensitive"
    assert variables.resolve("uz:pre-monthly-v1") == "uz:pre-monthly-v1", "an id resolves to itself"


def test_an_unanswerable_concept_is_refused_with_its_reason():
    for concept in ("vegetation", "ndvi", "drought index"):
        with pytest.raises(variables.Unavailable) as raised:
            variables.resolve(concept)
        assert len(str(raised.value)) > len(concept) + 10, "the refusal explains itself"

    # The dangerous near-misses: each names a published quantity it is not.
    with pytest.raises(variables.Unavailable, match="different measurements"):
        variables.resolve("land surface temperature")
    with pytest.raises(variables.Unavailable, match="not the same quantity"):
        variables.resolve("discharge")


def test_runoff_still_means_one_product_when_two_are_published():
    """TerraClimate runoff is published beside ERA5-Land's; asking for runoff must not
    start returning whichever was added last."""
    assert variables.resolve("runoff") == "uz:run-monthly-v1"
    assert variables.resolve("terraclimate runoff") == "uz:rtc-monthly-v1"
    with pytest.raises(variables.Unavailable, match="palmer drought severity index"):
        variables.resolve("drought index")
    assert variables.resolve("pdsi") == "uz:pds-monthly-v1"
    assert variables.VARIABLES["uz:cwd-monthly-v1"]["kind"] == "flux"
    assert variables.VARIABLES["uz:swe-monthly-v1"]["kind"] == "state"


def test_an_unknown_concept_lists_what_can_be_asked_for():
    with pytest.raises(variables.Unavailable, match="Registered concepts"):
        variables.resolve("wind speed")


def test_every_variable_names_a_real_attribute_in_the_contract():
    for identifier, entry in variables.VARIABLES.items():
        assert entry["attribute"].startswith("uzgeodata.dated."), identifier
        assert entry["unit"] and entry["cadence"] and entry["support"], identifier
        assert entry["kind"] in ("flux", "state"), f"{identifier} must say which it is"
        assert entry["preferred"], f"{identifier} names no source"
        assert entry.get("why"), f"{identifier} does not say why that source was preferred"


def test_a_flux_and_a_state_are_distinguished():
    """An annual total is meaningful for a flux and meaningless for a state: summing
    twelve monthly temperatures answers nothing. The registry has to carry which."""
    assert variables.VARIABLES["uz:pre-monthly-v1"]["kind"] == "flux"
    assert variables.VARIABLES["uz:aet-monthly-v1"]["kind"] == "flux"
    assert variables.VARIABLES["uz:tmp-monthly-v1"]["kind"] == "state"
    assert variables.VARIABLES["uz:soil-monthly-v1"]["kind"] == "state"
    assert variables.VARIABLES["uz:snw-monthly-v1"]["kind"] == "state"


def test_a_fallback_is_named_with_what_it_costs():
    """Naming a fallback without its cost invites treating the two as equivalent."""
    for identifier, entry in variables.VARIABLES.items():
        if entry.get("fallback"):
            assert entry.get("fallback_cost"), f"{identifier} names a fallback without its cost"
            assert entry["fallback"] != entry["preferred"], identifier


def test_the_snow_caution_travels_with_the_variable():
    """Snow is withdrawn from trend use, and that has to reach whoever queries it."""
    snow = variables.describe("uz:snw-monthly-v1")
    assert "trend" in snow["caution"].lower()


def test_concept_and_attribute_agree_for_every_registered_name():
    for concept in variables.CONCEPTS:
        entry = variables.VARIABLES[variables.resolve(concept)]
        assert variables.attribute(concept) == entry["attribute"]


def test_the_published_registry_states_what_it_will_not_answer():
    published = variables.registry()
    assert set(published["variables"]) == set(variables.VARIABLES)
    assert published["unavailable"], "a registry that lists only what it has is a catalogue"
    assert "vegetation" in published["unavailable"]
    for entry in published["variables"].values():
        assert entry["id"].startswith("uz:") and entry["id"].endswith("-v1"), \
            "identifiers are versioned, so a change of source is a new version"


def test_a_registered_attribute_is_one_the_contract_would_accept():
    """The registry must not drift from the store it speaks for."""
    for entry in variables.VARIABLES.values():
        record = observations.build(
            basin_id="4120380180", geometry_version="reg-1", basin_level=12,
            attribute_id=entry["attribute"], recipe_version="dated@abc",
            mode="annual_extension", spatial_support="s", time_kind="observation",
            temporal_statistic="monthly_mean", valid_start="2003-01-01",
            valid_end="2003-02-01", year=2003, month=1, value=1.0, unit=entry["unit"],
            source_release_id="x@y", run_id="run-1")
        assert record["attribute_id"] == entry["attribute"]
