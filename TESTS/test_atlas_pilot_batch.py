"""Scientific fixtures: temporal order, contributing support, encoding and gates."""
from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ATLAS_MODULES.hydrosheds.functions.pilot_batch import (
    climate_fields, reduce_field, upstream_members, physical_encoding, clean_value, compare_candidate)


def test_temperature_extremes_are_monthly_tavg_before_spatial_mean():
    monthly = {f"{v}_{m:02d}": np.array([[float(m), float(13-m)]])
               for v in ("tmp", "pre") for m in range(1, 13)}
    fields = climate_fields(monthly)
    assert len(fields) == 30
    assert fields["tmp_dc_smn"].tolist() == [[1, 1]]
    assert fields["tmp_dc_smx"].tolist() == [[12, 12]]
    assert fields["tmp_dc_syr"].tolist() == [[6.5, 6.5]]
    assert fields["pre_mm_syr"].tolist() == [[78, 78]]
    monthly["pre_02"][0, 0] = np.nan
    assert np.isnan(climate_fields(monthly)["pre_mm_syr"][0, 0])


def test_upstream_unique_weighted_support_and_missing_cells():
    features = [{"properties": {"HYBAS_ID": 1, "NEXT_DOWN": 2}},
                {"properties": {"HYBAS_ID": 2, "NEXT_DOWN": 0}}]
    members = upstream_members(features, [{"hybas_id": "1", "next_down": "2"}])
    assert members == {"1": {"1"}, "2": {"1", "2"}}
    values, zones, areas = np.array([[10., 30., 50.]]), np.array([[1, 2, 2]]), np.array([[1., 2., 3.]])
    local = reduce_field(values, features, zones, areas, members, "s")
    upstream = reduce_field(values, features, zones, areas, members, "u")
    assert local["2"]["raw_value"] == 40
    assert upstream["2"]["raw_value"] == pytest.approx(220/6)
    assert upstream["2"]["expected_cells"] == 3
    values[0, 2] = np.nan
    assert reduce_field(values, features, zones, areas, members, "u")["2"]["coverage_fraction"] == 2/3
    with pytest.raises(ValueError, match="omits contributing"):
        upstream_members(features, [{"hybas_id": "3", "next_down": "1"}])
    features[1]["properties"]["NEXT_DOWN"] = 1
    with pytest.raises(ValueError, match="Cycle"):
        upstream_members(features, [])


def test_storage_encoding_nodata_and_strict_comparison():
    assert physical_encoding("tmp_dc_syr", "degrees Celsius (x10)") == (0.1, "degrees Celsius")
    assert physical_encoding("dor_pc_pva", "percent (x10)") == (0.1, "percent")
    assert physical_encoding("pop_ct_sum", "count (thousands)") == (1000., "people")
    assert physical_encoding("lkv_mc_usu", "million cubic meters") == (1e6, "cubic meters")
    assert clean_value(-9999) is None and clean_value(0) == 0 and clean_value(-10) == -10
    candidate = {"1": {"raw_value": 10.5, "coverage_fraction": 1.0}}
    assert compare_candidate({"1": 10.}, candidate, 1)["pass"]
    assert not compare_candidate({"1": 10., "2": 20.}, candidate, 1)["pass"]
    candidate["1"]["coverage_fraction"] = .99
    assert not compare_candidate({"1": 10.}, candidate, 1)["pass"]


def test_published_batch_has_complete_pilot_and_honest_release_gates():
    import csv
    import json
    root = Path(__file__).resolve().parents[1]
    batch = json.loads((root / "PUBLISHED/data/atlas/batch-latest.json").read_text(encoding="utf-8"))
    assert batch["basin_count"] == 20 and batch["attribute_count"] == 281
    assert len(batch["attributes"]) == 281 and len(set(batch["basin_ids"])) == 20
    assert all(set(a["reference_values"]) == set(batch["basin_ids"]) for a in batch["attributes"])
    assert batch["independently_reproduced"] == 0
    assert not any(a["scientifically_reproduced"] for a in batch["attributes"])
    assert batch["candidate_attributes"] + batch["pending_attributes"] == 281
    assert batch["numerical_pass_attributes"] == sum(bool(a["comparison"] and a["comparison"]["pass"]) for a in batch["attributes"])
    directory = root / "PUBLISHED/data/atlas/runs" / batch["run_id"]
    with (directory / "observations.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == len({(r["hybas_id"], r["attribute"]) for r in rows}) == 5620
    assert all(not r["observation_year"] for r in rows)
    assert sum(bool(r["reference_raw"]) for r in rows) == batch["reference_nonmissing"]
    assert all(not r["candidate_raw"] for r in rows if r["candidate_status"] == "pending_original_inputs")
    timing = batch["timing"]
    assert timing["wall_seconds"] >= sum(s["wall_seconds"] for s in timing["stages"])
