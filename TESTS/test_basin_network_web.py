from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "PUBLISHED/data"
NETWORK = DATA / "hydroclimate/basin-network.json"


def network() -> dict:
    return json.loads(NETWORK.read_text(encoding="utf-8"))


def level7_lookup() -> dict[str, str]:
    features = json.loads(
        (DATA / "hydroclimate/basins-level07.geojson").read_text(encoding="utf-8")
    )["features"]
    return {
        str(feature["properties"]["PFAF_ID"]): str(feature["properties"]["HYBAS_ID"])
        for feature in features
    }


def anomaly_series() -> dict:
    index = json.loads((DATA / "basin-layers/index.json").read_text(encoding="utf-8"))
    layer = next(entry for entry in index["layers"] if entry.get("kind") == "anomaly")
    path = DATA / layer["series"].removeprefix("/data/")
    return json.loads(path.read_text(encoding="utf-8"))["basins"]


def test_the_network_carries_every_level_of_the_natural_frame():
    payload = network()
    assert set(payload["levels"]) == {"7", "10", "12"}
    for level, entry in payload["levels"].items():
        published = json.loads(
            (DATA / f"hydroclimate/basins-level{int(level):02d}.geojson").read_text(encoding="utf-8")
        )["features"]
        assert entry["counts"]["units"] == len(published)
        assert entry["geometry"].endswith(f"basins-level{int(level):02d}.geojson")


def test_an_upstream_unit_outside_uzbekistan_is_findable():
    """The national extraction stops at the border; this frame must not."""
    units = {int(record["id"]): record for record in network()["levels"]["7"]["basins"]}
    unit = units[4070529600]
    assert unit["pfafId"] == 4619503
    assert unit["systemId"] == "amu_darya"
    assert unit["inHeadwaterFormation"] is True
    assert unit["flowPosition"] == "runoff_formation"

    national = json.loads((DATA / "hydrography/relationships.json").read_text(encoding="utf-8"))
    assert 4070529600 not in {int(basin["id"]) for basin in national["basins"]}


def test_the_view_opens_on_a_control_section_not_on_the_terminal_lake():
    payload = network()
    focus = payload["defaultFocus"]
    assert focus["level"] == payload["defaultLevel"]
    sections = {section["id"] for section in payload["controlSections"] if section["level"] == focus["level"]}
    assert focus["id"] in sections
    units = {record["id"]: record for record in payload["levels"][str(focus["level"])]["basins"]}
    assert units[focus["id"]]["isControlSection"] is True
    assert not units[focus["id"]]["endorheic"] or units[focus["id"]]["inHeadwaterFormation"]


def test_every_formation_unit_resolves_to_a_temporal_signal():
    """The trace view reads the level-7 anomaly through a Pfafstetter prefix."""
    lookup = level7_lookup()
    series = anomaly_series()
    payload = network()
    level = str(payload["defaultLevel"])
    formation = [record for record in payload["levels"][level]["basins"] if record["inHeadwaterFormation"]]
    assert formation
    unresolved = [
        record["id"] for record in formation
        if lookup.get(str(record["pfafId"])[:7]) not in series
    ]
    assert not unresolved


def test_control_sections_cover_both_pilot_systems_at_every_level():
    payload = network()
    by_level = {}
    for section in payload["controlSections"]:
        by_level.setdefault(section["level"], set()).add(section["headwaterSystemId"])
    assert set(by_level) == {7, 10, 12}
    assert all(systems == {"upper_amu_darya", "upper_syr_darya"} for systems in by_level.values())
