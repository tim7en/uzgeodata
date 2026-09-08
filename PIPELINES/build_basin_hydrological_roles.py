"""Classify every transboundary basin unit by its place in the flow chain.

HydroBASINS gives the same kind of polygon to a Pskem headwater catchment and to
a stretch of the Kyzylkum, and HydroRIVERS draws a channel through both. Reading
them as the same object is what makes a downstream figure look like an upstream
one. Two independent attributes separate them:

* `flow_position` — where the unit sits in the natural chain: inside a declared
  runoff-formation zone, in transit below it, or an endorheic sink;
* `channel_class` — whether a natural channel actually carries water, measured
  from the long-term average discharge of the HydroRIVERS reaches inside it.

A desert unit keeps its geometry and its routing, but it is never again counted
as a place where runoff forms.

    python PIPELINES/build_basin_hydrological_roles.py
    python PIPELINES/build_basin_hydrological_roles.py --levels 10
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
import sys
from pathlib import Path

import pyogrio

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hydrosheds_sources  # noqa: E402  (path set above)

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "ONTOLOGY/vocab/hydroclimate-system.json"
PUBLISHED_DIR = ROOT / "PUBLISHED/data/hydroclimate"
BASIN_SOURCE = ROOT / "GEODATA/transboundary_basins_v2"
RIVERS = hydrosheds_sources.require(
    "HydroRIVERS_v10_as.gdb/HydroRIVERS_v10_as.gdb",
    hint="HydroRIVERS v1.0 (Asia) carries the reach network and its routing.",
)
HIERARCHY = PUBLISHED_DIR / "basin-hierarchy.csv"
OUTPUT = PUBLISHED_DIR / "basin-hydrological-roles.csv"
MANIFEST = PUBLISHED_DIR / "basin-hydrological-roles.manifest.json"
RIVER_COLUMNS = ["HYRIV_ID", "HYBAS_L12", "DIS_AV_CMS", "LENGTH_KM", "ORD_STRA"]
FIELDS = [
    "observation_unit_id", "basin_level", "system_id", "headwater_system_id",
    "hybas_id", "in_headwater_formation", "flow_position", "channel_class",
    "sub_area_km2", "reach_count", "river_length_km", "peak_discharge_cms",
    "max_strahler_order", "source_asset", "method", "retrieved_at",
]


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def read_units(level: int) -> list[dict]:
    path = BASIN_SOURCE / f"hydroatlas-level{level:02d}-full-basins.geojson"
    if not path.exists():
        raise SystemExit(f"Missing {path.relative_to(ROOT)}; run npm run basins:transboundary first")
    return [feature["properties"] for feature in json.loads(path.read_text(encoding="utf-8"))["features"]]


def read_hierarchy() -> dict[tuple[int, int], int]:
    links: dict[tuple[int, int], int] = {}
    with HIERARCHY.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            links[(int(row["child_level"]), int(row["child_hybas_id"]))] = int(row["parent_hybas_id"])
    return links


def basin_bounds(units_by_level: dict[int, list[dict]]) -> tuple[float, float, float, float]:
    """Bounding box of the coarsest level, which encloses the finer ones."""
    level = min(units_by_level)
    path = BASIN_SOURCE / f"hydroatlas-level{level:02d}-full-basins.geojson"
    minimum = [1e9, 1e9]
    maximum = [-1e9, -1e9]

    def walk(node):
        if isinstance(node[0], (int, float)):
            minimum[0] = min(minimum[0], node[0]); minimum[1] = min(minimum[1], node[1])
            maximum[0] = max(maximum[0], node[0]); maximum[1] = max(maximum[1], node[1])
            return
        for part in node:
            walk(part)

    for feature in json.loads(path.read_text(encoding="utf-8"))["features"]:
        walk(feature["geometry"]["coordinates"])
    return (minimum[0], minimum[1], maximum[0], maximum[1])


def classify(peak: float, reaches: int, thresholds: dict) -> str:
    if not reaches:
        return "no_mapped_channel"
    if peak >= thresholds["perennial"]:
        return "perennial"
    if peak >= thresholds["intermittent"]:
        return "intermittent"
    return "ephemeral_or_dry"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--levels", nargs="+", type=int, default=[7, 10, 12])
    args = parser.parse_args()
    levels = sorted(set(args.levels))
    if any(level not in {7, 10, 12} for level in levels):
        raise SystemExit("Roles are defined for HydroATLAS levels 7, 10 and 12")
    if not RIVERS.parent.exists():
        raise SystemExit(f"Missing {RIVERS.parent.relative_to(ROOT)}")

    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    thresholds = config["channelClassThresholdsCms"]
    units_by_level = {level: read_units(level) for level in levels}
    hierarchy = read_hierarchy()
    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    bounds = basin_bounds(units_by_level)
    print(f"Basin roles | HydroRIVERS bbox {[round(v, 2) for v in bounds]}")
    frame = pyogrio.read_dataframe(
        str(RIVERS), bbox=bounds, read_geometry=False, columns=RIVER_COLUMNS
    )
    print(f"  {len(frame):,} river reaches read")

    # A reach is measured in its own level-12 unit and rolled up the Pfafstetter
    # hierarchy, so every level counts the same channels.
    measured: dict[int, dict[int, dict]] = {level: defaultdict(
        lambda: {"reaches": 0, "length": 0.0, "peak": 0.0, "order": 0}
    ) for level in levels}
    unmatched = 0
    for hybas12, discharge, length, order in zip(
        frame["HYBAS_L12"].astype("int64"), frame["DIS_AV_CMS"], frame["LENGTH_KM"], frame["ORD_STRA"]
    ):
        chain = {12: int(hybas12)}
        chain[10] = hierarchy.get((12, chain[12]))
        chain[7] = hierarchy.get((10, chain[10])) if chain[10] else None
        if chain[10] is None:
            unmatched += 1
            continue
        for level in levels:
            unit_id = chain.get(level)
            if unit_id is None:
                continue
            entry = measured[level][unit_id]
            entry["reaches"] += 1
            entry["length"] += float(length)
            entry["peak"] = max(entry["peak"], float(discharge))
            entry["order"] = max(entry["order"], int(order))
    print(f"  {unmatched:,} reaches outside the two systems ignored")

    rows: list[dict] = []
    summary: dict[str, dict] = {}
    for level in levels:
        for unit in units_by_level[level]:
            hybas_id = int(unit["HYBAS_ID"])
            entry = measured[level].get(hybas_id, {"reaches": 0, "length": 0.0, "peak": 0.0, "order": 0})
            formation = bool(unit["in_headwater_formation"])
            if formation:
                position = "runoff_formation"
            elif int(unit.get("ENDO") or 0) == 2:
                position = "endorheic_sink"
            else:
                position = "transit"
            channel = classify(entry["peak"], entry["reaches"], thresholds)
            rows.append({
                "observation_unit_id": f"{hybas_id}",
                "basin_level": level,
                "system_id": unit["system_id"],
                "headwater_system_id": unit["headwater_system_id"] if formation else "",
                "hybas_id": hybas_id,
                "in_headwater_formation": int(formation),
                "flow_position": position,
                "channel_class": channel,
                "sub_area_km2": f"{float(unit['SUB_AREA']):.2f}",
                "reach_count": entry["reaches"],
                "river_length_km": f"{entry['length']:.2f}",
                "peak_discharge_cms": f"{entry['peak']:.4f}",
                "max_strahler_order": entry["order"] or "",
                "source_asset": "HydroRIVERS v1.0 (Asia)",
                "method": "reach discharge rolled up the Pfafstetter hierarchy",
                "retrieved_at": retrieved,
            })
            if level == 10:
                key = f"{position}/{channel}"
                bucket = summary.setdefault(key, {"units": 0, "areaKm2": 0.0})
                bucket["units"] += 1
                bucket["areaKm2"] += float(unit["SUB_AREA"])

    rows.sort(key=lambda row: (row["basin_level"], row["system_id"], row["hybas_id"]))
    write_csv(OUTPUT, FIELDS, rows)
    for key in sorted(summary):
        bucket = summary[key]
        bucket["areaKm2"] = round(bucket["areaKm2"], 1)
        print(f"    level 10 {key:38} {bucket['units']:5,} units {bucket['areaKm2']:11,.0f} km2")

    manifest = {
        "version": "1.0",
        "generatedAt": retrieved,
        "observationClass": "derived_indicator",
        "source": {
            "riverNetwork": "HydroRIVERS v1.0, Asia",
            "container": str(RIVERS.relative_to(ROOT)).replace("\\", "/"),
            "basins": "GEODATA/transboundary_basins_v2",
            "discharge": "DIS_AV_CMS, long-term average natural discharge, modelled",
        },
        "vocabulary": {
            "flow_position": {
                "runoff_formation": "inside a declared formation zone, upstream of its control section",
                "transit": "inside the natural basin but below every declared control section",
                "endorheic_sink": "terminal unit of the endorheic system (HydroBASINS ENDO = 2)",
            },
            "channel_class": {
                "perennial": f"peak reach discharge >= {thresholds['perennial']} m3/s",
                "intermittent": f"peak reach discharge >= {thresholds['intermittent']} m3/s",
                "ephemeral_or_dry": "a channel is mapped but its long-term average flow is below that",
                "no_mapped_channel": "no HydroRIVERS reach falls inside the unit",
            },
        },
        "levels": levels,
        "rows": len(rows),
        "level10Summary": summary,
        "outputs": {"csv": str(OUTPUT.relative_to(ROOT)).replace("\\", "/")},
        "qualityNotes": [
            "DIS_AV_CMS is a modelled long-term average, not a gauge record; it classifies a "
            "channel, it does not measure this year's flow.",
            "A mapped channel is not a flowing river: most of the Kyzylkum and Karakum units "
            "carry a HydroRIVERS line whose long-term average is below 0.1 m3/s.",
            "Position and channel class are independent: a formation unit can be seasonally dry "
            "and a transit unit can be perennial.",
        ],
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  {len(rows):,} rows -> {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
