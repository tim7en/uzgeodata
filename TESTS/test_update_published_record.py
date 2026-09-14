"""Appending fetched months to the published record must not rewrite or misstate earlier ones."""
import json
import pyarrow as pa
import pyarrow.parquet as pq
from PIPELINES import update_published_record as update

PRE = "uzgeodata.dated.v1.pre_mm_s"
TMP = "uzgeodata.dated.v1.tmp_dc_s"


def published(tmp_path):
    history, cube = tmp_path / "history", tmp_path / "cube"
    history.mkdir()
    months = 24  # 2023-2024
    series = lambda name, unit: {"label": name, "unit": unit, "run_ids": ["old"], "methods": ["m@1"],
                                 "values": [1.0] * months, "observed_months": months, "missing_months": 0}
    payload = {"basin_id": "1", "basin_level": 12, "years": [2023, 2024], "months": months,
               "series": {"pre_mm_s": series("precipitation", "millimetres per month"),
                          "tmp_dc_s": series("temperature", "degrees Celsius")}}
    (history / "1.json").write_text(json.dumps(payload))
    (history / "index.json").write_text(json.dumps({
        "years": [2023, 2024], "months": months,
        "series": {"pre_mm_s": {"run_ids": ["old"]}, "tmp_dc_s": {"run_ids": ["old"]}},
        "observed_months": {"1": {"pre_mm_s": months, "tmp_dc_s": months}}}))
    for attribute in (PRE, TMP):
        folder = cube / f"variable={attribute.rsplit('.', 1)[-1]}"
        folder.mkdir(parents=True)
        pq.write_table(pa.table({
            "basin_id": ["1"] * months, "attribute_id": [attribute] * months,
            "year": pa.array([2023 + i // 12 for i in range(months)], pa.int64()),
            "month": pa.array([i % 12 + 1 for i in range(months)], pa.int64()),
            "value": [1.0] * months, "unit": ["u"] * months}), folder / "data_0.parquet")
    (cube / "index.json").write_text(json.dumps({"release": {"store_rows": 1}}))
    return history, cube


def fetched(through_month):
    return [("1", PRE, 2025, month, float(month), "u", "new", "m@2") for month in range(1, through_month + 1)]


def test_published_through_reads_the_cube(tmp_path):
    _, cube = published(tmp_path)
    assert update.published_through([PRE, TMP], cube) == "2024-12"


def test_history_appends_and_marks_what_was_fetched(tmp_path):
    history, _ = published(tmp_path)
    note = {"source": "terraclimate"}
    update.update_history(fetched(3), [PRE], "2025-01", "2025-03", note, history)
    payload = json.loads((history / "1.json").read_text())
    assert payload["years"] == [2023, 2025] and payload["months"] == 36
    pre, tmp = payload["series"]["pre_mm_s"], payload["series"]["tmp_dc_s"]
    assert pre["values"][:24] == [1.0] * 24, "earlier months are untouched"
    assert pre["values"][24:27] == [1.0, 2.0, 3.0]
    assert pre["values"][27:] == [None] * 9, "unfinished months stay null"
    assert pre["extracted_through"] == "2025-03" and pre["missing_months"] == 0
    assert pre["run_ids"] == ["new", "old"] and pre["methods"] == ["m@1", "m@2"]
    assert tmp["extracted_through"] == "2024-12", "the other source is not read as missing 2025"
    assert tmp["values"][24:] == [None] * 12 and tmp["missing_months"] == 0
    index = json.loads((history / "index.json").read_text())
    assert index["years"] == [2023, 2025] and index["appended"] == [note]
    assert index["series"]["tmp_dc_s"]["extracted_through"] == "2024-12"

    # A later run fills in more of the same year without shifting anything.
    update.update_history(fetched(5), [PRE], "2025-04", "2025-05",
                          note, history)
    pre = json.loads((history / "1.json").read_text())["series"]["pre_mm_s"]
    assert pre["values"][24:29] == [1.0, 2.0, 3.0, 4.0, 5.0] and pre["extracted_through"] == "2025-05"


def test_cube_replaces_only_the_fetched_months(tmp_path, monkeypatch):
    _, cube = published(tmp_path)
    # The real registry rightly refuses a cube missing registered variables; this one has two.
    monkeypatch.setattr(update.variables, "registry",
                        lambda coverage, observed_through: {"coverage": coverage, "through": observed_through})
    update.update_cube(fetched(3), [PRE], "2025-01", {"source": "terraclimate"}, cube)
    table = pq.ParquetFile(cube / "variable=pre_mm_s/data_0.parquet").read().to_pylist()
    assert len(table) == 27 and table[-1] == {"basin_id": "1", "attribute_id": PRE, "year": 2025,
                                              "month": 3, "value": 3.0, "unit": "u"}
    assert len(pq.read_table(cube / "variable=tmp_dc_s/data_0.parquet")) == 24
    index = json.loads((cube / "index.json").read_text())
    assert index["months"] == ["2023-01", "2025-03"] and index["rows"] == 51
    assert index["release"] == {"store_rows": 1}, "the store release it came from is not rewritten"
    assert index["registry"]["through"] == {PRE: "2025-03", TMP: "2024-12"}


def test_incomplete_extraction_publishes_nothing():
    import pytest
    with pytest.raises(RuntimeError, match="Nothing was published"):
        update.check_complete(fetched(2), [PRE], 1, "2025-01", "2025-03")
