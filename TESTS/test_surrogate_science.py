"""The published surrogate science record must stay tied to a real run and claim nothing extra."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "PUBLISHED/data/atlas/surrogate-science.json"


@pytest.fixture(scope="module")
def record():
    return json.loads(RECORD.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def batch():
    return json.loads((ROOT / "PUBLISHED/data/atlas/batch-latest.json").read_text(encoding="utf-8"))


def test_record_matches_the_run_it_cites(record, batch):
    assert record["run_id"] == batch["run_id"]
    assert (ROOT / "PUBLISHED/data/atlas/runs" / record["run_id"] / "surrogate-registry.csv").is_file()
    pilot = record["pilot"]
    for key in ("attributes", "candidates", "surrogates", "without_estimate", "independently_reproduced"):
        source = {"attributes": "attribute_count", "candidates": "candidate_attributes",
                  "surrogates": "surrogate_attributes", "without_estimate": "attributes_without_any_estimate",
                  "independently_reproduced": "independently_reproduced"}[key]
        assert pilot[key] == batch[source], key
    assert pilot["independently_reproduced"] == 0
    assert sum(pilot["by_fidelity"].values()) == pilot["surrogates"]


def test_every_family_is_present_and_accounted_for(record):
    families = record["families"]
    assert len(families) == 56
    assert sum(f["attributes"] for f in families) == record["pilot"]["attributes"]
    assert sum(f["estimated_attributes"] for f in families) == record["pilot"]["surrogates"]
    assert all(f["estimated_attributes"] <= f["attributes"] for f in families)
    mixed = [f for f in families if f["status"] == "partial_surrogate"]
    assert all(0 < f["estimated_attributes"] < f["attributes"] for f in mixed)
    for family in families:
        assert family["fidelity"] in record["fidelity_classes"], family["family"]
        if family["estimated_attributes"]:
            assert family["surrogate"]["catalogue_url"].startswith("http"), family["family"]
            assert family["resolution"]["processing_grid_arcsec"] == 15.0
            if not family["units"]["convertible"]:
                assert family["relative_mae_mean"] is None, family["family"]
        else:
            assert family["pending_reason"], family["family"]


def test_scale_projection_separates_measurement_from_extrapolation(record):
    scale = record["scale_projection"]
    measured = scale["measured"]
    assert measured["bincount_pass_seconds"] > 0 and measured["per_basin_mask_seconds"] > 0
    # The label-indexed kernel must be the faster one, or the projection is meaningless.
    assert measured["bincount_pass_seconds"] < measured["per_basin_mask_seconds"] * record["domain"]["basins"]
    assert scale["kernel_speedup_required"] > 1
    assert scale["reduction_minutes_bincount"] < scale["reduction_hours_current_kernel"] * 60
    assert "extrapolat" in scale["basis"].lower()
    assert record["domain"]["basins"] > record["pilot"]["basins"]
    grids = record["domain"]["grids"]
    assert grids["15_arcsec"]["megacells"] < grids["3_arcsec"]["megacells"] < grids["1_arcsec"]["megacells"]


def test_temporal_verification_is_not_claimed_against_the_atlas(record):
    temporal = record["verification"]["temporal"]
    assert temporal["stations"] > 0 and temporal["monthly_records"] > 0
    assert temporal["first_year"] < temporal["last_year"]
    assert set(temporal["testable_families"]) <= {"tmp", "pre"}
    assert "cannot" in temporal["note"]


def test_the_page_and_its_downloads_are_published(record):
    assert (ROOT / "INTERFACE/surrogates.html").is_file()
    assert (ROOT / "INTERFACE/surrogates-main.jsx").is_file()
    assert "surrogates: here('./INTERFACE/surrogates.html')" in \
        (ROOT / "vite.config.mjs").read_text(encoding="utf-8")
    assert (ROOT / "PUBLISHED/data/atlas/surrogates.md").is_file()
    run = ROOT / "PUBLISHED/data/atlas/runs" / record["run_id"]
    for name in ("surrogate-registry.csv", "observations.csv"):
        assert (run / name).is_file(), name
