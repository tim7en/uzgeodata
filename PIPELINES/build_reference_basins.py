"""Publish level-12 reference basins with the full BasinATLAS attribute set.

Level 12 is the reference frame: the unit an observation is attached to, the unit
a trace walks, and the unit that carries the 281 thematic BasinATLAS attributes
that exist outside Earth Engine's own imagery. Everything else joins to it.

The attributes are read from `WWF/HydroATLAS/v1/Basins/level12`, which ships the
same 281 columns as the BasinATLAS distribution. The local BasinATLAS geodatabase
cannot supply them: in this copy levels 10, 11 and 12 read as empty while levels
1 to 9 read normally, so the download is truncated.

Two groupings matter to a reader and are kept apart everywhere:

* `basin_specific` — the value measured inside this sub-basin alone;
* `basin_accumulation` — the value over the whole upstream catchment, or taken
  at the pour point, which already accounts for everything above.

Summing an accumulation column over several basins counts the same water twice,
which is why the split is a property of the data and not a display preference.

    python PIPELINES/build_reference_basins.py
    python PIPELINES/build_reference_basins.py --refresh-attributes
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from shapely.geometry import mapping, shape

ROOT = Path(__file__).resolve().parent.parent
PUBLISHED_DIR = ROOT / "PUBLISHED/data/hydroclimate"
FRAME = PUBLISHED_DIR / "basins-level12.geojson"
ROLES = PUBLISHED_DIR / "basin-hydrological-roles.csv"
DICTIONARY = ROOT / "PUBLISHED/data/hydrography/attribute-dictionary.json"
CACHE_DIR = ROOT / "WORKSPACE/reference_basin_cache"
LADDER = PUBLISHED_DIR / "reference-basin-levels.json"
TABLE = PUBLISHED_DIR / "reference-basin-attributes.csv"
COLUMNS_JSON = PUBLISHED_DIR / "reference-basin-attributes.json"
GROUPS = PUBLISHED_DIR / "reference-attribute-groups.json"
MANIFEST = PUBLISHED_DIR / "reference-basins.manifest.json"
ASSET = "WWF/HydroATLAS/v1/Basins/level{level:02d}"
# Zoom ladder. A whole-region view does not need 7,445 polygons, and level 7 at
# 2 km simplification is a twentieth of the weight; the finer levels load only
# once the reader has zoomed into them.
DISPLAY_LEVELS = [
    {"level": 7, "minZoom": 0, "simplify": 0.02},
    {"level": 10, "minZoom": 7, "simplify": 0.01},
    {"level": 12, "minZoom": 9, "simplify": 0.006},
]
PROJECT = "ee-sabitovty"
LEVEL = 12
DOWNLOAD_TIMEOUT = 1800
# BasinATLAS spatial-extent codes, from the catalogue shipped with the data.
EXTENT_GROUPS = {
    "s": "basin_specific",
    "u": "basin_accumulation",
    "p": "basin_accumulation",
}
GROUP_LABELS = {
    "basin_specific": "Measured in this sub-basin",
    "basin_accumulation": "Accumulated over the upstream catchment",
}


def write_json(path: Path, payload: object, *, compact: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False,
                  separators=(",", ":") if compact else None, indent=None if compact else 2)
        handle.write("\n")
    os.replace(temporary, path)


def read_roles(level: int = LEVEL) -> dict[int, dict]:
    if not ROLES.exists():
        return {}
    with ROLES.open(encoding="utf-8", newline="") as handle:
        return {
            int(row["hybas_id"]): row
            for row in csv.DictReader(handle)
            if int(row["basin_level"]) == level
        }


def attribute_cache(level: int) -> Path:
    return CACHE_DIR / f"level{level:02d}-attributes.csv"


def download_attributes(columns: list[str], main_basins: list[int], level: int) -> list[dict]:
    """One table download per level; the CSV route has no 5000-element ceiling.

    Every HydroATLAS level ships the same 281 columns, so a coarser level is read
    from the asset rather than aggregated from level 12. Deriving it would mean
    choosing a rule per column; reading it keeps the published value authoritative.
    """
    import ee
    import requests

    ee.Initialize(project=PROJECT)
    selectors = ["HYBAS_ID", *columns]
    collection = (ee.FeatureCollection(ASSET.format(level=level))
                  .filter(ee.Filter.inList("MAIN_BAS", main_basins)))
    url = collection.getDownloadURL(filetype="CSV", selectors=selectors)
    response = requests.get(url, timeout=DOWNLOAD_TIMEOUT)
    response.raise_for_status()
    path = attribute_cache(level)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def attribute_url(level: int) -> str:
    return ("/data/hydroclimate/reference-basin-attributes.json" if level == LEVEL
            else f"/data/hydroclimate/reference-basin-attributes-level{level:02d}.json")


def load_attributes(level: int, columns: list[str], frame: list[dict], refresh: bool) -> dict[int, dict]:
    path = attribute_cache(level)
    if path.exists() and not refresh:
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        print(f"    reuse {path.relative_to(ROOT)} ({len(rows):,} rows)")
    else:
        main_basins = sorted({int(feature["properties"]["MAIN_BAS"]) for feature in frame})
        rows = download_attributes(columns, main_basins, level)
        print(f"    downloaded {len(rows):,} level-{level} rows")
    return {int(float(row["HYBAS_ID"])): row for row in rows if row.get("HYBAS_ID")}


def columnar(measured: dict[int, dict], ids: list[int], order: list[str]) -> dict:
    values = {column: [] for column in order}
    for hybas_id in ids:
        row = measured.get(hybas_id, {})
        for column in order:
            values[column].append(number(row.get(column)))
    return values


def number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result:
        return None
    return int(result) if result == int(result) and abs(result) < 1e15 else round(result, 4)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-attributes", action="store_true")
    args = parser.parse_args()

    dictionary = json.loads(DICTIONARY.read_text(encoding="utf-8"))
    columns = dictionary["columns"]
    frame = json.loads(FRAME.read_text(encoding="utf-8"))["features"]
    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    wanted = {int(feature["properties"]["HYBAS_ID"]) for feature in frame}
    print(f"Reference basins | level {LEVEL} | {len(wanted):,} units | {len(columns)} attributes")

    measured = load_attributes(LEVEL, sorted(columns), frame, args.refresh_attributes)
    missing = sorted(wanted - set(measured))
    if missing:
        raise SystemExit(f"{len(missing)} frame units have no attribute row, first {missing[:5]}")

    ordered = sorted(wanted)
    order = sorted(columns)
    values: dict[str, list] = {column: [] for column in order}
    table_rows: list[dict] = []
    for hybas_id in ordered:
        row = measured[hybas_id]
        record = {"hybas_id": hybas_id}
        for column in order:
            value = number(row.get(column))
            values[column].append(value)
            record[column] = "" if value is None else value
        table_rows.append(record)

    temporary = TABLE.with_suffix(TABLE.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["hybas_id", *order])
        writer.writeheader()
        writer.writerows(table_rows)
    os.replace(temporary, TABLE)

    grouped: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for column in order:
        meta = columns[column]
        group = EXTENT_GROUPS.get(meta["spatialExtent"], "basin_specific")
        grouped[group][meta["category"]].append({
            "column": column,
            "label": meta["label"],
            "units": meta.get("units"),
            "property": meta.get("property"),
            "spatialExtent": meta["spatialExtent"],
            "spatialExtentLabel": meta["spatialExtentLabel"],
            "aggregation": meta.get("aggregation"),
        })
    write_json(GROUPS, {
        "version": "1.0",
        "generatedAt": retrieved,
        "basinLevel": LEVEL,
        "source": dictionary.get("catalogSource"),
        "groups": [
            {
                "id": group,
                "label": GROUP_LABELS[group],
                "attributeCount": sum(len(items) for items in categories.values()),
                "categories": [
                    {"id": category, "attributes": sorted(items, key=lambda item: item["column"])}
                    for category, items in sorted(categories.items())
                ],
            }
            for group, categories in sorted(grouped.items())
        ],
        "note": ("basin_accumulation columns already describe everything upstream; summing them "
                 "across basins counts the same water twice."),
    }, compact=False)

    published_levels = []
    systems = defaultdict(int)
    for entry in DISPLAY_LEVELS:
        level = entry["level"]
        source = PUBLISHED_DIR / f"basins-level{level:02d}.geojson"
        units = json.loads(source.read_text(encoding="utf-8"))["features"]
        level_roles = read_roles(level)
        features = []
        for feature in units:
            props = feature["properties"]
            hybas_id = int(props["HYBAS_ID"])
            role = level_roles.get(hybas_id, {})
            geometry = shape(feature["geometry"])
            features.append({
                "type": "Feature",
                "properties": {
                    "hybas_id": hybas_id,
                    "pfaf_id": int(props["PFAF_ID"]),
                    "basin_level": level,
                    "system_id": props["system_id"],
                    "headwater_system_id": props["headwater_system_id"],
                    "next_down": int(props.get("NEXT_DOWN") or 0),
                    "area_km2": round(float(props["SUB_AREA"]), 2),
                    "upstream_km2": round(float(props["UP_AREA"]), 2),
                    "in_headwater_formation": int(bool(props["in_headwater_formation"])),
                    "flow_position": role.get("flow_position", ""),
                    "channel_class": role.get("channel_class", ""),
                },
                "geometry": mapping(geometry.simplify(entry["simplify"], preserve_topology=True)),
            })
        features.sort(key=lambda item: item["properties"]["hybas_id"])
        path = PUBLISHED_DIR / f"reference-basins-level{level:02d}.geojson"
        write_json(path, {
            "type": "FeatureCollection",
            "name": f"amu_syr_reference_basins_level{level:02d}",
            "features": features,
        })

        # Every level carries the full attribute set, so a choropleth works at any
        # zoom instead of only where the finest polygons are drawn.
        level_ids = [feature["properties"]["hybas_id"] for feature in features]
        level_values = (values if level == LEVEL
                        else columnar(load_attributes(level, order, units, args.refresh_attributes),
                                      level_ids, order))
        attributes_path = PUBLISHED_DIR / attribute_url(level).split("/")[-1]
        write_json(attributes_path, {
            "version": "1.0",
            "generatedAt": retrieved,
            "basinLevel": level,
            "joinKey": "hybas_id",
            "ids": level_ids,
            "columns": order,
            "values": level_values,
        })

        published_levels.append({
            "attributesUrl": attribute_url(level),
            "attributesBytes": attributes_path.stat().st_size,
            "level": level,
            "minZoom": entry["minZoom"],
            "simplifyDegrees": entry["simplify"],
            "units": len(features),
            "url": f"/data/hydroclimate/reference-basins-level{level:02d}.geojson",
            "sizeBytes": path.stat().st_size,
            "carriesAtlasAttributes": level == LEVEL,
        })
        if level == LEVEL:
            for feature in features:
                systems[feature["properties"]["system_id"]] += 1
        print(f"    level {level:>2}: {len(features):>5,} units  {path.stat().st_size / 1e6:>5.1f} MB geometry  "
              f"{attributes_path.stat().st_size / 1e6:>5.1f} MB attributes  from zoom {entry['minZoom']}")

    write_json(LADDER, {
        "version": "1.0",
        "generatedAt": retrieved,
        "attributeLevel": LEVEL,
        "levels": published_levels,
        "note": ("Coarser basins carry the same identity and routing fields; only level 12 carries "
                 "the BasinATLAS attributes, so a reader drilling into detail is drilling towards them."),
    }, compact=False)

    systems = defaultdict(int)
    for feature in features:
        systems[feature["properties"]["system_id"]] += 1
    manifest = {
        "version": "1.0",
        "displayLevels": published_levels,
        "generatedAt": retrieved,
        "observationClass": "reference",
        "basinLevel": LEVEL,
        "role": "reference frame every observation and trace joins to",
        "source": {
            "attributes": ASSET,
            "attributeCount": len(order),
            "catalogSource": dictionary.get("catalogSource"),
            "geometry": str(FRAME.relative_to(ROOT)).replace("\\", "/"),
            "localGeodatabase": ("GEODATA/BasinATLAS_Data_v10.gdb reads levels 1-9 only; levels 10, "
                                 "11 and 12 are empty in this copy, so attributes come from Earth Engine"),
        },
        "counts": {
            "units": len(features),
            "bySystem": dict(sorted(systems.items())),
            "basinSpecificAttributes": sum(
                1 for column in order if EXTENT_GROUPS.get(columns[column]["spatialExtent"]) == "basin_specific"
            ),
            "accumulationAttributes": sum(
                1 for column in order if EXTENT_GROUPS.get(columns[column]["spatialExtent"]) == "basin_accumulation"
            ),
        },
        "outputs": {
            "levelLadder": str(LADDER.relative_to(ROOT)).replace("\\", "/"),
            "csv": str(TABLE.relative_to(ROOT)).replace("\\", "/"),
            "columnsJSON": str(COLUMNS_JSON.relative_to(ROOT)).replace("\\", "/"),
            "groups": str(GROUPS.relative_to(ROOT)).replace("\\", "/"),
        },
        "qualityNotes": [
            "BasinATLAS attributes describe a fixed reference epoch, not the current year.",
            "basin_specific and basin_accumulation must never be mixed in one total.",
            "Geometry here is simplified for display; exact geometry stays in GEODATA.",
        ],
    }
    write_json(MANIFEST, manifest, compact=False)
    print(f"  {sum(systems.values()):,} level-{LEVEL} reference basins ({dict(sorted(systems.items()))})")
    print(f"  {manifest['counts']['basinSpecificAttributes']} basin-specific + "
          f"{manifest['counts']['accumulationAttributes']} accumulation attributes")
    print(f"  -> {LADDER.relative_to(ROOT)}, {COLUMNS_JSON.relative_to(ROOT)} "
          f"({COLUMNS_JSON.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
