"""Publish the dams and reservoirs that regulate the Amu and Syr systems.

HydroLAKES states that a reservoir exists and how much water it nominally holds.
It does not say who built it, when, how tall the dam is, or what it is operated
for — and for most of Central Asia it does not even carry the name. The Global
Dam Watch database supplies exactly those attributes, and it carries GRAND_ID,
HYRIV_ID, HYLAK_ID and HYBAS_L12 as native fields, so every link this build
records is read from the source rather than computed from geometry.

GDW v1.0 supersedes GRanD v1.3, which it fully embodies and which is being
discontinued; GRAND_ID is retained here as the cross-reference to the older
identifier that HydroLAKES stores in its own Grand_id column.

A barrier is selected when its level-12 basin is one of the two systems'. That
is the same whole-basin rule the rest of the hydroclimate frame uses, so Nurek,
Toktogul, Rogun and Kayrakkum are in scope even though none of them is in
Uzbekistan — they are precisely the structures that decide how much water
arrives.

    python PIPELINES/build_basin_dams.py
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pyogrio

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hydrosheds_sources  # noqa: E402  (path set above)

ROOT = Path(__file__).resolve().parent.parent
PUBLISHED_DIR = ROOT / "PUBLISHED/data/hydroclimate"
BASIN_SOURCE = ROOT / "GEODATA/transboundary_basins_v2"
ROLES = PUBLISHED_DIR / "basin-hydrological-roles.csv"
REACHES = ROOT / "PUBLISHED/data/hydrography/rivers-unified.csv"
WATER_BODIES = PUBLISHED_DIR / "water-bodies-transboundary.csv"

TABLE = PUBLISHED_DIR / "dams-transboundary.csv"
GEOJSON = PUBLISHED_DIR / "dams-transboundary.geojson"
BASIN_LINKS = PUBLISHED_DIR / "dam-basin-links.csv"
REACH_LINKS = PUBLISHED_DIR / "dam-reach-links.csv"
BODY_LINKS = PUBLISHED_DIR / "dam-water-body-links.csv"
MANIFEST = PUBLISHED_DIR / "dams-transboundary.manifest.json"

SOURCE_ID = "globaldamwatch-2026"
SOURCE_ASSET = "Global Dam Watch v1.0"
GDB = "GDW_v1_0/GDW_v1_0.gdb"
BARRIERS = "GDW_barriers_v1_0"

# GDW writes -99 for "not reported" in every numeric column. Reading it as a
# value would make a 1963 dam 168 metres shorter than nothing; it has to become
# an empty cell, not a zero, because zero is a legitimate height and capacity.
NODATA = -99

COLUMNS = [
    "GDW_ID", "DAM_NAME", "RES_NAME", "ALT_NAME", "DAM_TYPE", "RIVER",
    "MAIN_BASIN", "COUNTRY", "ADMIN_UNIT", "NEAR_CITY", "YEAR_DAM", "ALT_YEAR",
    "REM_YEAR", "DAM_HGT_M", "DAM_LEN_M", "AREA_SKM", "CAP_MCM", "DEPTH_M",
    "DIS_AVG_LS", "DOR_PC", "ELEV_MASL", "CATCH_SKM", "POWER_MW", "MAIN_USE",
    "USE_IRRI", "USE_ELEC", "USE_SUPP", "USE_FCON", "USE_RECR", "USE_NAVI",
    "USE_FISH", "USE_PCON", "USE_LIVE", "USE_OTHR", "QUALITY", "LONG_DAM",
    "LAT_DAM", "LONG_RIV", "LAT_RIV", "GRAND_ID", "HYRIV_ID", "HYLAK_ID",
    "HYBAS_L12",
]

TABLE_FIELDS = [
    "dam_id", "grand_id", "dam_name", "reservoir_name", "river", "country",
    "admin_unit", "nearest_city", "dam_type", "year_completed", "year_removed",
    "dam_height_m", "dam_length_m", "reservoir_area_km2", "capacity_mcm",
    "mean_depth_m", "average_discharge_cms", "degree_of_regulation_pc",
    "elevation_masl", "catchment_km2", "power_capacity_mw", "main_use", "uses",
    "record_quality", "longitude", "latitude", "position_source", "system_id",
    "hybas_id_level12", "hybas_id_level10", "in_headwater_formation",
    "hyriv_id", "hylak_id", "reach_scope", "water_body_scope",
    "source_asset", "retrieved_at",
]
BASIN_LINK_FIELDS = [
    "dam_id", "system_id", "basin_level", "hybas_id", "in_headwater_formation",
    "capacity_mcm", "method", "retrieved_at",
]
REACH_LINK_FIELDS = [
    "dam_id", "hyriv_id", "system_id", "reach_scope", "capacity_mcm",
    "degree_of_regulation_pc", "method", "retrieved_at",
]
BODY_LINK_FIELDS = [
    "dam_id", "water_body_id", "system_id", "water_body_scope", "capacity_mcm",
    "method", "retrieved_at",
]

USE_COLUMNS = {
    "USE_IRRI": "irrigation", "USE_ELEC": "hydroelectricity",
    "USE_SUPP": "water supply", "USE_FCON": "flood control",
    "USE_RECR": "recreation", "USE_NAVI": "navigation",
    "USE_FISH": "fisheries", "USE_PCON": "pollution control",
    "USE_LIVE": "livestock", "USE_OTHR": "other",
}


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def write_json(path: Path, payload: object, indent: int | None = None) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=indent,
                  separators=(",", ":") if indent is None else None)
        handle.write("\n")
    os.replace(temporary, path)


def number(value):
    """Return a float, or None where GDW means 'not reported'."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result or result == NODATA:
        return None
    return result


