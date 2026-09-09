"""Unify the delivered gauge, canal and meteorological-station metadata.

Two families arrived in `storage/meteo_gages_loc`:

* `gages_data_rus.xlsx` - 113 river gauges, canal heads and spillway outlets,
  with an elevation column. `Water discharges.xlsx` lists the same 113 sites
  by the same INDEX, minus elevation; it is cross-checked here, not merged,
  because it never disagrees and would otherwise silently duplicate rows.
* `Meteostan sheip original.zip` - a shapefile of 86 meteorological stations.
  Its member names are Cyrillic but the zip was written with a DOS codepage
  (cp866), so every unpacked filename is mojibake unless decoded as such.

Both deliveries were typed with a keyboard layout that sometimes lagged, so a
Cyrillic word can start with a Latin letter drawn identically in both
alphabets ("Cырдарья" is Latin C then five Cyrillic letters). `lib_cyrillic`
repairs that before anything is matched, counted or translated, because a
station split across two spellings is a station this project can silently
double-count.

Every row is cross-checked against the station entities the ontology already
carries (`ONTOLOGY/instances/entities.json`, network `uzhydromet-gauge` /
`uzhydromet-meteo`), so a mismatch is reported rather than assumed away.

    python PIPELINES/build_hydromet_station_network.py
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import zipfile
import hashlib
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from lib_cyrillic import clean_text, has_cyrillic, normalize_cyrillic, transliterate

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "storage/meteo_gages_loc"
PUBLISHED_DIR = ROOT / "PUBLISHED/data/hydroclimate"
ENTITIES = ROOT / "ONTOLOGY/instances/entities.json"
CACHE_DIR = ROOT / "WORKSPACE/meteo_station_shapefile_cache"

GAUGES_CSV = PUBLISHED_DIR / "hydromet-gauge-network.csv"
METEO_CSV = PUBLISHED_DIR / "hydromet-meteo-network.csv"
MANIFEST = PUBLISHED_DIR / "hydromet-station-network.manifest.json"

# Uzbekistan's extent, generously buffered; a coordinate outside this box is
# not a decimal-point slip somewhere else in the row, it is unusable.
LON_RANGE = (54.0, 74.5)
LAT_RANGE = (36.5, 46.0)

ELEVATION_SENTINEL = -32768.0
# nameCat / stationClass codes from the delivery, decoded once rather than
# left as bare acronyms in the published table.
CATEGORY_LABELS = {
    "M-II": "hydrometeorological station, class II",
    "M-I": "hydrometeorological station, class I",
    "M-III": "hydrometeorological station, class III",
    "АМСГ": "aviation meteorological station (АМСГ)",
    "Г-1": "hydrological post, class I (Г-1)",
    "Г-2": "hydrological post, class II (Г-2)",
}


from hydromet.io import write_csv, write_json


def coordinate_flag(longitude, latitude) -> str:
    if longitude is None or latitude is None or not all(math.isfinite(v) for v in (longitude, latitude)):
        return "missing"
    if not (LON_RANGE[0] <= longitude <= LON_RANGE[1] and LAT_RANGE[0] <= latitude <= LAT_RANGE[1]):
        return "outside_uzbekistan_extent"
    return "ok"


def station_type(river_raw: str) -> str:
    head = river_raw.strip().split()[0] if river_raw.strip() else ""
    head = head.rstrip(",.")
    if head == "р":
        return "river_gauge"
    if head == "кан":
        return "canal"
    if river_raw.strip().lower().startswith("сброс"):
        return "outlet"
    return "other"


def load_entity_ids(network_prefix: str) -> set[str]:
    if not ENTITIES.exists():
        return set()
    data = json.loads(ENTITIES.read_text(encoding="utf-8"))
    return {
        entity["id"] for entity in data.get("entities", [])
        if entity.get("type") == "MonitoringStation"
        and entity["id"].startswith(f"uz:station/{network_prefix}-")
    }


def build_gauge_network(retrieved: str) -> tuple[list[dict], dict]:
    import pandas as pd

    gauges_path = SOURCE_DIR / "gages_data_rus.xlsx"
    discharge_path = SOURCE_DIR / "Water discharges.xlsx"
    gauges = pd.read_excel(gauges_path)
    if gauges['INDEX'].isna().any() or gauges['INDEX'].duplicated().any():
        raise ValueError('Gauge INDEX must be present and unique.')
    rows: list[dict] = []
    homoglyph_fixes = 0
    elevation_sentinels = 0
    coordinate_issues = 0
    type_counts: dict[str, int] = {}

    for _, record in gauges.iterrows():
        river_raw = clean_text(record["RIVERS"])
        location_raw = clean_text(record["LOCATION"])
        river_clean = normalize_cyrillic(river_raw)
        location_clean = normalize_cyrillic(location_raw)
        if river_clean != river_raw or location_clean != location_raw:
            homoglyph_fixes += 1

        index = int(record["INDEX"])
        longitude = float(record["X"]) if pd.notna(record["X"]) else None
        latitude = float(record["Y"]) if pd.notna(record["Y"]) else None
        flag = coordinate_flag(longitude, latitude)
        if flag != "ok":
            coordinate_issues += 1

        elevation_raw = record["Высоты"]
        elevation_is_sentinel = pd.notna(elevation_raw) and float(elevation_raw) == ELEVATION_SENTINEL
        if elevation_is_sentinel:
            elevation_sentinels += 1
        elevation_m = None if (pd.isna(elevation_raw) or elevation_is_sentinel) else float(elevation_raw)

        kind = station_type(river_clean)
        type_counts[kind] = type_counts.get(kind, 0) + 1

        rows.append({
            "entity_id": f"uz:station/gauge-{index}",
            "index": index,
            "station_number": int(record["NUMBER"]),
            "station_type": kind,
            "river_or_canal_raw": river_raw,
            "river_or_canal_cyrillic": river_clean,
            "river_or_canal_latin": transliterate(river_clean),
            "location_raw": location_raw,
            "location_cyrillic": location_clean,
            "location_latin": transliterate(location_clean),
            "label_latin": f"{transliterate(river_clean)} ({transliterate(location_clean)})",
            "longitude": longitude,
            "latitude": latitude,
            "coordinate_flag": flag,
            "coordinate_crs_status": "geographic_degrees_assumed_source_crs_not_declared",
            "elevation_m": elevation_m,
            "elevation_source": "workbook_height_method_and_vertical_datum_unspecified",
            "elevation_flag": "sentinel_removed" if elevation_is_sentinel else ("missing" if elevation_m is None else "ok"),
            "source_file": gauges_path.name,
            "retrieved_at": retrieved,
        })

    # Cross-check Water discharges.xlsx: same 113 sites, no elevation column.
    cross_check = {"file": discharge_path.name, "rowsCompared": 0, "disagreements": []}
    if discharge_path.exists():
        subset = pd.read_excel(discharge_path)
        merged = gauges.merge(subset, on="INDEX", suffixes=("_g", "_w"))
        cross_check["rowsCompared"] = len(merged)
        for column in ("RIVERS", "LOCATION", "X", "Y"):
            mismatched = merged[merged[f"{column}_g"].astype(str) != merged[f"{column}_w"].astype(str)]
            for _, bad in mismatched.iterrows():
                cross_check["disagreements"].append({
                    "index": int(bad["INDEX"]), "column": column,
                    "gages_data_rus": str(bad[f"{column}_g"]), "water_discharges": str(bad[f"{column}_w"]),
                })

    entity_ids = load_entity_ids("gauge")
    matched = sum(1 for row in rows if row["entity_id"] in entity_ids)
    stats = {
        "rows": len(rows),
        "stationTypes": type_counts,
        "homoglyphFixes": homoglyph_fixes,
        "coordinateIssues": coordinate_issues,
        "elevationSentinelsRemoved": elevation_sentinels,
        "crossCheck": cross_check,
        "matchedOntologyEntities": matched,
        "ontologyEntities": len(entity_ids),
    }
    return rows, stats


def extract_shapefile() -> Path | None:
    archive = SOURCE_DIR / "Meteostan sheip original.zip"
    if not archive.exists():
        return None
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    shp_path = None
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            # The archive was written on a DOS codepage; every filename must be
            # decoded from cp866, not read as the utf-8/cp437 zip default.
            name = info.filename if info.flag_bits & 0x800 else info.filename.encode("cp437").decode("cp866")
            target = (CACHE_DIR / name).resolve()
            if not target.is_relative_to(CACHE_DIR.resolve()):
                raise ValueError("Unsafe archive member path")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            if name.lower().endswith(".shp"):
                shp_path = target
    return shp_path


def build_meteo_network(retrieved: str) -> tuple[list[dict], dict]:
    shp_path = extract_shapefile()
    if shp_path is None:
        return [], {"rows": 0, "note": "Meteostan shapefile not found"}

    import geopandas as gpd

    frame = gpd.read_file(shp_path, encoding="cp1251")
    if frame.crs is None:
        raise ValueError("Station shapefile has no declared CRS")
    source_crs = str(frame.crs)
    frame = frame.to_crs("EPSG:4326")
    key_counts = Counter(int(float(v)) for v in frame['NomerS'] if v is not None and v == v)

    rows: list[dict] = []
    homoglyph_fixes = 0
    coordinate_issues = 0
    for _, record in frame.iterrows():
        key = record.get("NomerS")
        if key is None or (hasattr(key, "__float__") and key != key):
            continue
        key = int(float(key))
        name_raw = clean_text(record.get("NameSt"))
        name_clean = normalize_cyrillic(name_raw)
        if name_clean != name_raw:
            homoglyph_fixes += 1
        longitude, latitude = float(record.geometry.x), float(record.geometry.y)
        flag = coordinate_flag(longitude, latitude)
        if flag != "ok":
            coordinate_issues += 1
        category = clean_text(record.get("nameCat"))
        identity = f"{name_clean}|{longitude:.6f}|{latitude:.6f}"
        reliable_key = key > 0 and key_counts[key] == 1
        entity_id = f"uz:station/meteo-{key}" if reliable_key else 'uz:station/meteo-local-' + hashlib.sha256(identity.encode()).hexdigest()[:12]
        rows.append({
            "entity_id": entity_id,
            "identity_flag": "source_unique" if reliable_key else "local_id_source_key_missing_or_duplicate",
            "station_key": key,
            "name_raw": name_raw,
            "name_cyrillic": name_clean,
            "name_latin": transliterate(name_clean),
            "category_code": category,
            "category_label": CATEGORY_LABELS.get(category, category),
            "longitude": round(longitude, 6),
            "latitude": round(latitude, 6),
            "coordinate_flag": flag,
            "source_file": "Meteostan sheip original.zip",
            "source_crs": source_crs,
            "retrieved_at": retrieved,
        })

    entity_ids = load_entity_ids("meteo")
    if len({r['entity_id'] for r in rows}) != len(rows):
        raise ValueError('Meteorological identities are not unique.')
    matched = sum(1 for row in rows if row["entity_id"] in entity_ids)
    stats = {
        "rows": len(rows),
        "homoglyphFixes": homoglyph_fixes,
        "coordinateIssues": coordinate_issues,
        "matchedOntologyEntities": matched,
        "ontologyEntities": len(entity_ids),
        "ontologyEntitiesNotInShapefile": sorted(entity_ids - {row["entity_id"] for row in rows}),
        "localIdentities": sum(r['identity_flag'] != 'source_unique' for r in rows),
    }
    return rows, stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    gauge_rows, gauge_stats = build_gauge_network(retrieved)
    gauge_rows.sort(key=lambda row: row["index"])
    write_csv(GAUGES_CSV, list(gauge_rows[0]), gauge_rows)
    print(f"Gauges/canals: {len(gauge_rows)} sites, "
          f"{gauge_stats['homoglyphFixes']} homoglyph fixes, "
          f"{gauge_stats['elevationSentinelsRemoved']} elevation sentinels removed, "
          f"{gauge_stats['matchedOntologyEntities']}/{gauge_stats['ontologyEntities']} matched to the ontology")

    meteo_rows, meteo_stats = build_meteo_network(retrieved)
    if meteo_rows:
        meteo_rows.sort(key=lambda row: row["station_key"])
        write_csv(METEO_CSV, list(meteo_rows[0]), meteo_rows)
        print(f"Meteo stations: {len(meteo_rows)} sites, "
              f"{meteo_stats['homoglyphFixes']} homoglyph fixes, "
              f"{meteo_stats['matchedOntologyEntities']}/{meteo_stats['ontologyEntities']} matched to the ontology")
    else:
        print("Meteo stations: none read -", meteo_stats.get("note", ""))

    manifest = {
        "version": "1.0",
        "generatedAt": retrieved,
        "observationClass": "station_metadata",
        "sources": [
            {"file": name, "role": role, "sha256": hashlib.sha256((SOURCE_DIR/name).read_bytes()).hexdigest()}
            for name,role in [("gages_data_rus.xlsx", "delivered gauge/canal/outlet metadata"),
                ("Water discharges.xlsx", "cross-check metadata, not discharge observations"),
                ("Meteostan sheip original.zip", "meteorological station shapefile")]
        ],
        "gaugeNetwork": gauge_stats,
        "meteoNetwork": meteo_stats,
        "notes": [
            "Cyrillic text was repaired for Latin-lookalike letters typed under the wrong "
            "keyboard layout (e.g. Latin C in 'Cырдарья') before matching or translating; "
            "the raw and repaired forms are both published so the fix is auditable.",
            "elevation_m is null where the source recorded the -32768 DEM no-data sentinel; "
            "the sentinel is reported, not guessed at.",
            "coordinate_flag marks points outside Uzbekistan's extent; they are kept, not dropped.",
        ],
    }
    write_json(MANIFEST, manifest)
    print(f"Manifest -> {MANIFEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
