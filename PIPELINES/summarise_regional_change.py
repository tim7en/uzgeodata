"""Aggregate what the dated series say changed between 2003 and 2022.

python PIPELINES/summarise_regional_change.py

Twenty years of monthly observations for every basin allow a question the atlas
attributes cannot answer at all, because a climatology has no time in it: did the
quantity move, and where?

A trend over twenty years is a description of those twenty years. It is not a climate
signal, and calling it one would be the mistake this report exists to avoid. Two
decades is short against the variability of this region, no significance is claimed
or tested, and a basin's trend rests on however many months actually carried a value.
Snow carries a further problem of its own: the availability of its source is not
stable across the record, so part of any snow trend may be a trend in what the sensor
delivered rather than in the snow. That is why snow is reported separately and marked.

Annual figures follow the atlas convention for each quantity: a total where the
quantity accumulates, a mean where it does not.
"""
from __future__ import annotations
import collections
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import observations
from ATLAS_MODULES.core.runtime import utc_now, write_json

STORE = ROOT / "PUBLISHED/data/atlas/observations"
REPORT = ROOT / "PUBLISHED/data/atlas/regional-change-2003-2022.json"

VARIABLES = {
    "uzgeodata.dated.v1.aet_mm_s": ("actual evapotranspiration", "total", "mm/year", False),
    "uzgeodata.dated.v1.pet_mm_s": ("potential evapotranspiration", "total", "mm/year", False),
    "uzgeodata.dated.v1.pre_mm_s": ("precipitation", "total", "mm/year", False),
    "uzgeodata.dated.v1.run_mm_s": ("runoff", "total", "mm/year", False),
    "uzgeodata.dated.v1.soil_mm_s": ("soil moisture", "mean", "mm", False),
    "uzgeodata.dated.v1.snw_pc_s": ("snow cover", "mean", "percent of days", True),
}
YEARS = (2003, 2022)
MINIMUM_YEARS = 15          # a trend needs most of the record behind it


def annual(store=STORE, years=YEARS):
    """Per basin, variable and year, following each quantity's own convention."""
    totals = collections.defaultdict(lambda: {"sum": 0.0, "months": 0})
    for year in range(years[0], years[1] + 1):
        for row in observations.read_partitions(store / "time_kind=observation" / f"year={year}"):
            if row["attribute_id"] not in VARIABLES or not row["geometry_version"].startswith("reg-"):
                continue
            if row["value"] is None:
                continue
            entry = totals[(row["basin_id"], row["attribute_id"], year)]
            entry["sum"] += row["value"]
            entry["months"] += 1
    out = {}
    for (basin, attribute, year), entry in totals.items():
        if entry["months"] < 12:        # a partial year is not an annual figure
            continue
        kind = VARIABLES[attribute][1]
        out[(basin, attribute, year)] = entry["sum"] if kind == "total" else entry["sum"] / 12.0
    return out


def slope(series):
    """Least squares change per year across whole years."""
    years = [y for y, _ in series]
    values = [v for _, v in series]
    mean_x, mean_y = statistics.mean(years), statistics.mean(values)
    spread = sum((x - mean_x) ** 2 for x in years)
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(years, values)) / spread if spread else 0.0


def build():
    values = annual()
    series = collections.defaultdict(list)
    for (basin, attribute, year), value in values.items():
        series[(basin, attribute)].append((year, value))

    report = {"generated_at": utc_now(), "period": list(YEARS), "variables": {}}
    for attribute, (label, kind, unit, caution) in VARIABLES.items():
        trends, levels = [], []
        for (basin, name), points in series.items():
            if name != attribute or len(points) < MINIMUM_YEARS:
                continue
            points.sort()
            trends.append(slope(points) * 10.0)      # per decade
            levels.append(statistics.mean(v for _, v in points))
        if len(trends) < 100:
            continue
        rising = sum(1 for t in trends if t > 0)
        report["variables"][label] = {
            "attribute_id": attribute, "annual_figure": kind, "unit_per_decade": unit,
            "basins": len(trends),
            "mean_level": statistics.mean(levels),
            "median_change_per_decade": statistics.median(trends),
            "mean_change_per_decade": statistics.mean(trends),
            "share_rising": rising / len(trends),
            "share_falling": 1 - rising / len(trends),
            "change_as_share_of_level": (statistics.median(trends) / statistics.mean(levels)
                                         if statistics.mean(levels) else None),
            "spread_of_change": statistics.pstdev(trends),
            "caution": ("Source availability is not stable across this record, so part of this "
                        "may be a trend in the imagery rather than in the snow.") if caution else None,
        }

    report["limits"] = {
        "length": "Twenty years. Short against this region's variability, and a description of "
                  "the period rather than a climate signal.",
        "significance": "Not tested. No confidence interval, no significance, no attribution.",
        "completeness": "Only basin-years with all twelve months are used, so a basin missing "
                        "months contributes fewer years and needs fifteen to appear at all.",
        "support": "Basin means on a 15 arc-second grid. Basins hold between one and 1,757 "
                   "cells, so the smallest rest on very little.",
    }
    write_json(REPORT, report)
    return report


def main():
    print(json.dumps(build(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
