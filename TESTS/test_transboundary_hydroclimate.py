from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "PUBLISHED/data/hydroclimate"


def rows(name: str) -> list[dict]:
    with (DATA / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_all_full_basin_routing_resolves_or_terminates():
    for level in (7, 10, 12):
        routing = rows(f"basin-routing-level{level:02d}.csv")
        assert routing
        assert {row["next_down_scope"] for row in routing} <= {"inside_full_basin", "terminal"}
        assert sum(row["next_down_scope"] == "terminal" for row in routing) == 2


def test_multilevel_hierarchy_has_no_unresolved_children():
    hierarchy = rows("basin-hierarchy.csv")
    assert hierarchy
    assert {row["match_rule"] for row in hierarchy} == {"pfaf_prefix"}
    assert all(row["parent_hybas_id"] for row in hierarchy)


def test_headwater_scope_remains_compatible_with_era5_system_ids():
    document = json.loads((DATA / "headwater-units.geojson").read_text(encoding="utf-8"))
    counts = defaultdict(int)
    for feature in document["features"]:
        props = feature["properties"]
        counts[props["system_id"]] += 1
        assert props["river_system_id"] in {"amu_darya", "syr_darya"}
        assert props["in_headwater_formation"] is True
    assert dict(counts) == {"upper_amu_darya": 86, "upper_syr_darya": 35}


def test_elevation_bands_partition_each_headwater_system():
    grouped = defaultdict(float)
    elevation = rows("headwater-elevation-bands.csv")
    assert len(elevation) == 10
    for row in elevation:
        grouped[row["system_id"]] += float(row["share_percent"])
        assert row["observation_unit_id"] == f"{row['system_id']}::{row['elevation_band']}"
    assert all(abs(total - 100) < 0.001 for total in grouped.values())


def test_temporal_grain_is_preserved_in_download_tables():
    era5 = rows("era5-land-headwater-elevation-monthly.csv")
    snow = rows("modis-snow-headwaters-daily.csv")
    assert len({row["period_start"] for row in era5}) >= 10
    assert len({row["date"] for row in snow}) >= 31
    assert all(row["valid_area_percent"] for row in snow)
    assert all(row["source_image"] for row in era5 + snow)


def test_state_tables_reach_back_to_the_start_of_the_water_year():
    """A water year opens on 1 October, so state must start there, not in January."""
    for name in (
        "era5-land-headwaters-monthly.csv",
        "era5-land-headwater-elevation-monthly.csv",
        "era5-land-headwater-anomaly.csv",
    ):
        months = sorted({row["period_start"] for row in rows(name)})
        assert months[0] == "2025-10-01"
        expected, year, month = [], 2025, 10
        while f"{year:04d}-{month:02d}-01" <= months[-1]:
            expected.append(f"{year:04d}-{month:02d}-01")
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        assert months == expected

    days = sorted({row["date"] for row in rows("modis-snow-headwaters-daily.csv")})
    assert days[0] <= "2025-10-01"
    assert len(days) >= 300


def test_headwater_anomalies_use_a_fixed_climate_normal():
    anomalies = rows("era5-land-headwater-anomaly.csv")
    assert anomalies
    assert {row["baseline_start"] for row in anomalies} == {"1991"}
    assert {row["baseline_end"] for row in anomalies} == {"2020"}
    assert {row["system_id"] for row in anomalies} == {"upper_amu_darya", "upper_syr_darya"}
    assert all(row["z_score"] and row["classification"] for row in anomalies)
