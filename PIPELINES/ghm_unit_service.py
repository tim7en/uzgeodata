"""Human modification per basin and per district, from the global gHM layer.

gHM gives, for every square kilometre, the proportion of it that human activity
has modified — settlement, agriculture, transport, mining and energy, electrical
infrastructure — combined from thirteen source datasets into one 0 to 1 index
for 2016.

It is the only layer in the ontology so far that is genuinely timeless. Not
archival like CHIRTS, which ran and stopped, and not static like a boundary that
merely changes rarely: the collection holds a single image with no
`system:time_start` at all. There is nothing to refresh and no period to fall
behind, so it is stored without a year column and registered as static.

It is measured against both frames. Human modification is a fact about a place
in a way that belongs to whoever governs it as much as to whatever drains it, so
the same index is reduced over level-12 basins and over districts. Both are
affordable because there is only one image to read.

Two figures are kept per unit rather than a mean alone. A mean of 0.3 can be a
uniformly semi-modified landscape or a city beside a desert, and those are
different places; the area shares in each modification band tell them apart.

    python PIPELINES/ghm_unit_service.py
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parent.parent
from ontology_paths import dataset_dir
OUTPUT = dataset_dir("GHM_UNIT_MODIFICATION", "LAND") / "ghm-unit-modification.csv"

PROJECT = "ee-sabitovty"
ASSET = "CSP/HM/GlobalHumanModification"
SCALE = 1000
EPOCH = 2016

# The bands used in the gHM literature. The boundaries matter: 0.1 separates land
# that is essentially wild from land that is measurably touched, and 0.4 is where
# modification stops being incidental and starts dominating the surface.
CLASSES = [("low", 0.0, 0.1), ("moderate", 0.1, 0.4),
           ("high", 0.4, 0.7), ("very_high", 0.7, 1.01)]

FRAMES = {
    "basin": {
        "path": "PUBLISHED/data/review/basinatlas/basinatlas_uz_lev12.geojson",
        "key": "HYBAS_ID", "column": "unit_id", "kind": "Basin",
    },
    "district": {
        "path": "PUBLISHED/data/admin/adm2.geojson",
        "key": "pcode", "column": "unit_id", "kind": "AdminArea",
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--frame", choices=sorted(FRAMES) + ["all"], default="all")
    args = parser.parse_args()

    try:
        import ee
        ee.Initialize(project=PROJECT)
        ee.Number(1).getInfo()
    except Exception as error:
        raise SystemExit(f"Earth Engine unavailable: {str(error).strip()[:150]}\n"
                         f"  Run: earthengine authenticate --project {PROJECT}") from error

    image = ee.ImageCollection(ASSET).first().select("gHM")
    area = ee.Image.pixelArea()

    frames = sorted(FRAMES) if args.frame == "all" else [args.frame]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    with OUTPUT.open("w", encoding="utf8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["frame", "unit_id", "unit_kind", "epoch",
                         "variable", "value", "unit", "quality"])
        for frame in frames:
            config = FRAMES[frame]
            document = json.loads((ROOT / config["path"]).read_text(encoding="utf8"))
            collection = ee.FeatureCollection([
                ee.Feature(ee.Geometry(f["geometry"]),
                           {"unit": str(f["properties"][config["key"]])})
                for f in document["features"]])

            # Mean and the spread around it, plus the area in each band. Area comes
            # from pixelArea rather than a pixel count, for the same reason as the
            # land cover work: this grid is geographic, so a pixel's ground area
            # changes with latitude.
            stack = image.rename("ghm_mean")
            for name, low, high in CLASSES:
                inside = image.gte(low).And(image.lt(high))
                stack = stack.addBands(area.multiply(inside).rename(f"area_{name}"))
            stack = stack.addBands(area.rename("area_total"))

            # One mean reducer covers both quantities. An area share is
            # sum(area x mask) / sum(area), and both sums divide by the same pixel
            # count, so the ratio of their means is the same number — which avoids
            # combining two reducers and the renamed properties that come with it.
            result = stack.reduceRegions(
                collection=collection, reducer=ee.Reducer.mean(), scale=SCALE).getInfo()

            for feature in result["features"]:
                properties = feature["properties"]
                total = properties.get("area_total") or 0
                mean = properties.get("ghm_mean")
                if mean is None or total <= 0:
                    continue
                writer.writerow([frame, properties["unit"], config["kind"], EPOCH,
                                 "ghm_mean", round(mean, 5), "index_0_1", "ok"])
                rows += 1
                for name, *_ in CLASSES:
                    share = (properties.get(f"area_{name}") or 0) / total
                    writer.writerow([frame, properties["unit"], config["kind"], EPOCH,
                                     f"share_{name}", round(share, 5), "fraction", "ok"])
                    rows += 1
            print(f"  {frame}: {len(result['features'])} units", flush=True)

    print(f"\n  {rows:,} observations -> {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
