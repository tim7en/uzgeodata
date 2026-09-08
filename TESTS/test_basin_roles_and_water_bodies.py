from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "PUBLISHED/data/hydroclimate"
POSITIONS = {"runoff_formation", "transit", "endorheic_sink"}
CHANNELS = {"perennial", "intermittent", "ephemeral_or_dry", "no_mapped_channel"}


def rows(name: str) -> list[dict]:
    with (DATA / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def manifest(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def test_every_basin_unit_carries_a_position_and_a_channel_class():
    roles = rows("basin-hydrological-roles.csv")
    assert roles
    assert {row["flow_position"] for row in roles} <= POSITIONS
    assert {row["channel_class"] for row in roles} <= CHANNELS
    keys = [(row["basin_level"], row["hybas_id"]) for row in roles]
    assert len(keys) == len(set(keys))
    for level in ("7", "10", "12"):
        assert any(row["basin_level"] == level for row in roles)


def test_position_and_channel_class_stay_independent():
    """A formation unit may be dry and a transit unit may be perennial."""
    pairs = {(row["flow_position"], row["channel_class"]) for row in rows("basin-hydrological-roles.csv")}
    assert ("runoff_formation", "perennial") in pairs
    assert ("transit", "perennial") in pairs
    assert ("transit", "ephemeral_or_dry") in pairs


def test_formation_units_match_the_published_basin_frame():
    frame = json.loads((DATA / "basins-level10.geojson").read_text(encoding="utf-8"))["features"]
    expected = {
        int(feature["properties"]["HYBAS_ID"])
        for feature in frame
        if feature["properties"]["in_headwater_formation"]
    }
    published = {
        int(row["hybas_id"])
        for row in rows("basin-hydrological-roles.csv")
        if row["basin_level"] == "10" and row["flow_position"] == "runoff_formation"
    }
    assert published == expected


def test_a_dry_channel_is_never_reported_as_a_river():
    thresholds = json.loads(
        (ROOT / "ONTOLOGY/vocab/hydroclimate-system.json").read_text(encoding="utf-8")
    )["channelClassThresholdsCms"]
    for row in rows("basin-hydrological-roles.csv"):
        peak = float(row["peak_discharge_cms"])
        if row["channel_class"] == "perennial":
            assert peak >= thresholds["perennial"]
        if row["channel_class"] == "no_mapped_channel":
            assert int(row["reach_count"]) == 0
        if row["channel_class"] == "ephemeral_or_dry":
            assert peak < thresholds["intermittent"]


def test_the_water_body_layer_reaches_beyond_the_national_cut():
    bodies = rows("water-bodies-transboundary.csv")
    reservoirs = [row for row in bodies if row["water_body_type"] == "reservoir"]
    national = json.loads(
        (ROOT / "PUBLISHED/data/hydrography/lakes.geojson").read_text(encoding="utf-8")
    )["features"]
    national_reservoirs = sum(1 for f in national if f["properties"].get("Lake_type") == 2)
    assert len(reservoirs) > national_reservoirs
    assert {row["system_id"] for row in bodies} == {"amu_darya", "syr_darya"}
    assert all(float(row["area_km2"]) > 0 for row in bodies)
    # The reservoirs that decide Uzbekistan's supply sit outside its border.
    assert sum(float(row["total_volume_mcm"]) for row in reservoirs) > 40_000


def test_water_bodies_resolve_to_the_basin_frame():
    membership = {row["hybas_id"] for row in rows("basin-membership-level10.csv")}
    links = rows("water-body-basin-links.csv")
    assert links
    by_body = defaultdict(set)
    for row in links:
        assert row["method"] == "pour_point_containment"
        by_body[row["water_body_id"]].add(row["basin_level"])
        if row["basin_level"] == "10":
            assert row["hybas_id"] in membership
    assert all("10" in levels for levels in by_body.values())


def test_water_body_manifest_separates_presence_from_operation():
    payload = manifest("water-bodies-transboundary.manifest.json")
    assert payload["observationClass"] == "inventory"
    assert payload["counts"]["reservoirs"] >= 20
    assert any("managed graph" in note for note in payload["qualityNotes"])
