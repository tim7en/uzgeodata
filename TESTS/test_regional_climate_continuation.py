"""Check the regional grid weights and one-pass upstream accumulation."""
import json

import duckdb
import geopandas as gpd
import numpy as np
from rasterio.transform import from_origin
from shapely.geometry import box

from PIPELINES import extract_regional_climate_grids as grids
from PIPELINES.model_regional_climate_continuation import accumulate_one
from PIPELINES.model_regional_climate_continuation import OUT, frame


def test_fractional_overlap_reduces_each_basin_on_its_own_support(tmp_path, monkeypatch):
    monkeypatch.setattr(grids, "CACHE", tmp_path)
    basins = gpd.GeoDataFrame({"basin_id": ["A", "B"],
                                "geometry": [box(0, 0, 1.5, 1), box(1.5, 0, 2, 1)]})
    indices, cells, weights = grids.grid_weights(basins, from_origin(0, 1, 1, 1), 2, 1)
    result, coverage = grids.reduce_grid(np.array([[10.0, 40.0]]), indices, cells,
                                         weights, 2)
    assert np.allclose(result, [20.0, 40.0])
    assert np.allclose(coverage, [1.0, 1.0])


def test_upstream_accumulation_counts_each_local_unit_once():
    order = ["A", "B", "C"]
    below = {"A": "C", "B": "C", "C": None}
    area = {"A": 1.0, "B": 2.0, "C": 3.0}
    result = accumulate_one({"A": 10.0, "B": 20.0, "C": 30.0}, order, below, area)
    assert result["C"]["area_km2"] == 6
    assert abs(result["C"]["mean"] - 140 / 6) < 1e-12
    assert abs(result["C"]["integral_mcm"] - 0.14) < 1e-12
    partial = accumulate_one({"A": 10.0, "C": 30.0}, order, below, area)
    assert abs(partial["C"]["coverage"] - 4 / 6) < 1e-12


def test_regional_release_keeps_versions_separate_and_closes_upstream_integrals():
    report = json.loads((OUT / "report.json").read_text())
    con = duckdb.connect()
    direct = OUT / "terraclimate-v1.1/year=2025.parquet"
    continuation = OUT / "v1.0-continuation.parquet"
    upstream = OUT / "upstream.parquet"
    assert report["basins"] == 7445
    assert report["continuation_through"] == "2026-08"
    assert con.execute("SELECT count(*), count(DISTINCT basin_id) FROM read_parquet(?)",
                       [str(direct)]).fetchone() == (1_250_760, 7445)
    assert con.execute("SELECT min(year),max(year),count(DISTINCT status) FROM read_parquet(?)",
                       [str(continuation)]).fetchone() == (2025, 2026, 1)
    basins = frame()
    con.register("basins", basins)
    for system in ("amu_darya", "syr_darya"):
        outlet = basins.loc[basins.system_id.eq(system) & basins.next_down.eq("0"), "basin_id"].iloc[0]
        independent = con.execute("""
            SELECT sum(d.value*b.area_km2)*0.001
            FROM read_parquet(?) d JOIN basins b USING(basin_id)
            WHERE b.system_id=? AND d.year=2025 AND d.month=1 AND d.variable='ppt'
        """, [str(direct), system]).fetchone()[0]
        accumulated = con.execute("""
            SELECT upstream_integral_mcm, coverage_fraction FROM read_parquet(?)
            WHERE basin_id=? AND year=2025 AND month=1 AND variable='ppt'
              AND product='terraclimate_v1.1_direct'
        """, [str(upstream), outlet]).fetchone()
        assert accumulated[1] == 1.0
        assert abs(accumulated[0] - independent) < 1e-7


def test_modal_download_matches_versioned_source_rows():
    basin_id = "4120050220"
    record = json.loads((OUT / "basins" / f"{basin_id}.json").read_text())
    assert record["basin_id"] == basin_id
    assert len(record["series"]) == 26
    direct = record["series"]["direct_v1.1:local:ppt"]
    estimate = record["series"]["estimated_v1.0:local:precipitation"]
    assert len(direct["rows"]) == 12
    assert len(estimate["rows"]) == 20
    assert estimate["rows"][-1][:2] == [2026, 8]
    con = duckdb.connect()
    source = con.execute("""
        SELECT value FROM read_parquet(?) WHERE basin_id=? AND year=2025
        AND month=1 AND variable='ppt'
    """, [str(OUT / "terraclimate-v1.1/year=2025.parquet"), basin_id]).fetchone()[0]
    assert abs(direct["rows"][0][2] - source) < 1e-10
