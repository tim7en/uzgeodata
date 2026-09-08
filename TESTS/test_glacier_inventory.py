from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "PUBLISHED/data/hydroclimate"
SYSTEMS = {"upper_amu_darya", "upper_syr_darya"}


def rows(name: str) -> list[dict]:
    with (DATA / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def manifest() -> dict:
    return json.loads((DATA / "glaciers-headwaters.manifest.json").read_text(encoding="utf-8"))


def test_inventory_holds_one_row_per_glims_glacier():
    inventory = rows("glacier-inventory-headwaters.csv")
    assert inventory
    # A glacier astride the Amu-Syr divide feeds both systems, so the row key is
    # the pair; glacier_id alone repeats for exactly those glaciers.
    keys = [(row["system_id"], row["glacier_id"]) for row in inventory]
    assert len(keys) == len(set(keys))
    shared = len(inventory) - len({row["glacier_id"] for row in inventory})
    assert shared == manifest()["counts"]["glaciersSharedBetweenSystems"]
    assert {row["system_id"] for row in inventory} == SYSTEMS
    assert all(float(row["area_km2"]) > 0 for row in inventory)
    assert all(row["survey_date"] and row["source_asset"].startswith("GLIMS/") for row in inventory)
    assert {row["quality"] for row in inventory} <= {
        "ok-inventory", "elevation-band-from-reported-elevation", "elevation-band-unresolved"
    }


def test_glacier_area_is_the_outline_without_internal_rock():
    for row in rows("glacier-inventory-headwaters.csv"):
        outline = float(row["outline_area_km2"])
        area = float(row["area_km2"])
        rock = float(row["internal_rock_area_km2"])
        assert rock >= 0
        assert abs(outline - area - rock) < 1e-5


def test_elevation_band_areas_sum_to_the_glacier_area():
    configured = {row["elevation_band"] for row in rows("headwater-elevation-bands.csv")}
    banded = defaultdict(float)
    for row in rows("glacier-elevation-bands.csv"):
        assert row["elevation_band"] in configured
        assert float(row["area_km2"]) > 0
        banded[(row["system_id"], row["glacier_id"])] += float(row["area_km2"])
    for row in rows("glacier-inventory-headwaters.csv"):
        key = (row["system_id"], row["glacier_id"])
        assert abs(banded[key] - float(row["area_km2"])) < 1e-4


def test_subbasin_links_stay_inside_the_glacier_and_the_basin_frame():
    membership = {
        level: {row["hybas_id"] for row in rows(f"basin-membership-level{level:02d}.csv")}
        for level in (10, 12)
    }
    linked = defaultdict(float)
    shares = defaultdict(float)
    primary = defaultdict(int)
    for row in rows("glacier-basin-links.csv"):
        level = int(row["basin_level"])
        assert row["hybas_id"] in membership[level]
        assert float(row["area_km2"]) > 0
        assert row["method"] == "vector_intersection"
        key = (row["system_id"], row["glacier_id"], level)
        linked[key] += float(row["area_km2"])
        shares[key] += float(row["share_of_glacier_percent"])
        primary[key] += int(row["is_primary_subbasin"])
    assert linked
    assert set(primary.values()) == {1}
    assert all(total <= 100.01 for total in shares.values())
    inventory = {
        (row["system_id"], row["glacier_id"]): float(row["area_km2"])
        for row in rows("glacier-inventory-headwaters.csv")
    }
    # Cutting a polygon adds boundary segments, and each published area is rounded
    # to six decimals, so the parts sum back to the whole only to within rounding.
    for (system_id, glacier_id, _), total in linked.items():
        area = inventory[(system_id, glacier_id)]
        assert total - area <= max(area * 1e-5, 1e-5)


def test_formation_zone_totals_use_the_clipped_glacier_area():
    inventory = rows("glacier-inventory-headwaters.csv")
    clipped = defaultdict(float)
    for row in inventory:
        inside = float(row["area_in_headwater_km2"])
        area = float(row["area_km2"])
        assert 0 <= inside <= area + max(area * 1e-5, 1e-5)
        clipped[row["system_id"]] += inside

    published = defaultdict(float)
    for row in rows("glacier-headwater-systems.csv"):
        published[row["system_id"]] += float(row["glacier_area_km2"])
    assert set(published) == SYSTEMS
    assert all(abs(published[system] - clipped[system]) < 0.5 for system in SYSTEMS)

    cross_tab = defaultdict(float)
    for row in rows("glacier-basin-elevation-bands.csv"):
        if int(row["basin_level"]) == 10 and row["in_headwater_formation"] == "1":
            cross_tab[row["system_id"]] += float(row["glacier_area_km2"])
    assert all(abs(cross_tab[system] - clipped[system]) < 0.5 for system in SYSTEMS)


def test_glacier_area_never_exceeds_the_band_it_is_reported_in():
    """Ice is placed in the bands the subbasin has, not spread by area share alone."""
    per_basin = defaultdict(float)
    stated = {}
    for row in rows("glacier-basin-elevation-bands.csv"):
        band_area = float(row["basin_band_area_km2"])
        glacier_area = float(row["glacier_area_km2"])
        assert glacier_area >= 0
        assert glacier_area <= band_area
        assert row["observation_unit_id"] == f"{row['hybas_id']}::{row['elevation_band']}"
        key = (row["basin_level"], row["hybas_id"])
        per_basin[key] += glacier_area
        stated[key] = float(row["basin_glacier_area_km2"])
    # The band split redistributes a subbasin's ice, it never invents or loses any.
    assert all(abs(per_basin[key] - stated[key]) < 1e-4 for key in stated)


def test_source_attribution_is_published_for_every_submission():
    attribution = rows("glacier-source-attribution.csv")
    assert attribution
    published = {(row["system_id"], row["glims_submission_id"]) for row in attribution}
    used = {
        (row["system_id"], row["glims_submission_id"])
        for row in rows("glacier-inventory-headwaters.csv")
    }
    assert used <= published


def test_glacier_products_declare_an_inventory_not_a_current_state():
    payload = manifest()
    assert payload["observationClass"] == "inventory"
    assert payload["spatialScope"] == "headwater_formation"
    assert payload["selection"]["deduplication"] == "latest src_date per glac_id"
    assert "intrnl_rock" in payload["selection"]["internalRock"]
    assert "inventory" in payload["semantics"]["temporalStatus"]
    assert {entry["systemId"] for entry in payload["systems"]} == SYSTEMS
    for entry in payload["systems"]:
        assert entry["glacierAreaKm2"] <= entry["intersectingGlacierAreaKm2"]
        assert len(entry["surveyDateRange"]) == 2
