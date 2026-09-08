from __future__ import annotations

import pytest

from PIPELINES.build_headwater_pilot import trace_upstream
from PIPELINES.update_headwater_era5 import aggregate_systems, merge_rows, month_tuple, months


def test_trace_upstream_follows_routing_not_geographic_intersection():
    rows = [
        {"HYBAS_ID": 1, "NEXT_DOWN": 3},
        {"HYBAS_ID": 2, "NEXT_DOWN": 3},
        {"HYBAS_ID": 3, "NEXT_DOWN": 4},
        {"HYBAS_ID": 4, "NEXT_DOWN": 0},
        {"HYBAS_ID": 5, "NEXT_DOWN": 4},
    ]
    assert trace_upstream(rows, 3) == [1, 2, 3]


def test_trace_upstream_rejects_cycles():
    rows = [
        {"HYBAS_ID": 1, "NEXT_DOWN": 2},
        {"HYBAS_ID": 2, "NEXT_DOWN": 1},
        {"HYBAS_ID": 3, "NEXT_DOWN": 0},
    ]
    with pytest.raises(ValueError, match="Cycle"):
        trace_upstream(rows, 3)


def test_month_range_is_inclusive_across_year_boundary():
    assert list(months(month_tuple("2025-11"), month_tuple("2026-02"))) == [
        (2025, 11), (2025, 12), (2026, 1), (2026, 2)
    ]


def test_merge_rows_replaces_the_same_basin_period_variable():
    base = {
        "system_id": "upper", "basin_id": "1", "year": "2026", "month": "1",
        "variable": "snow", "value": "2",
    }
    fresh = {**base, "value": "3"}
    assert merge_rows([base], [fresh]) == [fresh]


def test_system_aggregate_is_weighted_by_subbasin_area():
    common = {
        "system_id": "upper", "year": "2026", "month": "1",
        "period_start": "2026-01-01", "variable": "snow", "unit": "mm",
        "retrieved_at": "2026-02-01T00:00:00+00:00",
    }
    result = aggregate_systems(
        [{**common, "basin_id": "1", "value": "10"},
         {**common, "basin_id": "2", "value": "20"}],
        {1: 1.0, 2: 3.0},
    )
    assert len(result) == 1
    assert result[0]["value"] == "17.50000"
    assert result[0]["basin_count"] == 2
