"""Compact glacier facts per level-12 basin, for basin reports.

python PIPELINES/build_glacier_basin_context.py

A report on a basin needs to say how much ice drains into it, how exposed that ice
is, and how old the survey is. The published extent file answers the first for
every basin; the GLIMS inventory, glacier by glacier, answers the rest. This joins
them into one small file keyed by level-12 basin:

  ice_km2          ice area in the basin (the extent file, which includes the Pskem,
                   Angren and Hissar additions), null where the basin was not assessed
  glaciers         number of inventoried glaciers whose outline lies mostly here
  below_4000_km2   ice whose mean elevation is below 4,000 m - the ice that thins and
                   disappears first as the freezing level rises
  small_km2        ice in glaciers under 0.5 km², which respond fastest
  survey           [first, last] survey year of the inventoried outlines

Nothing here is a change over time: GLIMS holds one outline per glacier, surveyed
between 1994 and 2009 in this region. Change needs a second, independent survey,
which is planned rather than inferred.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "PUBLISHED/data/hydroclimate"
OUT = ROOT / "PUBLISHED/data/atlas/glacier-basin-context.json"


def build():
    extent = json.loads((SOURCE / "glacier-basin-extent.json").read_text(encoding="utf-8"))
    level = extent["levels"]["12"]
    area = dict(zip((str(i) for i in level["ids"]), level["values"]["gla_km2_glims"]))
    stats = defaultdict(lambda: {"glaciers": 0, "below": 0.0, "small": 0.0, "first": None, "last": None})
    with (SOURCE / "glacier-inventory-headwaters.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            basin = row["hybas_id_level12"]
            size = float(row["area_km2"])
            entry = stats[basin]
            entry["glaciers"] += 1
            if row["elevation_mean_m"] and float(row["elevation_mean_m"]) < 4000:
                entry["below"] += size
            if size < 0.5:
                entry["small"] += size
            year = int(row["survey_date"][:4]) if row["survey_date"] else None
            if year:
                entry["first"] = min(entry["first"] or year, year)
                entry["last"] = max(entry["last"] or year, year)
    basins = {}
    for basin, ice in area.items():
        if ice is None:
            continue
        entry = stats.get(basin)
        basins[basin] = [round(ice, 4), entry["glaciers"] if entry else None,
                         round(entry["below"], 4) if entry else None, round(entry["small"], 4) if entry else None,
                         [entry["first"], entry["last"]] if entry and entry["first"] else None]
    payload = {
        "version": "1.0", "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fields": ["ice_km2", "glaciers", "below_4000_km2", "small_km2", "survey"],
        "source": "glacier-basin-extent.json (ice area) and glacier-inventory-headwaters.csv (GLIMS outlines)",
        "note": "A basin absent from this file was not assessed: absence is not zero ice. Values are one survey, "
                "not a change over time.",
        "basins": basins,
    }
    OUT.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
    return {"basins": len(basins), "with_ice": sum(1 for v in basins.values() if v[0] > 0),
            "ice_km2": round(sum(v[0] for v in basins.values()), 1), "bytes": OUT.stat().st_size}


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
