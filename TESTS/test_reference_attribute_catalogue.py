from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "PUBLISHED/data/hydroclimate"


def catalogue() -> dict:
    return json.loads((DATA / "reference-attribute-catalogue.json").read_text(encoding="utf-8"))


def test_every_attribute_names_its_source_citation_and_licence():
    """A number without provenance is an anonymous number."""
    payload = catalogue()
    assert payload["counts"]["variables"] == len(payload["variables"])
    for variable in payload["variables"]:
        assert variable["source"], variable["code"]
        assert variable["citation"], variable["code"]
        assert variable["licence"], variable["code"]
        assert variable["description"], variable["code"]
        assert variable["category"] in payload["categories"]
        assert variable["columnCount"] == len(variable["columns"])


def test_the_catalogue_covers_exactly_the_published_columns():
    payload = catalogue()
    with (DATA / "reference-basin-attributes.csv").open(encoding="utf-8", newline="") as handle:
        published = [name for name in csv.DictReader(handle).fieldnames if name != "hybas_id"]
    catalogued = {column["column"] for variable in payload["variables"] for column in variable["columns"]}
    assert catalogued == set(published)
    assert set(payload["columnIndex"]) == set(published)
    assert payload["counts"]["columns"] == len(published) == 281


def test_each_column_keeps_its_local_or_upstream_kind():
    payload = catalogue()
    groups = json.loads((DATA / "reference-attribute-groups.json").read_text(encoding="utf-8"))
    expected = {
        attribute["column"]: group["id"]
        for group in groups["groups"]
        for category in group["categories"]
        for attribute in category["attributes"]
    }
    for column, entry in payload["columnIndex"].items():
        assert entry["group"] == expected[column], column


def test_the_catalogue_states_what_it_is_bound_to():
    bound = catalogue()["scheme"]["boundTo"]
    assert bound["joinKey"] == "hybas_id"
    assert bound["basins"] == 7445
    assert "HYBAS_L12" in bound["reachJoin"]
    scheme = catalogue()["scheme"]
    assert scheme["reference"].startswith("Linke")
    assert scheme["website"].startswith("https://")
    assert scheme["catalogueSource"]
