"""Publish the 2023 Kashkadarya and Surkhandarya glacier catalogues.

Both workbooks give one row per glacier: a catalogue name/number, area,
perimeter and a DMS centre point ("39° 03' 31.14\" N"), the same layout
`build_pskem_observations.py` already decodes for the Pskem catalogue. They
are kept as a separate, standalone inventory rather than folded into the
GLIMS-based `build_glacier_inventory.py` pipeline: that pipeline traces
multi-temporal GLIMS outlines against the headwater-formation basins, and
these two catalogues are a different survey with no outline geometry, only
a centre point and a reported area.

Two data problems are fixed here, not just reported, because both are
unambiguous:

* an exact duplicate row (same name, area, perimeter and point) is one
  glacier counted twice, so the second copy is dropped;
* two different glaciers sharing one catalogue number is a source numbering
  collision, not a duplicate glacier, so each gets a stable `a`/`b` suffix
  rather than one of them being discarded.

    python PIPELINES/build_regional_glacier_inventories.py
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import hashlib
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "storage"
PUBLISHED_DIR = ROOT / "PUBLISHED/data/hydroclimate"

INVENTORY_CSV = PUBLISHED_DIR / "regional-glaciers.csv"
INVENTORY_GEOJSON = PUBLISHED_DIR / "regional-glaciers.geojson"
MANIFEST = PUBLISHED_DIR / "regional-glaciers.manifest.json"

SHEETS = [
    ("Kashkadarya_2023.xlsx", "Kashkadarya_glaciers", "Kashkadarya", "р. Кашкадарья / Kashkadarya"),
    ("Surhandarya_2023.xlsx", "Surhan_glaciers", "Surkhandarya", "р. Сурхандарья / Surkhandarya"),
]

DMS = re.compile(r"\s*(\d+)\D+(\d+)\D+([\d.]+)\D*([NSEW])")


def dms_to_decimal(value: str):
    match = DMS.fullmatch(str(value).strip())
    if not match:
        return None
    degrees, minutes, seconds, hemisphere = match.groups()
    limit = 90 if hemisphere in {'N', 'S'} else 180
    if not (0 <= int(minutes) < 60 and 0 <= float(seconds) < 60):
        return None
    decimal = int(degrees) + int(minutes) / 60 + float(seconds) / 3600
    if decimal > limit:
        return None
    return -decimal if hemisphere in {"S", "W"} else decimal


from hydromet.io import write_csv, write_json


def read_basin(path: Path, sheet: str, basin: str, basin_label: str, retrieved: str):
    import pandas as pd

    frame = pd.read_excel(path, sheet_name=sheet)
    frame.columns = ["name", "area_km2", "perimeter_m", "lat", "lon"]

    seen: dict[tuple, str] = {}
    exact_duplicates = 0
    rejected = []
    rows = []
    for _, record in frame.iterrows():
        name = str(record["name"]).strip()
        area = float(record["area_km2"])
        perimeter = float(record["perimeter_m"])
        latitude = dms_to_decimal(record["lat"])
        longitude = dms_to_decimal(record["lon"])
        fingerprint = (name, round(area, 6), round(perimeter, 3), record["lat"], record["lon"])
        if fingerprint in seen:
            exact_duplicates += 1
            continue
        seen[fingerprint] = name
        if (latitude is None or longitude is None or not math.isfinite(area)
                or not math.isfinite(perimeter) or area <= 0 or perimeter <= 0):
            rejected.append({'source_row': int(record.name)+2, 'name': name, 'reason': 'invalid_geometry_or_size'})
            continue
        rows.append({
            "glacier_key": name,
            "basin": basin,
            "area_km2": round(area, 4),
            "perimeter_m": round(perimeter, 1),
            "longitude": round(longitude, 6),
            "latitude": round(latitude, 6),
            "duplicate_catalogue_number": "no",
            "source_file": path.name,
            "source_sheet": sheet,
            "source_row": int(record.name)+2,
            "inventory_year": 2023,
            "geometry_role": "reported_centre_no_outline",
            "source_basin_label": basin_label,
            "retrieved_at": retrieved,
        })

    # A catalogue number reused by two different glaciers: keep both, suffix
    # the key so neither the id nor a later join silently picks one.
    counts = Counter(row["glacier_key"] for row in rows)
    collisions = {key for key, count in counts.items() if count > 1}
    if collisions:
        suffix_seen: dict[str, int] = defaultdict(int)
        for row in rows:
            if row["glacier_key"] in collisions:
                index = suffix_seen[row["glacier_key"]]
                suffix_seen[row["glacier_key"]] += 1
                row["duplicate_catalogue_number"] = "yes"
                row["glacier_key"] = f"{row['glacier_key']}{chr(ord('a') + index)}"

    return rows, {
        "rows": len(rows),
        "exactDuplicatesRemoved": exact_duplicates,
        "catalogueNumberCollisions": sorted(collisions),
        "rejectedRows": rejected,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    all_rows: list[dict] = []
    stats = {}
    for filename, sheet, basin, label in SHEETS:
        path = SOURCE_DIR / filename
        if not path.exists():
            print(f"skipped, absent: {filename}")
            continue
        rows, basin_stats = read_basin(path, sheet, basin, label, retrieved)
        all_rows.extend(rows)
        stats[basin] = basin_stats
        print(f"{filename}: {basin_stats['rows']} glaciers, "
              f"{basin_stats['exactDuplicatesRemoved']} exact duplicate row(s) removed, "
              f"{len(basin_stats['catalogueNumberCollisions'])} catalogue-number collision(s) resolved")

    all_rows.sort(key=lambda row: (row["basin"], row["glacier_key"]))
    write_csv(INVENTORY_CSV, list(all_rows[0]) if all_rows else [], all_rows)

    write_json(INVENTORY_GEOJSON, {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [row["longitude"], row["latitude"]]},
            "properties": {key: value for key, value in row.items()
                            if key not in {"longitude", "latitude"}},
        } for row in all_rows],
    })

    manifest = {
        "version": "1.0",
        "generatedAt": retrieved,
        "observationClass": "inventory",
        "spatialScope": "point (centre of glacier polygon, source geometry not delivered)",
        "sources": [{"file": filename, "basin": basin,
                     "sha256": hashlib.sha256((SOURCE_DIR/filename).read_bytes()).hexdigest() if (SOURCE_DIR/filename).exists() else None}
                    for filename, _, basin, _ in SHEETS],
        "counts": {"glaciers": len(all_rows)},
        "basins": stats,
        "notes": [
            "This is a separate 2023 point-catalogue survey, not the GLIMS-based inventory "
            "build_glacier_inventory.py publishes; the two are not merged because this delivery "
            "carries no outline geometry, only a reported area and a centre point.",
            "An exact duplicate row (same name, area, perimeter and point) was dropped as one "
            "glacier counted twice; two different glaciers sharing one catalogue number were both "
            "kept and given an a/b suffix instead.",
        ],
    }
    write_json(MANIFEST, manifest)
    print(f"\n{len(all_rows)} glaciers -> {INVENTORY_CSV.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
