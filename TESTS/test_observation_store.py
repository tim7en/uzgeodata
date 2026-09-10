"""The stage 5 acceptance gate, as tests.

Round-trip a frozen snapshot, append a correction without losing the value it
replaces, preserve nulls, keep monthly observations apart from monthly
climatologies, and refuse a changed unit, geometry or period inside an
unversioned series.
"""
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import observations
from ATLAS_MODULES.core.observations import ContractError
from PIPELINES.stage_pilot_observations import STORE, build_rows, latest_run

CLIMATOLOGY = dict(
    basin_id="4120380180", geometry_version="geom-1", basin_level=12,
    attribute_id="hydrosheds.basinatlas.v1.pre_mm_s07", recipe_version="terraclimate@abc",
    mode="annual_extension", spatial_support="s", time_kind="climatology", month=7,
    temporal_statistic="monthly_climatological_mean",
    valid_start="1991-01-01", valid_end="2021-01-01",
    value=12.5, unit="millimetres per month", source_release_id="terraclimate@abc", run_id="run-1")


def make(**overrides):
    return observations.build(**{**CLIMATOLOGY, **overrides})


@pytest.fixture(scope="module")
def staged():
    rows = observations.read_partitions(STORE)
    assert rows, "the pilot observations are published"
    return rows


@pytest.fixture(scope="module")
def manifest():
    return json.loads((STORE / "manifest.json").read_text(encoding="utf-8"))


def test_the_staged_pilot_invents_no_observation_year(staged, manifest):
    assert manifest["rows"] == len(staged)
    assert manifest["dated_observations"] == 0
    assert all(row["year"] is None for row in staged), "this run holds no dated observations"
    assert {row["time_kind"] for row in staged} == {"static", "source_epoch", "climatology"}
    assert manifest["by_mode"]["reference_import"] == manifest["basins"] * 281


def test_a_monthly_climatology_is_not_a_dated_month():
    climatology = make()
    assert climatology["year"] is None and climatology["month"] == 7
    with pytest.raises(ContractError, match="carries no year"):
        make(year=2026)
    with pytest.raises(ContractError, match="requires its year"):
        make(time_kind="observation", year=None)

    # July 2026 and a July climatology are different observations, never the same row.
    dated = make(time_kind="observation", year=2026, valid_start="2026-07-01",
                 valid_end="2026-08-01", temporal_statistic="monthly_mean")
    assert dated["observation_id"] != climatology["observation_id"]
    assert observations.partition(dated) != observations.partition(climatology)


def test_a_class_code_is_never_stored_as_a_calendar_month(staged):
    with pytest.raises(ContractError, match="dimension code"):
        make(time_kind="source_epoch", month=1, valid_start=None, valid_end=None)
    with pytest.raises(ContractError, match="not a calendar month"):
        make(month=13)

    def months(column):
        return {row["month"] for row in staged
                if row["attribute_id"].endswith(column) and row["mode"] == "annual_extension"}
    assert months("glc_pc_s01") == {None}, "land-cover class 1 is not January"
    assert months("snw_pc_s01") == {1}, "a January snow climatology keeps its month"


def test_a_missing_value_keeps_its_reason_and_never_becomes_a_zero(staged):
    with pytest.raises(ContractError, match="requires a missing_reason"):
        make(value=None)
    with pytest.raises(ContractError, match="is not missing"):
        make(value=0.0, missing_reason="not measured")
    assert make(value=0.0)["value"] == 0.0, "a measured zero is a value"

    missing = [row for row in staged if row["value"] is None]
    assert missing, "the pilot carries published missing values"
    assert all(row["missing_reason"] for row in missing)
    assert all(row["value"] != 0 for row in missing)


def test_a_correction_supersedes_without_losing_the_earlier_value():
    first = make(value=12.5)
    corrected = make(value=13.25, revision=2, supersedes=observations.row_key(first), run_id="run-2")
    stored = observations.append([first], [corrected])

    assert len(stored) == 2, "the superseded value stays in the store"
    assert [row["value"] for row in stored] == [12.5, 13.25]
    current = observations.latest(stored)
    assert [row["value"] for row in current] == [13.25]
    assert current[0]["revision"] == 2

    with pytest.raises(ContractError, match="not in the store"):
        observations.append([], [corrected])
    with pytest.raises(ContractError, match="supersedes nothing"):
        make(revision=1, supersedes=observations.row_key(first))


