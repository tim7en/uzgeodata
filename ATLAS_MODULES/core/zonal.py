"""Grouped zonal statistics: one pass over the grid, not one pass per basin.

The pilot reduced each basin by masking the whole analysis grid for that basin,
which costs the grid times the basin count. At 20 basins that is invisible. At the
7,445 level-12 basins of the Amu Darya and Syr Darya it is the dominant cost of a
regional run, and it is pure waste: every cell already carries the label of the
basin it falls in, so all basins can be accumulated in a single sweep.

The statistics returned are sufficient statistics. A mean, an area-weighted mean,
a density integral or an upstream accumulation is assembled from them afterwards,
so a basin never has to be re-scanned to answer a second question, and upstream
support is summed from parts rather than re-reduced over a merged mask.

Label 0 is "outside every basin" and is carried through the arrays so that the
label grid can be used as-is; callers index groups from 1.
"""
from __future__ import annotations

import numpy as np


def grouped_statistics(values, labels, areas, groups, extremes=False):
    """Sufficient statistics for every label, in one pass over the grid.

    ``values`` may contain NaN for masked or absent source data. Those cells count
    towards ``expected`` but not ``count``, which is what makes coverage a real
    fraction rather than an assumption that missing data is zero.
    """
    labels = np.asarray(labels).ravel()
    values = np.asarray(values, dtype="float64").ravel()
    areas = np.asarray(areas, dtype="float64").ravel()
    if labels.shape != values.shape or labels.shape != areas.shape:
        raise ValueError("values, labels and areas must describe the same grid")
    size = groups + 1

    finite = np.isfinite(values)
    valid_labels = labels[finite]
    valid_values = values[finite]
    valid_areas = areas[finite]

    statistics = {
        "expected": np.bincount(labels, minlength=size)[:size],
        "count": np.bincount(valid_labels, minlength=size)[:size],
        "sum": np.bincount(valid_labels, weights=valid_values, minlength=size)[:size],
        "area": np.bincount(valid_labels, weights=valid_areas, minlength=size)[:size],
        "weighted": np.bincount(valid_labels, weights=valid_values * valid_areas, minlength=size)[:size],
    }
    if extremes:
        statistics["minimum"], statistics["maximum"] = _extremes(valid_labels, valid_values, size)
    return statistics


def _extremes(labels, values, size):
    """Per-label minimum and maximum, by sorting once instead of masking per label."""
    minimum = np.full(size, np.nan)
    maximum = np.full(size, np.nan)
    if not labels.size:
        return minimum, maximum
    order = np.argsort(labels, kind="stable")
    labels, values = labels[order], values[order]
    starts = np.searchsorted(labels, np.arange(size), side="left")
    ends = np.searchsorted(labels, np.arange(size), side="right")
    present = ends > starts
    # Empty labels contribute no cells, so the spans between the occupied starts
    # are exactly the occupied groups and reduceat can take them in one call.
    minimum[present] = np.minimum.reduceat(values, starts[present])
    maximum[present] = np.maximum.reduceat(values, starts[present])
    return minimum, maximum


def parts_by_id(statistics, ids, extremes=False):
    """Reshape the grouped arrays into the per-basin records the modules pass around."""
    parts = {}
    for index, bid in enumerate(ids, 1):
        record = {"count": int(statistics["count"][index]),
                  "expected": int(statistics["expected"][index]),
                  "sum": float(statistics["sum"][index]),
                  "area": float(statistics["area"][index]),
                  "weighted": float(statistics["weighted"][index])}
        if extremes:
            has_value = statistics["count"][index] > 0
            record["minimum"] = float(statistics["minimum"][index]) if has_value else None
            record["maximum"] = float(statistics["maximum"][index]) if has_value else None
        parts[bid] = record
    return parts
