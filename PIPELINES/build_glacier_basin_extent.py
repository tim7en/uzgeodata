"""Publish glacier extent per basin from the project's GLIMS inventory.

The atlas already carries a glacier column, and for this region it is not usable.
Read straight from BasinATLAS_v10.gdb, every level-12 basin in the Pskem window
reports gla_pc_sse = 0 and gla_pc_use = 0. Checked against the inventory built by
PIPELINES/build_glacier_inventory.py over the same basins, the atlas records zero
in 693 basins holding 5,009 km2 of ice - 39 percent of the 12,820 km2 mapped -
including every Pskem and Zeravshan unit. The 2012 snapshot behind the atlas
column appears to lack Western Tien Shan coverage rather than to disagree about
area, which makes it a gap, not a measurement.

This publishes the inventory as a basin column the map can draw, so a reader can
colour the basins by ice that was actually mapped. It does not correct the atlas
value: an archived attribute stays as its publisher released it, and the two sit
side by side with the difference stated.

Two decisions are worth knowing about.

Coverage is not zero. GLIMS was queried over the runoff-formation geometry
(`filterBounds` in the inventory pipeline), so outside that zone nothing was
looked for. A basin there is published as null - not assessed - rather than as
zero, because "no ice was mapped here" and "nobody looked here" are different
statements and only one of them is a measurement.

Coarser levels are aggregated from level 12, where the vector intersection was
computed, through the Pfafstetter prefix that nests the levels. A level-7 or
level-10 basin is published only when every level-12 unit inside it was assessed;
one unassessed child makes the parent's percentage a fraction with an unknown
numerator. That drops 3 basins at level 10 and 8 at level 7.

    python PIPELINES/build_glacier_basin_extent.py
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / "PUBLISHED/data/hydroclimate"
LINKS = PUBLISHED / "glacier-basin-links.csv"
MEMBERSHIP = PUBLISHED / "basin-membership-level12.csv"
MANIFEST = PUBLISHED / "glaciers-headwaters.manifest.json"
SYSTEMS = PUBLISHED / "glacier-headwater-systems.json"
OUTPUT = PUBLISHED / "glacier-basin-extent.json"

BASE_LEVEL = 12
# Pfafstetter ids nest by prefix: the first ten digits of a level-12 id name its
# level-10 parent, the first seven its level-7 parent.
LEVELS = (7, 10, 12)


def basins(level: int) -> list[dict]:
    path = PUBLISHED / f"basins-level{level:02d}.geojson"
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)["features"]


def ice_by_basin() -> dict[int, float]:
    """Mapped ice area per level-12 basin, summed over the glaciers touching it."""
    ice: dict[int, float] = defaultdict(float)
    with LINKS.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if int(row["basin_level"]) == BASE_LEVEL:
                ice[int(row["hybas_id"])] += float(row["area_km2"])
    return dict(ice)


def formation_zone() -> set[int]:
    covered = set()
    with MEMBERSHIP.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if int(row["level"]) == BASE_LEVEL and row["headwater_formation"] == "1":
                covered.add(int(row["hybas_id"]))
    return covered


def main() -> None:
    ice = ice_by_basin()
    formation = formation_zone()
    base = basins(BASE_LEVEL)

    # Assessed means the inventory looked here: inside the formation zone it did by
    # construction, and a glacier mapped just outside it is evidence that it looked
    # there too. Everything else stays null.
    assessed = {}
    area_km2 = {}
    pfaf = {}
    for feature in base:
        properties = feature["properties"]
        hybas = int(properties["HYBAS_ID"])
        pfaf[hybas] = str(properties["PFAF_ID"])
        area_km2[hybas] = float(properties["SUB_AREA"])
        assessed[hybas] = hybas in formation or ice.get(hybas, 0.0) > 0

    levels = {}
    for level in LEVELS:
        digits = level if level != BASE_LEVEL else None
        children: dict[str, list[int]] = defaultdict(list)
        for hybas, code in pfaf.items():
            children[code if digits is None else code[:digits]].append(hybas)

        ids, ice_column, percent_column = [], [], []
        assessed_count = with_ice = withheld = 0
        for feature in basins(level):
            properties = feature["properties"]
            hybas = int(properties["HYBAS_ID"])
            code = str(properties["PFAF_ID"])
            units = children.get(code, [])
            ids.append(hybas)
            # A parent whose children were not all assessed has an ice total that
            # cannot be compared with its own area, so it is withheld rather than
            # published as a number that reads like a measurement.
            if not units or not all(assessed[unit] for unit in units):
                ice_column.append(None)
                percent_column.append(None)
                withheld += 1
                continue
            total = round(sum(ice.get(unit, 0.0) for unit in units), 4)
            extent = float(properties["SUB_AREA"])
            ice_column.append(total)
            percent_column.append(round(total / extent * 100, 3) if extent > 0 else None)
            assessed_count += 1
            with_ice += 1 if total > 0 else 0

        levels[str(level)] = {
            "ids": ids,
            "basins": len(ids),
            "assessed": assessed_count,
            "withIce": with_ice,
            "notAssessed": withheld,
            "iceAreaKm2": round(sum(value for value in ice_column if value), 3),
            "values": {"gla_km2_glims": ice_column, "gla_pc_glims": percent_column},
        }

    with MANIFEST.open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    with SYSTEMS.open(encoding="utf-8") as handle:
        systems = json.load(handle)["systems"]

    payload = {
        "version": "1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "joinKey": "hybas_id",
        "columns": ["gla_km2_glims", "gla_pc_glims"],
        "units": {"gla_km2_glims": "square kilometres", "gla_pc_glims": "percent of basin area"},
        "labels": {
            "gla_km2_glims": "Glacier area, GLIMS inventory",
            "gla_pc_glims": "Glacier extent, GLIMS inventory",
        },
        "source": manifest["source"],
        "selection": manifest["selection"],
        "surveyDates": {
            system["systemId"]: system["surveyDateRange"] for system in systems
        },
        "coverage": {
            "scope": manifest["spatialScope"],
            "note": "GLIMS was queried over the runoff-formation geometry. A basin outside it is "
                    "null, meaning not assessed, never zero.",
            "aggregation": "Levels 7 and 10 are summed from the level-12 intersection through the "
                           "Pfafstetter prefix, and published only where every level-12 unit inside "
                           "them was assessed.",
        },
        "comparison": {
            "note": "Published beside the atlas column gla_pc_sse, which is not corrected here.",
            "atlasZeroBasinsWithMappedIce": sum(1 for hybas, value in ice.items() if value > 0),
        },
        "levels": levels,
    }
    with OUTPUT.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    print(json.dumps({
        "output": str(OUTPUT.relative_to(ROOT)).replace("\\", "/"),
        "bytes": OUTPUT.stat().st_size,
        "levels": {level: {key: entry[key] for key in ("basins", "assessed", "withIce",
                                                       "notAssessed", "iceAreaKm2")}
                   for level, entry in levels.items()},
    }, indent=2))


if __name__ == "__main__":
    main()