def test_a_published_row_cannot_be_rewritten_in_place():
    first = make(value=12.5)
    with pytest.raises(ContractError, match="already published with different content"):
        observations.append([first], [make(value=99.0)])
    # Re-staging identical frozen evidence is a no-op, so a rebuild changes nothing.
    assert observations.append([first], [make()]) == [first]


def test_an_unversioned_series_cannot_change_its_unit_or_period():
    metres = make(unit="metres", value=1.0)
    with pytest.raises(ContractError, match="unit changes"):
        observations.append([metres], [make(unit="feet", value=3.28, basin_id="4120380350")])

    # The same change is acceptable once the recipe that made it is versioned.
    versioned = make(unit="feet", value=3.28, recipe_version="terraclimate@def",
                     basin_id="4120380350")
    assert len(observations.append([metres], [versioned])) == 2

    with pytest.raises(ContractError, match="valid_start changes"):
        observations.append([metres], [make(unit="metres", value=2.0, valid_start="1961-01-01",
                                            basin_id="4120380350")])


def test_a_dated_series_may_hold_many_periods():
    dated = [make(time_kind="observation", year=2026, month=month,
                  valid_start=f"2026-{month:02d}-01", valid_end=f"2026-{month + 1:02d}-01",
                  temporal_statistic="monthly_mean", value=float(month)) for month in (7, 8)]
    stored = observations.append([], dated)
    assert len(stored) == 2
    assert not observations.series_conflicts(stored), "months are observations, not a drifting series"
    with pytest.raises(ContractError, match="must lie after"):
        make(time_kind="observation", year=2026, valid_start="2026-08-01", valid_end="2026-08-01")


def test_the_store_round_trips_through_its_partitions(tmp_path):
    rows = observations.append([], [
        make(),
        make(value=None, missing_reason="source masked", basin_id="4120380350"),
        make(value=0.0, basin_id="4120382970"),
        # A dated extraction is a different method from a climatology, so it carries
        # its own recipe version rather than drifting inside the climatological one.
        make(time_kind="observation", year=2026, valid_start="2026-07-01",
             valid_end="2026-08-01", temporal_statistic="monthly_mean",
             recipe_version="terraclimate-dated@abc", basin_id="4120383080"),
    ])
    observations.write_partitions(tmp_path, rows)
    restored = observations.read_partitions(tmp_path)

    assert sorted(restored, key=observations.sort_key) == sorted(rows, key=observations.sort_key)
    values = {row["basin_id"]: row["value"] for row in restored}
    assert values["4120380350"] is None and values["4120382970"] == 0.0, "a null survives as a null"


def test_the_published_store_round_trips_and_matches_its_run(staged):
    batch, lock = latest_run()
    rebuilt, _ = build_rows(batch, lock)
    assert len(rebuilt) == len(staged)
    assert {observations.row_key(row) for row in rebuilt} == {observations.row_key(row) for row in staged}
    assert not observations.series_conflicts(staged)
    assert all(row["run_id"] == batch["run_id"] for row in staged)


def test_qa_denominators_must_agree_with_their_coverage():
    assert make(valid_count=900, expected_count=947, coverage_fraction=900 / 947)
    with pytest.raises(ContractError, match="exceeds expected_count"):
        make(valid_count=1000, expected_count=947, coverage_fraction=1.0)
    with pytest.raises(ContractError, match="disagrees with its own QA denominators"):
        make(valid_count=100, expected_count=947, coverage_fraction=1.0)
    with pytest.raises(ContractError, match="outside 0..1"):
        make(coverage_fraction=1.4)


def test_provenance_is_required_on_every_row(staged):
    for field in ("attribute_id", "geometry_version", "recipe_version", "source_release_id", "run_id"):
        with pytest.raises(ContractError, match=f"{field} is required"):
            make(**{field: None})
    releases = {row["source_release_id"] for row in staged}
    published = {line.split(",")[0] for line in
                 (STORE / "source_release.csv").read_text(encoding="utf-8").splitlines()[1:]}
    assert releases <= published, "every observation points at a published source release"
