"""Open-data surrogate registry, reduction kernels and published-run accounting."""
import csv
import json
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ATLAS_MODULES.hydrosheds.functions import surrogates as sg

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = json.loads((ROOT / "ATLAS_MODULES/hydrosheds/surrogates.json").read_text(encoding="utf-8"))
RECIPES = json.loads((ROOT / "ATLAS_MODULES/hydrosheds/recipes.json").read_text(encoding="utf-8"))


def square(identifier, next_down, west):
    ring = [[west, 0], [west + 1, 0], [west + 1, 1], [west, 1], [west, 0]]
    return {"properties": {"HYBAS_ID": identifier, "NEXT_DOWN": next_down},
            "geometry": {"type": "Polygon", "coordinates": [ring]}}


class Timer:
    def event(self, message, **details):
        pass


@pytest.fixture
def domain(tmp_path):
    features = [square(1, 2, 0), square(2, 0, 1)]
    zones = np.array([[1, 2, 2]])
    areas = np.array([[1.0e6, 2.0e6, 3.0e6]])
    return sg.Domain(features, {"1": {"1"}, "2": {"1", "2"}}, zones, areas,
                     [sg.CELL, 0, 0, 0, -sg.CELL, 1], 3, 1, (0, 0, 2, 1), tmp_path, Timer(), True)


def test_registry_covers_every_attribute_and_names_real_builders():
    columns = [a["column"] for a in RECIPES["attributes"]]
    families = REGISTRY["families"]
    assert sum(entry["attribute_count"] for entry in families.values()) == len(columns) == 281
    assert sorted(c for entry in families.values() for c in entry["attribute_columns"]) == sorted(columns)
    for name, entry in families.items():
        assert entry["fidelity"] in REGISTRY["fidelity_classes"], name
        assert set(entry["resolution"]) >= {"native_scale_m", "grid", "processing_grid_arcsec"}, name
        assert entry["resolution"]["processing_grid_arcsec"] == 15.0, name
        assert set(entry["units"]) == {"surrogate", "reference_stored", "convertible", "factor"}, name
        assert entry["surrogate"]["catalogue_url"].startswith("http"), name
        if entry["executable"] and not entry.get("handled_by"):
            assert entry["builder"] in sg.BUILDERS, name
        else:
            assert entry.get("pending_reason") or entry.get("handled_by"), name
    assert "WWF/HydroATLAS/v1/Basins/level12" in REGISTRY["excluded_sources"]


def test_class_crosswalks_stay_inside_their_target_legends():
    assert set(sg.GLC2000_FROM_COPERNICUS.values()) <= set(range(1, 23))
    assert set(sg.EARTHSTAT_PNV_FROM_BIOME00K.values()) <= set(range(1, 16))
    assert len(sg.GLC2000_FROM_COPERNICUS) == len(set(sg.GLC2000_FROM_COPERNICUS))
    # A crosswalk that mapped every legend position would hide the classes it cannot reach.
    assert set(range(1, 23)) - set(sg.GLC2000_FROM_COPERNICUS.values())


def test_upstream_column_swaps_only_the_support_character():
    assert sg.upstream_column("cly_pc_sav") == "cly_pc_uav"
    assert sg.upstream_column("glc_pc_s07") == "glc_pc_u07"
    with pytest.raises(ValueError, match="not a local-support column"):
        sg.upstream_column("dis_m3_pyr")


def test_reductions_weight_upstream_support_and_accumulate_densities(domain):
    values = np.array([[10.0, 30.0, 50.0]])
    local = sg.reduce_general(values, domain, "s")
    upstream = sg.reduce_general(values, domain, "u")
    assert local["2"]["raw_value"] == 40.0
    assert upstream["2"]["raw_value"] == pytest.approx((10 * 1 + 30 * 2 + 50 * 3) / 6)
    assert upstream["2"]["support_basin_count"] == 2 and upstream["2"]["expected_cells"] == 3
    density = np.array([[2.0, 2.0, 2.0]])
    assert sg.reduce_general(density, domain, "s", "sum_over_km2")["2"]["raw_value"] == pytest.approx(10.0)
    assert sg.reduce_general(density, domain, "u", "sum_over_m2")["2"]["raw_value"] == pytest.approx(12.0e6)
    values[0, 2] = np.nan
    partial = sg.reduce_general(values, domain, "u")
    assert partial["2"]["coverage_fraction"] == pytest.approx(2 / 3)
    assert sg.reduce_general(np.full((1, 3), np.nan), domain, "s")["1"]["raw_value"] is None


