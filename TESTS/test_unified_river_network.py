from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "PUBLISHED/data"


def load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def test_unified_graph_contains_the_complete_routed_systems():
    graph = load("hydrography/relationships-unified.json")
    rivers = graph["rivers"]
    ids = {int(row["id"]) for row in rivers}
    assert len(ids) == len(rivers) == graph["counts"]["rivers"]
    assert graph["spatialScope"] == "full_basin"
    assert graph["integrity"]["danglingRiverTargets"] == 0
    assert all(not int(row["nextDown"]) or int(row["nextDown"]) in ids for row in rivers)


def test_every_reach_resolves_to_a_published_level_12_basin():
    graph = load("hydrography/relationships-unified.json")
    basin_ids = {int(row["id"]) for row in graph["basins"]}
    assert basin_ids
    assert all(int(row["basinId"]) in basin_ids for row in graph["rivers"])
    assert graph["integrity"]["unresolvedRiverBasins"] == 0


def test_the_unified_graph_adds_reaches_outside_the_national_cut():
    graph = load("hydrography/relationships-unified.json")
    national = load("hydrography/relationships.json")
    national_ids = {int(row["id"]) for row in national["rivers"]}
    unified_ids = {int(row["id"]) for row in graph["rivers"]}
    assert len(unified_ids - national_ids) == graph["counts"]["riversPreviouslyUnavailable"]
    assert graph["counts"]["riversPreviouslyUnavailable"] > 30_000
    assert unified_ids & national_ids


def test_both_river_systems_and_all_flow_positions_are_present():
    graph = load("hydrography/relationships-unified.json")
    assert set(graph["countsBySystem"]) == {"amu_darya", "syr_darya"}
    assert {row["systemId"] for row in graph["rivers"]} == {"amu_darya", "syr_darya"}
    assert {row["flowPosition"] for row in graph["rivers"]} >= {
        "runoff_formation", "transit", "endorheic_sink"
    }
