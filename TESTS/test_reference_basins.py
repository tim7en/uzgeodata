from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "PUBLISHED/data/hydroclimate"


def load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def frame_ids() -> set[int]:
    return {
        int(feature["properties"]["HYBAS_ID"])
        for feature in load("basins-level12.geojson")["features"]
    }


def test_every_reference_basin_carries_the_atlas_attributes():
    columns = load("reference-basin-attributes.json")
    assert set(columns["ids"]) == frame_ids()
    assert columns["joinKey"] == "hybas_id"
    assert len(columns["columns"]) == 281
    for column in columns["columns"]:
        assert len(columns["values"][column]) == len(columns["ids"]), column


def test_the_csv_and_the_column_store_agree():
    columns = load("reference-basin-attributes.json")
    with (DATA / "reference-basin-attributes.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(columns["ids"])
    assert [int(row["hybas_id"]) for row in rows] == columns["ids"]
    probe = columns["columns"][0]
    for index in (0, len(rows) // 2, len(rows) - 1):
        stored = columns["values"][probe][index]
        published = rows[index][probe]
        assert (published == "" and stored is None) or float(published) == stored


def test_basin_specific_and_accumulation_never_overlap():
    """Summing an upstream column across basins counts the same water twice."""
    groups = load("reference-attribute-groups.json")["groups"]
    members = {
        group["id"]: {attribute["column"]
                      for category in group["categories"]
                      for attribute in category["attributes"]}
        for group in groups
    }
    assert set(members) == {"basin_specific", "basin_accumulation"}
    assert not members["basin_specific"] & members["basin_accumulation"]
    assert len(members["basin_specific"] | members["basin_accumulation"]) == 281

    extents = {
        attribute["column"]: attribute["spatialExtent"]
        for group in groups
        for category in group["categories"]
        for attribute in category["attributes"]
    }
    assert all(extents[column] == "s" for column in members["basin_specific"])
    assert all(extents[column] in {"u", "p"} for column in members["basin_accumulation"])


def test_each_group_is_broken_into_readable_categories():
    for group in load("reference-attribute-groups.json")["groups"]:
        assert group["label"]
        assert group["attributeCount"] == sum(len(c["attributes"]) for c in group["categories"])
        for category in group["categories"]:
            assert category["id"]
            for attribute in category["attributes"]:
                assert attribute["label"] and attribute["spatialExtentLabel"]


def test_the_display_layer_separates_the_two_river_systems():
    features = load("reference-basins-level12.geojson")["features"]
    assert len(features) == len(frame_ids())
    systems = {feature["properties"]["system_id"] for feature in features}
    assert systems == {"amu_darya", "syr_darya"}
    for feature in features:
        props = feature["properties"]
        assert props["area_km2"] > 0
        assert props["flow_position"] in {"runoff_formation", "transit", "endorheic_sink"}


def test_the_reference_frame_declares_what_it_is():
    manifest = load("reference-basins.manifest.json")
    assert manifest["observationClass"] == "reference"
    assert manifest["basinLevel"] == 12
    assert manifest["counts"]["basinSpecificAttributes"] == 190
    assert manifest["counts"]["accumulationAttributes"] == 91
    assert any("never be mixed" in note for note in manifest["qualityNotes"])
