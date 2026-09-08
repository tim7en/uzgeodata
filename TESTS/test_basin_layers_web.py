from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "PIPELINES"))
import build_basin_layers_web as web  # noqa: E402


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", encoding="utf8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def test_monthly_layer_pivots_by_basin_period_variable(tmp_path):
    source = tmp_path / "cfsv2.csv"
    write_csv(source, ["basin_id", "year", "month", "variable", "value", "unit"], [
        [1, 2024, 1, "precipitation", 0.5, "mm/day"],
        [1, 2024, 2, "precipitation", 1.5, "mm/day"],
        [2, 2024, 1, "precipitation", 2.0, "mm/day"],
    ])
    layer = {**next(item for item in web.LAYERS if item["id"] == "cfsv2-basin-monthly"), "source": source}
    entry, series = web.build_layer(layer)

    assert series["basins"]["1"]["2024-01"]["precipitation"] == {"v": 0.5}
    assert series["basins"]["1"]["2024-02"]["precipitation"] == {"v": 1.5}
    assert entry["coverage"] == {"rows": 3, "basins": 2, "periods": 2}
    assert entry["periods"] == ["2024-01", "2024-02"]
    assert {v["code"] for v in entry["variables"]} == {"precipitation"}


def test_anomaly_layer_carries_z_score_and_classification(tmp_path):
    source = tmp_path / "anomaly.csv"
    write_csv(source, ["basin_id", "year", "month", "variable", "value", "unit",
                       "z_score", "classification"], [
        [1, 2024, 1, "precipitation", 0.0, "mm/day", -1.5, "dry"],
    ])
    layer = {**next(item for item in web.LAYERS if item["id"] == "cfsv2-basin-anomaly"), "source": source}
    entry, series = web.build_layer(layer)
    assert series["basins"]["1"]["2024-01"]["precipitation"] == {"v": 0.0, "z": -1.5, "c": "dry"}
    assert entry["kind"] == "anomaly"


def test_pentad_layer_keys_periods_with_a_pentad_suffix(tmp_path):
    source = tmp_path / "chirps.csv"
    write_csv(source, ["basin_id", "year", "month", "pentad", "variable", "value", "unit"], [
        [1, 2024, 6, 3, "precipitation_total", 4.2, "mm"],
    ])
    layer = {**next(item for item in web.LAYERS if item["id"] == "chirps-v3-basin-pentad"), "source": source}
    entry, _ = web.build_layer(layer)
    assert entry["periods"] == ["2024-06-p3"]


def test_ghm_layer_keeps_only_the_basin_frame(tmp_path):
    source = tmp_path / "ghm.csv"
    write_csv(source, ["frame", "unit_id", "unit_kind", "epoch", "variable", "value", "unit"], [
        ["basin", 1, "Basin", 2016, "ghm_mean", 0.2, "index_0_1"],
        ["district", 1, "District", 2016, "ghm_mean", 0.6, "index_0_1"],
    ])
    layer = {**web.LAYERS[-1], "source": source}  # ghm-basin-modification: filtered to frame == basin
    entry, series = web.build_layer(layer)
    assert entry["coverage"]["rows"] == 1
    assert series["basins"]["1"]["2016"]["ghm_mean"] == {"v": 0.2}


def test_layer_index_exposes_a_weighted_quality_signal(tmp_path):
    source = tmp_path / "quality.csv"
    write_csv(source, ["basin_id", "year", "month", "variable", "value", "unit", "quality"], [
        [1, 2024, 1, "precipitation", 1.0, "mm/day", "ok"],
        [2, 2024, 1, "precipitation", 2.0, "mm/day", "ok-interpolated"],
        [3, 2024, 1, "precipitation", 9999, "mm/day", "implausible"],
    ])
    layer = {**next(item for item in web.LAYERS if item["id"] == "cfsv2-basin-monthly"), "source": source}
    entry, _ = web.build_layer(layer)

    assert entry["quality"]["validPercent"] == 100.0
    assert entry["quality"]["scorePercent"] == 55.0
    assert entry["quality"]["states"] == {
        "implausible": 1,
        "ok": 1,
        "ok-interpolated": 1,
    }


def test_headwater_layer_uses_transboundary_geometry():
    layer = next(item for item in web.LAYERS if item["id"] == "era5-land-headwaters-monthly")
    entry, _ = web.build_layer(layer)
    assert entry["geometry"] == "/data/hydroclimate/headwater-units.geojson"
    assert entry["coverage"]["basins"] == 121
    assert entry["coverage"]["rows"] == entry["coverage"]["basins"] * entry["coverage"]["periods"] * 6


def test_upstream_anomaly_is_the_default_layer_and_declares_fixed_baseline():
    layer = web.LAYERS[0]
    entry, _ = web.build_layer(layer)
    assert entry["id"] == "era5-land-headwater-anomaly"
    assert entry["spatialScope"] == "headwater_formation"
    assert entry["baseline"] == "1991-2020"
    assert entry["geometry"] == "/data/hydroclimate/headwater-units.geojson"
    assert entry["coverage"]["basins"] == 121


def test_daily_system_layer_uses_system_identifier():
    layer = next(item for item in web.LAYERS if item["id"] == "modis-snow-headwater-daily")
    entry, _ = web.build_layer(layer)
    assert entry["periodGrain"] == "day"
    assert entry["geometryIdColumn"] == "system_id"
    assert entry["coverage"]["basins"] == 2
