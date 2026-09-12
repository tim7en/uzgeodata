"""The regional coverage ledger: what it counts, and what it refuses to conflate.

Coverage is the number the programme will be read by, so the ways it can flatter are
worth testing directly. A basin the source genuinely says nothing about must not look
like work left undone; an abandoned run's values must not be counted for the basins it
reached; and an attribute nothing has estimated must not be filed beside one the pilot
estimated and the region has not.
"""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import observations
from PIPELINES import build_regional_coverage as coverage

EPOCH = dict(
    geometry_version="reg-1", basin_level=12, recipe_version="glims_regional@abc",
    mode="annual_extension", spatial_support="s", time_kind="source_epoch",
    temporal_statistic="epoch_snapshot", valid_start="2015-01-01", valid_end="2016-01-01",
    unit="percent cover", source_release_id="glims@GLIMS/current")


def value(basin, run_id, number, column="gla_pc_sse"):
    missing = None if number is not None else "no_source_value_in_basin"
    return observations.build(**{**EPOCH, "basin_id": basin, "run_id": run_id,
                                 "attribute_id": f"hydrosheds.basinatlas.v1.{column}",
                                 "value": number, "missing_reason": missing})


def test_a_source_with_nothing_to_say_is_not_an_unfinished_run():
    assert coverage.state_of(covered=100, reached=100, total=100, in_pilot=True) == "regional"
    assert coverage.state_of(covered=93, reached=100, total=100, in_pilot=True) == "source_gaps"
    assert coverage.state_of(covered=93, reached=95, total=100, in_pilot=True) == "partial"


def test_an_unadapted_family_is_not_filed_beside_one_merely_unscaled():
    assert coverage.state_of(covered=0, reached=0, total=100, in_pilot=True) == "pilot_only"
    assert coverage.state_of(covered=0, reached=0, total=100, in_pilot=False) == "absent"


def test_a_basin_the_source_was_silent_about_is_reached_but_not_covered(tmp_path):
    observations.append_partitioned(tmp_path, [
        value("4120380180", "run-1", 12.0), value("4120380350", "run-1", None),
        value("4120382970", "run-1", 0.0)])

    covered, reached, total = coverage.counts(tmp_path, {"gla_pc_sse": "run-1"})
    assert total == 3
    assert reached["gla_pc_sse"] == 3, "every basin was asked"
    assert covered["gla_pc_sse"] == 2, "and a measured zero is a value, a null is not"


def test_only_the_published_run_is_counted(tmp_path):
    # The abandoned run reached two basins; the finished re-run reached all three and
    # carries its own recipe, so both sets of values are current in the store.
    abandoned = [value("4120380180", "partial", 12.0), value("4120380350", "partial", 8.0)]
    finished = [observations.build(**{**EPOCH, "basin_id": basin, "run_id": "finished",
                                      "recipe_version": "glims_regional@def",
                                      "attribute_id": "hydrosheds.basinatlas.v1.gla_pc_sse",
                                      "value": 15.0})
                for basin in ("4120380180", "4120380350", "4120382970")]
    observations.append_partitioned(tmp_path, abandoned + finished)
    observations.merge_table(tmp_path / "run.csv", [
        {"run_id": "partial", "started_at": "2026-09-11T00:00:00Z", "status": "incomplete"},
        {"run_id": "finished", "started_at": "2026-09-12T00:00:00Z", "status": "complete"}], "run_id")

    ranking = observations.run_ranking(tmp_path)
    runs, detail = coverage.sources_by_column(tmp_path)
    published = coverage.published_run(runs, ranking)
    assert published["gla_pc_sse"] == "finished", "the run that covered the region wins"

    covered, reached, total = coverage.counts(tmp_path, published)
    assert covered["gla_pc_sse"] == 3
    assert detail[("gla_pc_sse", "finished")]["method"] == "glims_regional@def"


def test_a_pilot_row_is_not_regional_coverage(tmp_path):
    """The pilot's twenty basins carry their own geometry and are counted separately."""
    observations.append_partitioned(tmp_path, [
        observations.build(**{**EPOCH, "basin_id": "4120380180", "run_id": "pilot",
                              "geometry_version": "pilot-1", "value": 12.0,
                              "attribute_id": "hydrosheds.basinatlas.v1.gla_pc_sse"})])

    runs, _ = coverage.sources_by_column(tmp_path)
    covered, reached, total = coverage.counts(tmp_path, {})
    assert runs == {} and total == 0, "a pilot geometry is not the regional domain"
    assert coverage.state_of(0, 0, total, in_pilot=True) == "absent", "with no domain, nothing is covered"


def test_every_state_carries_a_reason_the_ledger_can_print():
    assert set(coverage.REASONS) == {"regional", "source_gaps", "partial", "pilot_only", "absent"}
    assert coverage.REASONS["source_gaps"].format(short=192).endswith("with its reason")
    assert "{short}" not in coverage.REASONS["partial"], "only a source gap counts basins"
