import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from PIPELINES import rebase_terraclimate_v11 as rebase


def setup(tmp_path, monkeypatch, years=(2003, 2004), drop=None):
    source, history = tmp_path / "source", tmp_path / "history"
    source.mkdir()
    history.mkdir()
    monkeypatch.setattr(rebase, "SOURCE", source)
    names = list(rebase.SERIES.values())
    series = {name: {"label": name, "unit": "u", "source": "terraclimate", "values": [1.0] * 36}
              for name in names}
    series["run_mm_s"] = {"label": "runoff", "unit": "mm", "source": "era5_runoff", "values": [7.0] * 36}
    for basin in ("1", "2"):
        (history / f"{basin}.json").write_text(json.dumps(
            {"basin_id": basin, "years": [2003, 2005], "months": 36, "series": series}))
    (history / "index.json").write_text(json.dumps(
        {"years": [2003, 2005], "months": 36, "observed_months": {},
         "series": {name: {"unit": "u"} for name in [*names, "run_mm_s"]}}))
    for year in years:
        rows = [{"basin_id": basin, "year": year, "month": month, "variable": variable,
                 "value": 100.0 * (basin == "2") + month, "coverage": 1.0, "unit": "u"}
                for basin in ("1", "2") for month in range(1, 13) for variable in rebase.SERIES
                if (basin, year, variable) != drop]
        pq.write_table(pa.Table.from_pylist(rows), source / f"year={year}.parquet")
    return history


def test_the_eleven_series_are_replaced_end_to_end_and_labelled(tmp_path, monkeypatch):
    history = setup(tmp_path, monkeypatch)
    basins, matrices, counts = rebase.load([2003, 2004], 2003, 36)
    assert rebase.check(basins, matrices, counts, 0, 23) == 0
    assert rebase.rebase_history(basins, matrices, 0, 23, "2004-12", "run-x", history) == 2
    record = json.loads((history / "2.json").read_text())
    precipitation = record["series"]["pre_mm_s"]
    assert precipitation["values"][:2] == [101.0, 102.0]
    # Months after the producer's last year are left empty for the provisional product.
    assert precipitation["values"][24:] == [None] * 12
    assert precipitation["product_version"] == "v1.1" and precipitation["extracted_through"] == "2004-12"
    assert precipitation["observed_months"] == 24 and precipitation["missing_months"] == 0
    # ERA5-Land series are not TerraClimate and are not touched.
    assert record["series"]["run_mm_s"]["values"] == [7.0] * 36
    index = json.loads((history / "index.json").read_text())
    assert index["series"]["pre_mm_s"]["source_release"] == "terraclimate-v1.1@climatologylab"
    assert index["appended"][-1]["replaced"].startswith("TerraClimate v1.0")


def test_an_incomplete_producer_year_writes_nothing(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, drop=("2", 2004, "ppt"))
    basins, matrices, counts = rebase.load([2003, 2004], 2003, 36)
    with pytest.raises(RuntimeError, match="Nothing was written"):
        rebase.check(basins, matrices, counts, 0, 23)


def test_a_gap_in_the_producer_years_is_refused(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, years=(2003, 2005))
    with pytest.raises(FileNotFoundError, match="missing years"):
        rebase.years_available(2003)