def integer(value):
    result = number(value)
    return None if result is None else int(result)


def decimal(value, places: int) -> str:
    result = number(value)
    return "" if result is None else f"{result:.{places}f}"


def text(value) -> str:
    cleaned = str(value).strip() if value is not None else ""
    return "" if cleaned in {"", "None", "nan", "NULL", "<Null>", str(NODATA)} else cleaned


def read_basin_frame() -> dict[int, dict]:
    """Level-12 basins of the two systems, keyed by HYBAS_ID."""
    path = BASIN_SOURCE / "hydroatlas-level12-full-basins.geojson"
    if not path.exists():
        raise SystemExit(f"Missing {path.relative_to(ROOT)}; run npm run basins:transboundary first")
    frame = {}
    for feature in json.loads(path.read_text(encoding="utf-8"))["features"]:
        props = feature["properties"]
        frame[int(props["HYBAS_ID"])] = {
            "system_id": props["system_id"],
            "in_headwater_formation": bool(props["in_headwater_formation"]),
        }
    return frame


def read_level10() -> dict[int, int]:
    """Level-12 to level-10 lookup, by Pfafstetter membership."""
    path = PUBLISHED_DIR / "basin-hierarchy.csv"
    if not path.exists():
        return {}
    parents = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                child_level = int(row.get("child_level") or row.get("basin_level") or 0)
                parent_level = int(row.get("parent_level") or 0)
            except ValueError:
                continue
            if child_level == 12 and parent_level == 10:
                parents[int(row["child_hybas_id"])] = int(row["parent_hybas_id"])
    return parents


