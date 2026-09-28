"""Check the regional grid weights and one-pass upstream accumulation."""
import json

import duckdb
import geopandas as gpd
import numpy as np
from rasterio.transform import from_origin
from shapely.geometry import box

from PIPELINES import extract_regional_climate_grids as grids
from PIPELINES.model_regional_climate_continuation import accumulate_one
from PIPELINES.model_regional_climate_continuation import OUT, TEST_END, TRAIN_END, VERSION, frame


def continued_through():
    """(year, month, months since the record ends) of the published continuation."""
    through = json.loads((OUT / "report.json").read_text())["continuation_through"]
    year, month = map(int, through.split("-"))
    return year, month, (year - TEST_END - 1) * 12 + month


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
    continuation = OUT / f"{VERSION}-continuation.parquet"
    upstream = OUT / "upstream.parquet"
    assert report["basins"] == 7445
    assert report["held_out_years"] == [TRAIN_END + 1, TEST_END]
    last_year, _, _ = continued_through()
    # The estimate starts the month after the record ends, and is one product.
    assert con.execute("SELECT min(year),max(year),count(DISTINCT status) FROM read_parquet(?)",
                       [str(continuation)]).fetchone() == (TEST_END + 1, last_year, 1)
    basins = frame()
    con.register("basins", basins)
    for system in ("amu_darya", "syr_darya"):
        outlet = basins.loc[basins.system_id.eq(system) & basins.next_down.eq("0"), "basin_id"].iloc[0]
        independent = con.execute("""
            SELECT sum(d.estimate*b.area_km2)*0.001
            FROM read_parquet(?) d JOIN basins b USING(basin_id)
            WHERE b.system_id=? AND d.year=? AND d.month=1 AND d.variable='precipitation'
        """, [str(continuation), system, TEST_END + 1]).fetchone()[0]
        accumulated = con.execute("""
            SELECT upstream_integral_mcm, coverage_fraction FROM read_parquet(?)
            WHERE basin_id=? AND year=? AND month=1 AND variable='precipitation'
              AND product=?
        """, [str(upstream), outlet, TEST_END + 1, f"estimated_{VERSION}_continuation"]).fetchone()
        assert accumulated[1] == 1.0
        assert abs(accumulated[0] - independent) < 1e-6


def test_modal_download_matches_versioned_source_rows():
    basin_id = "4120050220"
    record = json.loads((OUT / "basins" / f"{basin_id}.json").read_text())
    assert record["basin_id"] == basin_id
    estimated = f"estimated_{VERSION}"
    # A producer year the record already holds is not repeated as a second product.
    later = [p for p in (OUT / "terraclimate-v1.1").glob("year=*.parquet") if int(p.stem.split("=")[1]) > TEST_END]
    assert any(key.startswith("direct_v1.1:") for key in record["series"]) == bool(later)
    assert all(key.split(":")[0] in (estimated, "direct_v1.1") for key in record["series"])
    estimate = record["series"][f"{estimated}:local:precipitation"]
    year, month, months = continued_through()
    assert len(estimate["rows"]) == months
    assert estimate["rows"][0][:2] == [TEST_END + 1, 1]
    assert estimate["rows"][-1][:2] == [year, month]
    runoff = record["series"][f"{estimated}:local:q"]
    assert len(runoff["rows"]) == months
    assert all(row[2] >= 0 for row in runoff["rows"])
    source = duckdb.connect().execute("""
        SELECT estimate FROM read_parquet(?) WHERE basin_id=? AND year=? AND month=1 AND variable='precipitation'
    """, [str(OUT / f"{VERSION}-continuation.parquet"), basin_id, TEST_END + 1]).fetchone()[0]
    assert abs(estimate["rows"][0][2] - source) < 1e-10


def test_water_balance_continuation_only_publishes_variables_that_beat_climatology():
    report = json.loads((OUT / "water-balance-report.json").read_text())
    assert report["held_out_years"] == [TRAIN_END + 1, TEST_END]
    for variable in report["eligible_variables"]:
        for system in ("amu_darya", "syr_darya"):
            scores = report["validation"][variable][system]
            assert scores["era_adjusted"]["rmse"] < scores["seasonal_climatology"]["rmse"]
            assert scores["era_adjusted"]["mae"] < scores["seasonal_climatology"]["mae"]
    con = duckdb.connect()
    path = str(OUT / f"{VERSION}-water-balance-continuation.parquet")
    rows, basins, first, last = con.execute(
        "SELECT count(*), count(DISTINCT basin_id), min(year*100+month), max(year*100+month) "
        "FROM read_parquet(?)", [path]).fetchone()
    year, month, months = continued_through()
    assert (basins, first, last) == (7445, (TEST_END + 1) * 100 + 1, year * 100 + month)
    assert rows == 7445 * months * len(report["eligible_variables"])
    assert con.execute("SELECT count(*) FROM read_parquet(?) WHERE estimate IS NULL OR NOT isfinite(estimate) "
                       "OR (variable <> 'PDSI' AND estimate < 0)", [path]).fetchone()[0] == 0
