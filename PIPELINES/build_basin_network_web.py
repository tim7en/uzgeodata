"""Publish the transboundary basin network in the shape the trace view reads.

The ontology trace view was built on `PUBLISHED/data/hydrography/relationships.json`,
which is the national extraction: 3,981 level-12 units clipped to Uzbekistan. A
unit that lies in Tajikistan or Kyrgyzstan simply is not in it, so looking up an
upstream basin returns nothing, and a trace from any lowland outlet stops at the
border and ends at the Aral.

This publishes the same record shape over the transboundary frame instead, at all
three analysis levels, and names the control sections so the view can open on one
of them rather than on the terminal lake.

    python PIPELINES/build_basin_network_web.py
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "ONTOLOGY/vocab/hydroclimate-system.json"
PUBLISHED_DIR = ROOT / "PUBLISHED/data/hydroclimate"
BASIN_SOURCE = ROOT / "GEODATA/transboundary_basins_v2"
ROLES = PUBLISHED_DIR / "basin-hydrological-roles.csv"
MANIFEST_SOURCE = PUBLISHED_DIR / "transboundary-basins-manifest.json"
OUTPUT = PUBLISHED_DIR / "basin-network.json"
LEVELS = (7, 10, 12)
# The trace view opens on level 7: it is the grain the ERA5 anomaly series is
# published at, and its geometry is a tenth the weight of level 10. Finer levels
# load on demand when a unit of that level is selected.
DEFAULT_LEVEL = 7


def write_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
    os.replace(temporary, path)


def read_roles() -> dict[tuple[int, int], dict]:
    if not ROLES.exists():
        return {}
    with ROLES.open(encoding="utf-8", newline="") as handle:
        return {(int(row["basin_level"]), int(row["hybas_id"])): row for row in csv.DictReader(handle)}


def read_units(level: int) -> list[dict]:
    path = BASIN_SOURCE / f"hydroatlas-level{level:02d}-full-basins.geojson"
    if not path.exists():
        raise SystemExit(f"Missing {path.relative_to(ROOT)}; run npm run basins:transboundary first")
    return [feature["properties"] for feature in json.loads(path.read_text(encoding="utf-8"))["features"]]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    labels = {pilot["id"]: pilot["label"] for pilot in config["pilotSystems"]}
    source_manifest = json.loads(MANIFEST_SOURCE.read_text(encoding="utf-8"))
    roles = read_roles()
    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    outlets: dict[int, dict[str, int]] = {}
    for level_entry in source_manifest["levels"]:
        outlets[int(level_entry["level"])] = {
            system["headwaterSystemId"]: int(system["headwaterOutletHybasId"])
            for system in level_entry["systems"]
        }

    levels: dict[str, dict] = {}
    control_sections: list[dict] = []
    for level in LEVELS:
        units = read_units(level)
        by_system = outlets.get(level, {})
        outlet_ids = set(by_system.values())
        records = []
        for unit in units:
            hybas_id = int(unit["HYBAS_ID"])
            role = roles.get((level, hybas_id), {})
            records.append({
                "id": hybas_id,
                "pfafId": int(unit["PFAF_ID"]),
                "nextDown": int(unit.get("NEXT_DOWN") or 0),
                "mainBasin": int(unit["MAIN_BAS"]),
                "areaKm2": round(float(unit["SUB_AREA"]), 2),
                "upstreamKm2": round(float(unit["UP_AREA"]), 2),
                "endorheic": int(unit.get("ENDO") or 0) > 0,
                "systemId": unit["system_id"],
                "headwaterSystemId": unit["headwater_system_id"],
                "inHeadwaterFormation": bool(unit["in_headwater_formation"]),
                "isControlSection": hybas_id in outlet_ids,
                "flowPosition": role.get("flow_position", ""),
                "channelClass": role.get("channel_class", ""),
            })
        records.sort(key=lambda record: (record["systemId"], record["id"]))
        levels[str(level)] = {
            "level": level,
            "geometry": f"/data/hydroclimate/basins-level{level:02d}.geojson",
            "basins": records,
            "counts": {
                "units": len(records),
                "formationUnits": sum(1 for record in records if record["inHeadwaterFormation"]),
            },
        }
        for headwater_system, hybas_id in sorted(by_system.items()):
            control_sections.append({
                "id": hybas_id,
                "level": level,
                "systemId": next(r["systemId"] for r in records if r["id"] == hybas_id),
                "headwaterSystemId": headwater_system,
                "label": labels.get(headwater_system, headwater_system),
            })
        print(f"  level {level}: {len(records):,} units, "
              f"{levels[str(level)]['counts']['formationUnits']:,} in formation zones")

    default_section = next(
        section for section in control_sections
        if section["level"] == DEFAULT_LEVEL and section["headwaterSystemId"] == "upper_amu_darya"
    )
    payload = {
        "version": "1.0",
        "generatedAt": retrieved,
        "title": "Amu Darya and Syr Darya natural basin network",
        "spatialScope": "full_basin",
        "nestedScope": "headwater_formation",
        "selection": "MAIN_BAS of the two systems; no administrative clipping",
        "defaultLevel": DEFAULT_LEVEL,
        "defaultFocus": {"level": DEFAULT_LEVEL, "id": default_section["id"]},
        "controlSections": control_sections,
        "levels": levels,
        "counts": {
            "units": sum(entry["counts"]["units"] for entry in levels.values()),
            "controlSections": len(control_sections),
        },
        "qualityNotes": [
            "This frame is not clipped to Uzbekistan; a trace from a control section reaches the "
            "whole contributing area, including the part in Tajikistan, Kyrgyzstan and Afghanistan.",
            "flowPosition and channelClass carry the distinction between a formation unit and a "
            "desert unit with a drawn but dry channel.",
            "The default focus is a control section, not the terminal lake, because the question "
            "this frame answers is where runoff forms rather than where it ends.",
        ],
    }
    write_json(OUTPUT, payload)
    print(f"  default focus: {default_section['label']} outlet {default_section['id']} "
          f"(level {DEFAULT_LEVEL})")
    print(f"  {payload['counts']['units']:,} units -> {OUTPUT.relative_to(ROOT)} "
          f"({OUTPUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