def read_ids(path: Path, column: str) -> set[int]:
    if not path.exists():
        return set()
    with path.open(encoding="utf-8", newline="") as handle:
        return {int(row[column]) for row in csv.DictReader(handle) if row.get(column)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    source = hydrosheds_sources.require(
        GDB,
        hint="Global Dam Watch v1.0 geodatabase; free at https://www.globaldamwatch.org/database.",
        source_id=SOURCE_ID,
    )
    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    basins = read_basin_frame()
    level10 = read_level10()
    reaches = read_ids(REACHES, "HYRIV_ID")
    bodies = read_ids(WATER_BODIES, "water_body_id")
    print(f"Dams | frame: {len(basins):,} level-12 basins, {len(reaches):,} reaches, {len(bodies):,} water bodies")

    frame = pyogrio.read_dataframe(str(source), layer=BARRIERS, columns=COLUMNS)
    print(f"  {len(frame):,} barriers in {SOURCE_ASSET}")

    rows, features, basin_links, reach_links, body_links = [], [], [], [], []
    for record in frame.itertuples(index=False):
        basin_id = integer(record.HYBAS_L12)
        placed = basins.get(basin_id) if basin_id else None
        if placed is None:
            continue

        dam_id = int(record.GDW_ID)
        capacity = decimal(record.CAP_MCM, 2)
        regulation = decimal(record.DOR_PC, 2)
        parent10 = level10.get(basin_id)
        uses = [label for column, label in USE_COLUMNS.items()
                if text(getattr(record, column)).lower() in {"main", "sec", "yes", "1"}]

        reach_id = integer(record.HYRIV_ID)
        reach_scope = ("outside_selection" if reach_id and reach_id not in reaches
                       else "in_selection" if reach_id else "not_reported")
        body_id = integer(record.HYLAK_ID)
        body_scope = ("outside_selection" if body_id and body_id not in bodies
                      else "in_selection" if body_id else "not_reported")

        # GDW carries two positions: the reported dam location and the one snapped
        # onto the river network. For the large Central Asian dams - Toktogul,
        # Nurek, Rogun, Charvak - the reported pair is empty and only the snapped
        # pair is populated, so preferring one and giving up loses exactly the
        # reservoirs that matter. Which of the two was used is recorded per row.
        longitude, latitude = number(record.LONG_DAM), number(record.LAT_DAM)
        position_source = "reported dam location"
        if longitude is None or latitude is None:
            longitude, latitude = number(record.LONG_RIV), number(record.LAT_RIV)
            position_source = "snapped to the river network" if longitude is not None else ""
        rows.append({
            "dam_id": dam_id,
            "grand_id": integer(record.GRAND_ID) or "",
            "dam_name": text(record.DAM_NAME),
            "reservoir_name": text(record.RES_NAME),
            "river": text(record.RIVER),
            "country": text(record.COUNTRY),
            "admin_unit": text(record.ADMIN_UNIT),
            "nearest_city": text(record.NEAR_CITY),
            "dam_type": text(record.DAM_TYPE),
            "year_completed": integer(record.YEAR_DAM) or "",
            "year_removed": integer(record.REM_YEAR) or "",
            "dam_height_m": decimal(record.DAM_HGT_M, 0),
            "dam_length_m": decimal(record.DAM_LEN_M, 0),
            "reservoir_area_km2": decimal(record.AREA_SKM, 4),
            "capacity_mcm": capacity,
            "mean_depth_m": decimal(record.DEPTH_M, 2),
            "average_discharge_cms": ("" if number(record.DIS_AVG_LS) is None
                                      else f"{number(record.DIS_AVG_LS) / 1000.0:.4f}"),
            "degree_of_regulation_pc": regulation,
            "elevation_masl": decimal(record.ELEV_MASL, 0),
            "catchment_km2": decimal(record.CATCH_SKM, 0),
            "power_capacity_mw": decimal(record.POWER_MW, 2),
            "main_use": text(record.MAIN_USE),
            "uses": ";".join(uses),
            "record_quality": text(record.QUALITY),
            "longitude": "" if longitude is None else f"{longitude:.5f}",
            "latitude": "" if latitude is None else f"{latitude:.5f}",
            "position_source": position_source,
            "system_id": placed["system_id"],
            "hybas_id_level12": basin_id,
            "hybas_id_level10": parent10 or "",
            "in_headwater_formation": int(placed["in_headwater_formation"]),
            "hyriv_id": reach_id or "",
            "hylak_id": body_id or "",
            "reach_scope": reach_scope,
            "water_body_scope": body_scope,
            "source_asset": SOURCE_ASSET,
            "retrieved_at": retrieved,
        })

        for level, hybas in ((12, basin_id), (10, parent10)):
            if not hybas:
                continue
            basin_links.append({
                "dam_id": dam_id, "system_id": placed["system_id"],
                "basin_level": level, "hybas_id": hybas,
                "in_headwater_formation": int(placed["in_headwater_formation"]),
                "capacity_mcm": capacity, "method": "native GDW HYBAS_L12",
                "retrieved_at": retrieved,
            })
        if reach_id:
            reach_links.append({
                "dam_id": dam_id, "hyriv_id": reach_id,
                "system_id": placed["system_id"], "reach_scope": reach_scope,
                "capacity_mcm": capacity, "degree_of_regulation_pc": regulation,
                "method": "native GDW HYRIV_ID", "retrieved_at": retrieved,
            })
        if body_id:
            body_links.append({
                "dam_id": dam_id, "water_body_id": body_id,
                "system_id": placed["system_id"], "water_body_scope": body_scope,
                "capacity_mcm": capacity, "method": "native GDW HYLAK_ID",
                "retrieved_at": retrieved,
            })

        if longitude is not None and latitude is not None:
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(longitude, 5), round(latitude, 5)]},
                "properties": {key: rows[-1][key] for key in (
                    "dam_id", "grand_id", "dam_name", "reservoir_name", "river",
                    "country", "year_completed", "dam_height_m", "capacity_mcm",
                    "power_capacity_mw", "main_use", "uses", "system_id",
                    "hybas_id_level12", "in_headwater_formation", "hyriv_id",
                    "hylak_id", "position_source")},
            })

    rows.sort(key=lambda row: -(float(row["capacity_mcm"] or 0)))
    write_csv(TABLE, TABLE_FIELDS, rows)
    write_csv(BASIN_LINKS, BASIN_LINK_FIELDS, basin_links)
    write_csv(REACH_LINKS, REACH_LINK_FIELDS, reach_links)
    write_csv(BODY_LINKS, BODY_LINK_FIELDS, body_links)
    write_json(GEOJSON, {"type": "FeatureCollection", "features": features})

    storage = sum(float(row["capacity_mcm"] or 0) for row in rows)
    named = sum(1 for row in rows if row["dam_name"] or row["reservoir_name"])
    # Every barrier in this region leaves POWER_MW unreported. Summing empties to
    # zero would publish "0 MW installed" for a basin that runs on hydropower, so
    # the total is null unless at least one dam actually states a figure.
    reporting_power = [float(row["power_capacity_mw"]) for row in rows if row["power_capacity_mw"]]
    powered = round(sum(reporting_power), 1) if reporting_power else None
    manifest = {
        "version": "1.0",
        "generatedAt": retrieved,
        "observationClass": "inventory",
        "spatialScope": "full_basin",
        "source": {
            "asset": SOURCE_ASSET,
            "container": str(source.relative_to(ROOT)).replace("\\", "/"),
            "selection": "native HYBAS_L12 inside a level-12 unit of the Amu or Syr system",
            "license": "CC-BY-4.0",
        },
        "counts": {
            "dams": len(rows),
            "named": named,
            "withGrandId": sum(1 for row in rows if row["grand_id"]),
            "basinLinks": len(basin_links),
            "reachLinks": len(reach_links),
            "reachLinksInSelection": sum(1 for row in reach_links if row["reach_scope"] == "in_selection"),
            "waterBodyLinks": len(body_links),
            "waterBodyLinksInSelection": sum(1 for row in body_links if row["water_body_scope"] == "in_selection"),
            "inHeadwaterFormation": sum(1 for row in rows if row["in_headwater_formation"] == 1),
            "mapped": len(features),
            "positionSnappedToRiver": sum(1 for row in rows
                                          if row["position_source"] == "snapped to the river network"),
        },
        "storageCapacityMcm": round(storage, 1),
        "installedPowerMw": powered,
        "damsReportingPower": len(reporting_power),
        "byCountry": {
            country: sum(1 for row in rows if row["country"] == country)
            for country in sorted({row["country"] for row in rows if row["country"]})
        },
        "largestDams": [
            {
                "id": int(row["dam_id"]),
                "name": row["dam_name"] or row["reservoir_name"] or None,
                "country": row["country"] or None,
                "year": int(row["year_completed"]) if row["year_completed"] else None,
                "capacityMcm": float(row["capacity_mcm"]) if row["capacity_mcm"] else None,
                "heightM": float(row["dam_height_m"]) if row["dam_height_m"] else None,
                "mainUse": row["main_use"] or None,
                "system": row["system_id"],
                "inFormationZone": row["in_headwater_formation"] == 1,
            }
            for row in rows[:15]
        ],
        "outputs": {
            "csv": str(TABLE.relative_to(ROOT)).replace("\\", "/"),
            "geojson": str(GEOJSON.relative_to(ROOT)).replace("\\", "/"),
            "basinLinkCSV": str(BASIN_LINKS.relative_to(ROOT)).replace("\\", "/"),
            "reachLinkCSV": str(REACH_LINKS.relative_to(ROOT)).replace("\\", "/"),
            "waterBodyLinkCSV": str(BODY_LINKS.relative_to(ROOT)).replace("\\", "/"),
        },
        "qualityNotes": [
            "GDW records -99 for an unreported number. Those become empty cells here, "
            "never zero, because zero height and zero capacity are both legitimate values. "
            "Installed power is unreported for every barrier in this region, so "
            "installedPowerMw is null rather than the 0 MW a naive sum would publish for "
            "a basin that runs on hydropower.",
            "capacity_mcm is nominal storage as designed or reported, not an operating "
            "level. This layer says a structure exists and how much it can hold; it never "
            "says how full it is on a given day.",
            "A dam is placed by the level-12 basin GDW itself assigns, so the placement is "
            "read from the source rather than recomputed. Where GDW's HYRIV_ID or HYLAK_ID "
            "falls outside this project's published selection the row is kept and the scope "
            "column records it, rather than dropping the link.",
            "GDW v1.0 supersedes GRanD v1.3 and GRanD is being discontinued. grand_id is "
            "kept as the cross-reference to HydroLAKES, whose Grand_id column still carries "
            "the older identifier.",
            "Most of the large dams here, Toktogul and Nurek among them, have no reported "
            "dam coordinate in GDW and are placed by its river-snapped position instead. "
            "position_source says which of the two was used for every row, because a "
            "snapped point sits on the river centreline rather than on the structure.",
        ],
    }
    write_json(MANIFEST, manifest, indent=1)

    power = f"{powered:,.0f} MW" if powered is not None else "power not reported"
    print(f"  {len(rows):,} dams | {named:,} named | {storage:,.0f} MCM storage | {power}")
    print(f"  links: {len(basin_links):,} basin, {len(reach_links):,} reach, {len(body_links):,} water body")
    print(f"  mapped: {len(features):,} of {len(rows):,} placed "
          f"({manifest['counts']['positionSnappedToRiver']:,} snapped to the river network)")
    for entry in manifest["largestDams"][:6]:
        print(f"    {str(entry['name'] or '(unnamed)')[:22]:22} {str(entry['country'])[:12]:12} "
              f"{entry['year'] or '----'} {entry['capacityMcm'] or 0:>9,.0f} MCM  {entry['mainUse'] or ''}")
    print(f"  wrote {TABLE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
