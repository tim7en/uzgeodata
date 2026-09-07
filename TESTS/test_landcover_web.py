from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "PIPELINES"))
import build_landcover_web as web  # noqa: E402


def test_projection_keeps_ontology_identity_and_ignores_foreign_basins(tmp_path, monkeypatch):
    reference = tmp_path / "basins.geojson"
    reference.write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"HYBAS_ID": 1, "PFAF_ID": 11,
                                                   "SUB_AREA": 10}, "geometry": None},
            {"type": "Feature", "properties": {"HYBAS_ID": 2, "PFAF_ID": 12,
                                                   "SUB_AREA": 20}, "geometry": None},
        ],
    }), encoding="utf8")
    source = tmp_path / "landcover.csv"
    with source.open("w", encoding="utf8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["dataset_id", "basin_id", "unit_name", "year",
                         "class_code", "class_name", "km2"])
        writer.writerow(["esri-io-landcover-10m", 1, 1, 2017, 5, "Crops", 4.5])
        writer.writerow(["esri-io-landcover-10m", 1, 1, 2018, 5, "Crops", 5.5])
        writer.writerow(["esri-io-landcover-10m", 999, 999, 2018, 5, "Crops", 99])

    monkeypatch.setattr(web, "REFERENCE", reference)
    monkeypatch.setattr(web, "SOURCE", source)
    index, series = web.build()

    assert index["ontology"] == {
        "subject": "uz:ds/esri-io-landcover-10m",
        "predicate": "uz:hasBasinStatistic",
        "objectType": "Basin",
        "identifierScheme": "HYBAS_ID",
        "distribution": "uz:dist/landcover-basin-year",
    }
    assert index["coverage"]["sourceRows"] == 2
    assert index["coverage"]["measuredBasins"] == 1
    assert index["coverage"]["measuredBasinYears"] == 2
    assert index["coverage"]["expectedBasinYears"] == 18
    assert set(series["basins"]) == {"1"}
    assert series["basins"]["1"]["years"]["2018"]["5"] == 5.5