def test_majority_reports_the_largest_share_and_nothing_when_all_are_zero(domain):
    fractions = {1: np.array([[80.0, 10.0, 10.0]]), 2: np.array([[20.0, 90.0, 90.0]])}
    majority = sg.majority_from_fractions(fractions, domain, "s")
    assert majority["1"]["raw_value"] == 1.0 and majority["2"]["raw_value"] == 2.0
    assert majority["2"]["class_share_percent"] == pytest.approx(90.0)
    empty = sg.majority_from_fractions({1: np.zeros((1, 3)), 2: np.zeros((1, 3))}, domain, "s")
    assert empty["1"]["raw_value"] is None


def test_vector_cover_uses_exact_geodesic_shares(domain):
    from shapely.geometry import shape
    half = shape({"type": "Polygon", "coordinates": [[[0, 0], [0.5, 0], [0.5, 1], [0, 1], [0, 0]]]})
    cover = sg.vector_cover([half], domain, "s")
    assert cover["1"]["raw_value"] == pytest.approx(50.0, abs=0.5)
    assert cover["2"]["raw_value"] == pytest.approx(0.0)
    assert sg.vector_cover([], domain, "s")["1"]["raw_value"] == pytest.approx(0.0)
    upstream = sg.vector_cover([half], domain, "u")
    assert 0 < upstream["2"]["raw_value"] < cover["1"]["raw_value"]


def test_moisture_index_is_bounded_and_signed_by_the_water_balance():
    precipitation = np.array([100.0, 50.0, 100.0])
    potential = np.array([50.0, 100.0, 100.0])
    index = sg.moisture_index(precipitation, potential)
    assert index.tolist() == [0.5, -0.5, 0.0]
    assert np.all(np.abs(index) <= 1)


def test_published_run_keeps_surrogates_separate_from_reproduction():
    batch = json.loads((ROOT / "PUBLISHED/data/atlas/batch-latest.json").read_text(encoding="utf-8"))
    attributes = batch["attributes"]
    assert len(attributes) == 281
    estimated = [a for a in attributes if a["surrogate_status"] == "open_surrogate_estimate"]
    assert len(estimated) == batch["surrogate_attributes"]
    assert sum(batch["surrogate_by_fidelity"].values()) == len(estimated)
    assert not any(a["surrogate_is_reproduction"] for a in attributes)
    assert batch["independently_reproduced"] == 0
    assert batch["attributes_without_any_estimate"] == sum(
        1 for a in attributes if a["candidate_status"] != "computed_candidate"
        and a["surrogate_status"] != "open_surrogate_estimate")
    for attribute in attributes:
        plan = batch["surrogate_families"][attribute["surrogate_family"]]
        if attribute["surrogate_status"] == "open_surrogate_estimate":
            assert set(attribute["surrogate_values"]) == set(batch["basin_ids"]), attribute["column"]
            assert plan["resolution"]["processing_grid_arcsec"] == 15.0
            if plan["units"]["factor"] is None:
                assert attribute["surrogate_divergence"]["comparable"] is False
        else:
            assert attribute["surrogate_values"] is None
            assert plan.get("pending_reason") or plan.get("handled_by") or plan.get("pending_dimensions")


def test_published_surrogate_registry_records_resolution_for_every_attribute():
    batch = json.loads((ROOT / "PUBLISHED/data/atlas/batch-latest.json").read_text(encoding="utf-8"))
    path = ROOT / "PUBLISHED/data/atlas/runs" / batch["run_id"] / "surrogate-registry.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 281 and len({r["attribute"] for r in rows}) == 281
    assert all(r["is_reproduction"] == "False" for r in rows)
    for row in rows:
        assert row["processing_grid_arcsec"] == "15.0", row["attribute"]
        if row["status"] == "open_surrogate_estimate":
            assert row["asset"] and row["licence"] and row["catalogue_url"].startswith("http")
            assert row["native_scale_m"] or row["native_grid"] == "vector polygons", row["attribute"]
            assert row["resampling"], row["attribute"]
        else:
            assert row["pending_reason"], row["attribute"]
