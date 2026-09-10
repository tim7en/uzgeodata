"""The grouped kernel must answer exactly what the per-basin scan answered.

The scan it replaces is kept here as the oracle: it is obviously correct and
obviously too slow, which is the only reason it was replaced.
"""
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core.zonal import grouped_statistics, parts_by_id


def scan(values, zones, areas, ids, extremes=False):
    """The original implementation: one full-grid mask per basin."""
    parts = {}
    for index, bid in enumerate(ids, 1):
        mask = zones == index
        valid = mask & np.isfinite(values)
        record = {"count": int(valid.sum()), "expected": int(mask.sum()),
                  "sum": float(values[valid].sum()), "area": float(areas[valid].sum()),
                  "weighted": float((values[valid] * areas[valid]).sum())}
        if extremes:
            record["minimum"] = float(values[valid].min()) if valid.any() else None
            record["maximum"] = float(values[valid].max()) if valid.any() else None
        parts[bid] = record
    return parts


def grid(basins=40, shape=(120, 150), seed=0, holes=True):
    rng = np.random.default_rng(seed)
    zones = rng.integers(0, basins + 1, size=shape).astype("int32")
    values = rng.normal(50, 20, size=shape)
    if holes:  # masked source cells, which must count as expected but never as valid
        values[rng.random(shape) < 0.2] = np.nan
    areas = rng.uniform(0.5, 1.5, size=shape) * 1e6
    return values, zones, areas, [str(4120000000 + i) for i in range(basins)]


def compare(values, zones, areas, ids, extremes=False):
    expected = scan(values, zones, areas, ids, extremes)
    actual = parts_by_id(grouped_statistics(values, zones, areas, len(ids), extremes=extremes),
                         ids, extremes=extremes)
    assert set(actual) == set(expected)
    for bid in ids:
        for field, value in expected[bid].items():
            got = actual[bid][field]
            if value is None or got is None:
                assert got == value, f"{bid}.{field}"
            elif field in ("count", "expected"):
                assert got == value, f"{bid}.{field}"
            else:
                assert got == pytest.approx(value, rel=1e-12, abs=1e-9), f"{bid}.{field}"
    return actual


def test_the_grouped_kernel_matches_the_scan_it_replaced():
    compare(*grid(), extremes=True)


def test_it_matches_across_grid_and_basin_shapes():
    for basins, shape, seed in ((1, (30, 40), 1), (7, (11, 13), 2), (500, (200, 200), 3)):
        compare(*grid(basins=basins, shape=shape, seed=seed), extremes=True)


def test_a_basin_with_no_cells_reports_nothing_rather_than_zero():
    values, zones, areas, ids = grid(basins=6, seed=4)
    zones[zones == 3] = 0  # basin 3 keeps no cell centres at this resolution
    parts = compare(values, zones, areas, ids, extremes=True)
    absent = parts[ids[2]]
    assert absent["expected"] == 0 and absent["count"] == 0
    assert absent["minimum"] is None and absent["maximum"] is None
    assert absent["sum"] == 0.0, "an empty sum is not a measurement; coverage is what reports it"


def test_masked_source_data_lowers_coverage_and_never_becomes_zero():
    values, zones, areas, ids = grid(basins=5, seed=5, holes=False)
    values[zones == 2] = np.nan  # the source covers this basin with nodata
    parts = compare(values, zones, areas, ids, extremes=True)
    blanked = parts[ids[1]]
    assert blanked["expected"] > 0, "the cells exist"
    assert blanked["count"] == 0, "but none of them carry a value"
    assert blanked["minimum"] is None


def test_infinities_are_excluded_like_the_scan_excluded_them():
    values, zones, areas, ids = grid(basins=4, seed=6, holes=False)
    values[0, 0] = np.inf
    values[0, 1] = -np.inf
    compare(values, zones, areas, ids, extremes=True)


def test_the_grid_must_agree_with_its_labels():
    values, zones, areas, ids = grid(basins=3, seed=7)
    with pytest.raises(ValueError, match="same grid"):
        grouped_statistics(values[:, :-1], zones, areas, len(ids))


def test_every_cell_is_accounted_for_once_whatever_the_basin_count():
    """The point of the change: cost follows the grid, not grid times basins, and
    the accounting is identical at either end of that range."""
    shape = (300, 300)
    for basins in (10, 2000):
        values, zones, areas, ids = grid(basins=basins, shape=shape, seed=8, holes=False)
        statistics = grouped_statistics(values, zones, areas, len(ids))
        assert int(statistics["expected"].sum()) == shape[0] * shape[1]
        assert int(statistics["count"][1:].sum()) == int((zones > 0).sum())
        assert statistics["expected"].shape == (basins + 1,), "one slot per basin, plus outside"
