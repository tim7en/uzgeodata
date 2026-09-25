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
numerator.

Two surveys feed the column and each basin records which one it came from. The
headwater inventory covers the runoff-formation zone. The Pskem lies outside that
geometry, so the inventory holds nothing there - not for want of GLIMS coverage,
but because the query never reached it - and the case study's 452 digitised
outlines fill it: 31 basins and 103 km2 of ice that would otherwise read as
unassessed in the headwaters of a river this project has a case study about.

    python PIPELINES/build_glacier_basin_extent.py
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from pyproj import Geod
from shapely.geometry import shape
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / "PUBLISHED/data/hydroclimate"
LINKS = PUBLISHED / "glacier-basin-links.csv"
MEMBERSHIP = PUBLISHED / "basin-membership-level12.csv"
MANIFEST = PUBLISHED / "glaciers-headwaters.manifest.json"
SYSTEMS = PUBLISHED / "glacier-headwater-systems.json"
# The Pskem sits outside the runoff-formation geometry the headwater inventory was
# queried over, so that inventory holds nothing for it -- not because GLIMS lacks
# coverage there, but because the query never reached it. The case study digitised
# the same archive for the same basins: 452 outlines analysed at the Astronomical
# Institute in Tashkent. They are intersected here so the published column covers a
# basin this project has a whole case study about.
PSKEM_OUTLINES = ROOT / "PUBLISHED/data/case-studies/pskem-glims-outlines.geojson"
# The Kashkadarya and Surkhandarya 2023 catalogues are a different kind of evidence
# and get their own columns rather than being poured into the GLIMS ones. They
# deliver a centre point and a reported area per glacier, with no outline, so a
# basin total here is areas attributed to the basin a point falls in - not area
# measured inside that basin. Summing the two kinds into one number would state a
# precision that only one of them has.
REGIONAL_CATALOGUE = PUBLISHED / "regional-glaciers.geojson"
OUTPUT = PUBLISHED / "glacier-basin-extent.json"
GEOD = Geod(ellps="WGS84")

# Which survey put ice in a basin, published per basin because two extractions of
# the same archive over different ground are not one measurement. Codes are built
# as the sources are found, so adding a region does not renumber the others.
BASE_SURVEYS = {"not_assessed": 0, "headwater_inventory": 1}

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


def outline_sources() -> list[tuple[str, Path]]:
    """Every set of glacier outlines published outside the headwater inventory.

    The case study digitised the Pskem; extract_glacier_region_outlines.py fetches
    the windows the inventory's formation geometry excluded. Each is a separate
    survey and keeps its own name in the per-basin provenance.
    """
    found = []
    if PSKEM_OUTLINES.exists():
        found.append(("pskem_case_study", PSKEM_OUTLINES))
    for path in sorted(PUBLISHED.glob("glims-*-outlines.geojson")):
        found.append((f"glims_{path.stem.split('-')[1]}", path))
    return found


def outline_ice(path: Path, tree: STRtree, polygons: list[tuple[int, object]]) -> dict[int, float]:
    """Ice per level-12 basin from one set of outlines.

    Exact vector intersection, geodesic area, the way the headwater inventory does
    it, so every number in the column means the same thing. Each file arrives
    already deduplicated to one outline per glacier with internal rock removed, so
    nothing is subtracted here.
    """
    with path.open(encoding="utf-8") as handle:
        outlines = [shape(feature["geometry"]) for feature in json.load(handle)["features"]]
    ice: dict[int, float] = defaultdict(float)
    for outline in outlines:
        if not outline.is_valid:
            outline = outline.buffer(0)
        for index in tree.query(outline):
            hybas, basin = polygons[int(index)]
            piece = outline.intersection(basin)
            if piece.is_empty:
                continue
            ice[hybas] += abs(GEOD.geometry_area_perimeter(piece)[0]) / 1e6
    return {hybas: round(value, 6) for hybas, value in ice.items()}


