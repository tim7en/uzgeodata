"""Fetch GLIMS outlines for basins the headwater inventory never queried.

PIPELINES/build_glacier_inventory.py filters GLIMS to the runoff-formation
geometry. Everything outside it came back as unassessed, and for a while that was
read as an absence of ice. It is not: asked directly, GLIMS returns 1,510 outlines
over the Hissar ranges that feed the Kashkadarya and the Surkhandarya, and 80 over
the Angren headwaters. Neither is in any file this project held.

This fetches those windows the way the inventory fetches its own, so the numbers
mean the same thing downstream:

* `glac_bound` outlines only, `intrnl_rock` polygons subtracted from the glacier
  they belong to;
* one outline per `glac_id`, the latest `src_date`, because GLIMS is a
  multi-temporal archive and summing it raw counts the same glacier once per
  survey epoch;
* geometry written as published GeoJSON, intersected with the basins by
  build_glacier_basin_extent.py rather than here.

The windows are rectangles rather than basin geometry on purpose. A basin-shaped
filter is what produced the gap this repairs: it decides in advance where ice is
allowed to be. A rectangle over the range asks the archive what it holds, and the
basins are matched to the answer afterwards.

    python PIPELINES/extract_glacier_region_outlines.py
    python PIPELINES/extract_glacier_region_outlines.py --region angren
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / "PUBLISHED/data/hydroclimate"
ASSET = "GLIMS/20230607"
PAGE = 200

REGIONS = {
    "hissar": {
        "label": "Hissar range, Kashkadarya and Surkhandarya headwaters",
        "bbox": [66.5, 38.0, 68.5, 39.6],
    },
    "angren": {
        "label": "Angren (Ahangaran) headwaters, Kurama and Chatkal ranges",
        "bbox": [69.8, 40.8, 70.9, 41.7],
    },
}


def page_features(collection, total: int) -> list[dict]:
    """Download in pages: one getInfo over a few thousand polygons times out."""
    import ee
    listed = collection.toList(total)
    features: list[dict] = []
    for start in range(0, total, PAGE):
        chunk = ee.FeatureCollection(listed.slice(start, min(start + PAGE, total))).getInfo()
        features.extend(chunk["features"])
        print(f"    {len(features)}/{total}", flush=True)
    return features


def latest_per_glacier(features: list[dict]) -> dict[str, dict]:
    """GLIMS keeps every survey of a glacier; only the most recent one is its extent."""
    newest: dict[str, dict] = {}
    for feature in features:
        properties = feature["properties"]
        glacier = properties.get("glac_id")
        if not glacier:
            continue
        date = str(properties.get("src_date") or "")
        held = newest.get(glacier)
        if held is None or date > str(held["properties"].get("src_date") or ""):
            newest[glacier] = feature
    return newest


def fetch(name: str, region: dict) -> dict:
    import ee
    from shapely.geometry import mapping, shape
    from shapely.ops import unary_union

    box = ee.Geometry.Rectangle(region["bbox"])
    glims = ee.FeatureCollection(ASSET).filterBounds(box)
    outlines = glims.filter(ee.Filter.eq("line_type", "glac_bound"))
    rocks = glims.filter(ee.Filter.eq("line_type", "intrnl_rock"))
    counts = (outlines.size().getInfo(), rocks.size().getInfo())
    print(f"  {name}: {counts[0]} outlines, {counts[1]} internal-rock polygons", flush=True)

    kept = latest_per_glacier(page_features(outlines, counts[0]))
    rock_by_glacier: dict[str, list] = defaultdict(list)
    for feature in page_features(rocks, counts[1]) if counts[1] else []:
        rock_by_glacier[feature["properties"].get("glac_id")].append(shape(feature["geometry"]))

    features = []
    for glacier, feature in sorted(kept.items()):
        geometry = shape(feature["geometry"])
        if not geometry.is_valid:
            geometry = geometry.buffer(0)
        rock = rock_by_glacier.get(glacier)
        if rock:
            # Rock showing through a glacier is not ice, and GLIMS records it as its
            # own polygon rather than as a hole in the outline.
            geometry = geometry.difference(unary_union(rock).buffer(0))
        if geometry.is_empty:
            continue
        properties = feature["properties"]
        features.append({
            "type": "Feature",
            "geometry": mapping(geometry),
            "properties": {
                "glac_id": glacier,
                "glac_name": properties.get("glac_name"),
                "src_date": properties.get("src_date"),
                "anlys_time": properties.get("anlys_time"),
                "area": properties.get("area"),
                "analysts": properties.get("analysts"),
                "region": name,
            },
        })

    path = PUBLISHED / f"glims-{name}-outlines.geojson"
    payload = {
        "type": "FeatureCollection",
        "name": f"glims_{name}_outlines",
        "source": {"asset": ASSET, "bbox": region["bbox"], "label": region["label"]},
        "selection": {
            "lineType": "glac_bound",
            "deduplication": "latest src_date per glac_id",
            "internalRock": "intrnl_rock polygons of the same glacier subtracted",
        },
        "retrievedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "features": features,
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    return {
        "region": name,
        "outlinesReturned": counts[0],
        "glaciers": len(features),
        "output": str(path.relative_to(ROOT)).replace("\\", "/"),
        "bytes": path.stat().st_size,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--region", choices=sorted(REGIONS), action="append",
                        help="limit to one window; repeatable")
    arguments = parser.parse_args()

    import ee
    import sys
    sys.path.insert(0, str(ROOT))
    from PIPELINES.extract_dated_snow import PROJECT
    ee.Initialize(project=PROJECT)

    wanted = arguments.region or sorted(REGIONS)
    print(json.dumps([fetch(name, REGIONS[name]) for name in wanted], indent=2))


if __name__ == "__main__":
    main()
