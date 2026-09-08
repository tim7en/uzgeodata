"""Publish the Amu and Syr river network in tiers matched to the basin zoom ladder.

The unified network is 46,976 reaches and 33 MB, which is more than a landing map
should ever load. Most of that weight is headwater capillaries carrying a fraction
of a cubic metre per second: real channels, but not what a reader is looking for
when the whole region is on screen.

Each tier is selected by long-term average discharge, so the cut is a property of
the river rather than a cartographic guess, and every reach keeps its own
`channel_class` — a line drawn across the Kyzylkum is still a line that carries
almost no water, and the map says so by drawing it dashed.

    python PIPELINES/build_reference_rivers.py
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from shapely.geometry import mapping, shape

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "PUBLISHED/data/hydrography/rivers-unified.geojson"
PUBLISHED_DIR = ROOT / "PUBLISHED/data/hydroclimate"
LADDER = PUBLISHED_DIR / "reference-river-levels.json"
MANIFEST = PUBLISHED_DIR / "reference-rivers.manifest.json"
# Thresholds line up with the basin ladder: main stems while the whole region is
# in view, tributaries as the reader zooms into a system, headwaters at basin
# detail.
TIERS = [
    {"id": "main", "minZoom": 0, "minDischargeCms": 20.0, "simplify": 0.004},
    {"id": "tributary", "minZoom": 7, "minDischargeCms": 5.0, "simplify": 0.002},
    {"id": "headwater", "minZoom": 9, "minDischargeCms": 1.0, "simplify": 0.001},
]


def write_json(path: Path, payload: object, *, compact: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False,
                  separators=(",", ":") if compact else None, indent=None if compact else 2)
        handle.write("\n")
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    if not SOURCE.exists():
        raise SystemExit(f"Missing {SOURCE.relative_to(ROOT)}; build the unified river network first")

    reaches = json.loads(SOURCE.read_text(encoding="utf-8"))["features"]
    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    print(f"Reference rivers | {len(reaches):,} reaches in the unified network")

    published = []
    for tier in TIERS:
        selected = [
            feature for feature in reaches
            if float(feature["properties"].get("DIS_AV_CMS") or 0) >= tier["minDischargeCms"]
        ]
        features = []
        for feature in selected:
            props = feature["properties"]
            geometry = shape(feature["geometry"]).simplify(tier["simplify"], preserve_topology=True)
            if geometry.is_empty:
                continue
            features.append({
                "type": "Feature",
                "properties": {
                    "hyriv_id": int(props["HYRIV_ID"]),
                    "system_id": props["system_id"],
                    "discharge_cms": round(float(props.get("DIS_AV_CMS") or 0), 3),
                    "strahler_order": int(props.get("ORD_STRA") or 0),
                    "channel_class": props.get("channel_class", ""),
                    "in_headwater_formation": int(props.get("in_headwater_formation") or 0),
                },
                "geometry": mapping(geometry),
            })
        features.sort(key=lambda item: item["properties"]["discharge_cms"])
        path = PUBLISHED_DIR / f"reference-rivers-{tier['id']}.geojson"
        write_json(path, {
            "type": "FeatureCollection",
            "name": f"amu_syr_reference_rivers_{tier['id']}",
            "features": features,
        })
        classes = Counter(feature["properties"]["channel_class"] for feature in features)
        published.append({
            "id": tier["id"],
            "minZoom": tier["minZoom"],
            "minDischargeCms": tier["minDischargeCms"],
            "simplifyDegrees": tier["simplify"],
            "reaches": len(features),
            "url": f"/data/hydroclimate/reference-rivers-{tier['id']}.geojson",
            "sizeBytes": path.stat().st_size,
            "channelClasses": dict(sorted(classes.items())),
        })
        print(f"    {tier['id']:>10}: {len(features):>6,} reaches  {path.stat().st_size / 1e6:>5.2f} MB  "
              f"from zoom {tier['minZoom']}  (>= {tier['minDischargeCms']} m3/s)")

    write_json(LADDER, {
        "version": "1.0",
        "generatedAt": retrieved,
        "tiers": published,
        "selection": "long-term average discharge of the reach, DIS_AV_CMS",
        "note": ("DIS_AV_CMS is a modelled long-term average from HydroRIVERS, not a gauge record. "
                 "It selects which reaches are drawn; it never states this year's flow."),
    }, compact=False)

    manifest = {
        "version": "1.0",
        "generatedAt": retrieved,
        "observationClass": "reference",
        "source": {
            "network": str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
            "reaches": len(reaches),
            "asset": "HydroRIVERS v1.0 (Asia)",
        },
        "tiers": published,
        "outputs": {"ladder": str(LADDER.relative_to(ROOT)).replace("\\", "/")},
        "qualityNotes": [
            "Tiers are display selections of one network, not different networks.",
            "A reach classified ephemeral_or_dry keeps that label at every tier so a desert "
            "channel is never drawn as a flowing river.",
            "Geometry is simplified for display; the unified network keeps the full detail.",
        ],
    }
    write_json(MANIFEST, manifest, compact=False)
    print(f"  -> {LADDER.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