def catalogue_ice(base: list[dict]) -> tuple[dict[int, float], dict[int, int], dict]:
    """Reported glacier area per basin from the 2023 point catalogues.

    Each row is one glacier: a catalogue number, an area, a perimeter and a centre
    point. The whole reported area is credited to the basin the point falls in,
    which is the only placement the survey supports. A glacier astride a divide is
    therefore credited to one side of it - stated here rather than smoothed over.
    """
    if not REGIONAL_CATALOGUE.exists():
        return {}, {}, {}
    with REGIONAL_CATALOGUE.open(encoding="utf-8") as handle:
        points = json.load(handle)["features"]
    polygons = [(int(feature["properties"]["HYBAS_ID"]), shape(feature["geometry"]))
                for feature in base]
    tree = STRtree([geometry for _, geometry in polygons])
    ice: dict[int, float] = defaultdict(float)
    counted: dict[int, int] = defaultdict(int)
    placed = 0
    for feature in points:
        point = shape(feature["geometry"])
        area = float(feature["properties"].get("area_km2") or 0)
        for index in tree.query(point):
            hybas, basin = polygons[int(index)]
            if not basin.contains(point):
                continue
            ice[hybas] += area
            counted[hybas] += 1
            placed += 1
            break
    summary = {
        "glaciers": len(points),
        "placedInBasins": placed,
        "outsideBasins": len(points) - placed,
        "basins": len(ice),
        "areaKm2": round(sum(ice.values()), 3),
    }
    return {key: round(value, 6) for key, value in ice.items()}, dict(counted), summary


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

    # Which survey each basin's ice came from, kept per basin: the headwater
    # inventory and the case study are two extractions of the same archive over
    # different ground, and a reader tracing a number is entitled to know which one
    # produced it.
    survey = {int(feature["properties"]["HYBAS_ID"]): "not_assessed" for feature in base}
    for hybas in ice:
        survey[hybas] = "headwater_inventory"

    polygons = [(int(feature["properties"]["HYBAS_ID"]), shape(feature["geometry"]))
                for feature in base]
    tree = STRtree([geometry for _, geometry in polygons])
    survey_codes = dict(BASE_SURVEYS)
    added = {}
    for name, path in outline_sources():
        survey_codes.setdefault(name, len(survey_codes))
        found = outline_ice(path, tree, polygons)
        fresh = 0.0
        for hybas, value in found.items():
            # A later survey only fills ground no earlier one covered. Where two
            # extractions of the same archive overlap a basin, the first stands, or
            # the ice in it would be counted twice.
            if survey.get(hybas) != "not_assessed":
                continue
            ice[hybas] = value
            survey[hybas] = name
            fresh += value
        added[name] = {"basins": sum(1 for h, s in survey.items() if s == name),
                       "iceAreaKm2": round(fresh, 3)}
        print(f"{name}: adds {added[name]['basins']} basin(s), {added[name]['iceAreaKm2']} km2 "
              f"the headwater inventory never reached.")

    catalogue, catalogue_counts, catalogue_summary = catalogue_ice(base)
    if catalogue_summary:
        print(f"2023 catalogues place {catalogue_summary['placedInBasins']} of "
              f"{catalogue_summary['glaciers']} glaciers in {catalogue_summary['basins']} basins, "
              f"{catalogue_summary['areaKm2']} km2 reported.")

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
        assessed[hybas] = (hybas in formation or ice.get(hybas, 0.0) > 0
                           or survey.get(hybas) != "not_assessed")

    levels = {}
    for level in LEVELS:
        digits = level if level != BASE_LEVEL else None
        children: dict[str, list[int]] = defaultdict(list)
        for hybas, code in pfaf.items():
            children[code if digits is None else code[:digits]].append(hybas)

        ids, ice_column, percent_column, survey_column = [], [], [], []
        catalogue_km2, catalogue_pc, catalogue_n = [], [], []
        assessed_count = with_ice = withheld = 0
        for feature in basins(level):
            properties = feature["properties"]
            hybas = int(properties["HYBAS_ID"])
            code = str(properties["PFAF_ID"])
            units = children.get(code, [])
            ids.append(hybas)
            # The catalogues are a survey of their own ground: a basin is covered by
            # them when a catalogued glacier sits in it, and silent otherwise. There
            # is no formation geometry to say where they looked, so this column
            # claims nothing about where they did not.
            reported = round(sum(catalogue.get(unit, 0.0) for unit in units), 6)
            glaciers = sum(catalogue_counts.get(unit, 0) for unit in units)
            catalogue_km2.append(reported if glaciers else None)
            catalogue_n.append(glaciers if glaciers else None)
            catalogue_pc.append(round(reported / float(properties["SUB_AREA"]) * 100, 3)
                                if glaciers and float(properties["SUB_AREA"]) > 0 else None)
            # A parent whose children were not all assessed has an ice total that
            # cannot be compared with its own area, so it is withheld rather than
            # published as a number that reads like a measurement.
            if not units or not all(assessed[unit] for unit in units):
                ice_column.append(None)
                percent_column.append(None)
                survey_column.append(survey_codes["not_assessed"])
                withheld += 1
                continue
            total = round(sum(ice.get(unit, 0.0) for unit in units), 4)
            extent = float(properties["SUB_AREA"])
            ice_column.append(total)
            percent_column.append(round(total / extent * 100, 3) if extent > 0 else None)
            # A parent inherits a survey only when every unit inside it names the
            # same one; mixed provenance is recorded as mixed, not as either.
            named = {survey[unit] for unit in units if survey[unit] != "not_assessed"}
            survey_column.append(survey_codes[named.pop()] if len(named) == 1 else
                                 (survey_codes["not_assessed"] if not named else -1))
            assessed_count += 1
            with_ice += 1 if total > 0 else 0

        levels[str(level)] = {
            "ids": ids,
            "basins": len(ids),
            "assessed": assessed_count,
            "withIce": with_ice,
            "notAssessed": withheld,
            "iceAreaKm2": round(sum(value for value in ice_column if value), 3),
            "values": {"gla_km2_glims": ice_column, "gla_pc_glims": percent_column,
                       "gla_survey_glims": survey_column,
                       "gla_km2_catalogue": catalogue_km2, "gla_pc_catalogue": catalogue_pc,
                       "gla_n_catalogue": catalogue_n},
            "catalogueBasins": sum(1 for value in catalogue_n if value),
        }

    with MANIFEST.open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    with SYSTEMS.open(encoding="utf-8") as handle:
        systems = json.load(handle)["systems"]

    payload = {
        "version": "1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "joinKey": "hybas_id",
        "columns": ["gla_km2_glims", "gla_pc_glims", "gla_km2_catalogue", "gla_pc_catalogue",
                    "gla_n_catalogue"],
        "provenance": {"column": "gla_survey_glims", "codes": survey_codes, "mixed": -1,
                       "added": added},
        "units": {"gla_km2_glims": "square kilometres", "gla_pc_glims": "percent of basin area"},
        "labels": {
            "gla_km2_glims": "Glacier area, GLIMS inventory",
            "gla_pc_glims": "Glacier extent, GLIMS inventory",
            "gla_km2_catalogue": "Glacier area, 2023 regional catalogues",
            "gla_pc_catalogue": "Glacier extent, 2023 regional catalogues",
            "gla_n_catalogue": "Catalogued glaciers in the basin",
        },
        "catalogue": {
            **catalogue_summary,
            "source": "Kashkadarya and Surkhandarya 2023 workbooks",
            "geometry": "centre point per glacier; the reported area is credited to the basin "
                        "containing the point, not measured inside it",
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
