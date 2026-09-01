"""Annual land cover area per administrative unit or per basin, from Earth Engine.

The single-district analysis answers one question once. This fills a table: every
unit, every year, every class, so the ontology holds the measurement instead of
re-deriving it. Recomputing is the expensive part — an Earth Engine reduction per
unit-year — and a stored table is what stops that cost being paid again every
time somebody asks what happened to the cropland.

Written as an edge list rather than a set of assertions, following what the
entity schema already says: individual features are not minted as entities, and a
measured relation between a dataset and thousands of features belongs in a
relationship table. This one carries a year column, which the others do not — it
is the first time series in the graph.

Cost, measured rather than guessed: about 3.1 s per unit-year at 10 m, 1.2 s at
30 m for 0.04% less accuracy. Districts are therefore an hour and a half of
wall clock; level-12 basins would be a day, which is why basins default to a
coarser scale and why this writes each row as it arrives and skips what it
already has. Interrupt it and run it again — it resumes.

    python PIPELINES/build_landcover_statistics.py --level admin
    python PIPELINES/build_landcover_statistics.py --level basin --scale 30
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "PUBLISHED" / "data" / "ontology"
MANIFEST = ROOT / "ONTOLOGY" / "instances" / "landcover-statistics.json"

PROJECT = "ee-sabitovty"
ASSET = "projects/sat-io/open-datasets/landcover/ESRI_Global-LULC_10m_TS"

CLASSES = {
    1: "Water", 2: "Trees", 4: "Flooded vegetation", 5: "Crops",
    7: "Built area", 8: "Bare ground", 9: "Snow/ice", 10: "Clouds", 11: "Rangeland",
}

SOURCES = {
    "admin": {
        "path": "PUBLISHED/data/admin/adm2.geojson",
        "key": "pcode",
        "label": "nameEn",
        "output": "2_LAND/2.1_LANDCOVER_ADMIN_YEAR/landcover-admin-year.csv",
        "unitColumn": "pcode",
        "subjectType": "AdminArea",
        "dataset": "esri-io-landcover-10m",
        "predicate": "uz:hasAdminStatistic",
        "scale": 10,
    },
    "basin": {
        "path": "PUBLISHED/data/hydrography/basins.geojson",
        "key": "HYBAS_ID",
        "label": "HYBAS_ID",
        "output": "2_LAND/2.2_LANDCOVER_BASIN_YEAR/landcover-basin-year.csv",
        "unitColumn": "basin_id",
        "subjectType": "Basin",
        "dataset": "esri-io-landcover-10m",
        "predicate": "uz:hasBasinStatistic",
        # Level 12 averages about 110 km2 and there are thousands of them, so the
        # reduction runs coarser by default. At 30 m the area of a class inside a
        # basin moves by well under a tenth of a percent, which is far smaller
        # than the year-to-year change the table exists to record.
        "scale": 30,
    },
}


def units(config: dict) -> list[tuple[str, str, dict]]:
    collection = json.loads((ROOT / config["path"]).read_text(encoding="utf8"))
    rows = []
    for feature in collection["features"]:
        properties = feature["properties"]
        rows.append((str(properties[config["key"]]), str(properties[config["label"]]), feature["geometry"]))
    return rows


def done_already(target: Path, unit_column: str) -> set[tuple[str, int]]:
    """Which unit-years the table already holds, so a rerun resumes."""
    if not target.exists():
        return set()
    with target.open(encoding="utf8", newline="") as handle:
        return {(row[unit_column], int(row["year"])) for row in csv.DictReader(handle)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--level", choices=sorted(SOURCES), default="admin")
    parser.add_argument("--years", nargs="*", type=int,
                        default=list(range(2017, 2026)), help="Years to measure.")
    parser.add_argument("--scale", type=int, help="Reduction scale in metres. Overrides the default.")
    parser.add_argument("--limit", type=int, help="Stop after this many units, for a trial run.")
    args = parser.parse_args()

    config = SOURCES[args.level]
    scale = args.scale or config["scale"]
    target = OUT_DIR / config["output"]
    unit_column = config["unitColumn"]

    try:
        import ee
        ee.Initialize(project=PROJECT)
        ee.Number(1).getInfo()
    except Exception as error:
        raise SystemExit(
            f"Earth Engine is not available: {str(error).strip()[:160]}\n"
            f"  Run: earthengine authenticate --project {PROJECT}") from error

    collection = ee.ImageCollection(ASSET)
    mosaics = {year: collection.filterDate(f"{year}-01-01", f"{year + 1}-01-01").mosaic()
               for year in args.years}

    rows = units(config)
    if args.limit:
        rows = rows[:args.limit]
    already = done_already(target, unit_column)
    todo = [(unit, label, geometry, year)
            for unit, label, geometry in rows
            for year in args.years if (unit, year) not in already]

    print(f"{args.level}: {len(rows):,} units x {len(args.years)} years at {scale} m")
    print(f"  {len(already):,} unit-years already in {target.relative_to(ROOT)}, {len(todo):,} to measure")
    if not todo:
        print("  nothing to do")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fresh = not target.exists()
    started = time.time()
    written = 0

    with target.open("a", encoding="utf8", newline="") as handle:
        writer = csv.writer(handle)
        if fresh:
            writer.writerow(["dataset_id", unit_column, "unit_name", "year",
                             "class_code", "class_name", "km2"])
        for position, (unit, label, geometry, year) in enumerate(todo, start=1):
            region = ee.Geometry(geometry)
            try:
                grouped = ee.Image.pixelArea().addBands(mosaics[year]).reduceRegion(
                    reducer=ee.Reducer.sum().group(groupField=1, groupName="class"),
                    geometry=region, scale=scale, maxPixels=1e10, tileScale=4,
                ).getInfo()
            except Exception as error:
                # One bad geometry should not lose the hours already banked.
                print(f"  ! {unit} {year}: {str(error).strip()[:110]}", flush=True)
                continue
            for group in grouped.get("groups", []):
                code = int(group["class"])
                writer.writerow([config["dataset"], unit, label, year, code,
                                 CLASSES.get(code, str(code)), round(group["sum"] / 1e6, 4)])
                written += 1
            handle.flush()
            if position % 25 == 0 or position == len(todo):
                rate = (time.time() - started) / position
                left = (len(todo) - position) * rate
                print(f"  {position:,}/{len(todo):,} unit-years · {rate:.1f}s each · "
                      f"{left / 60:.0f} min left", flush=True)

    MANIFEST.write_text(json.dumps({
        "version": "1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "predicate": config["predicate"],
        "subjectType": "Dataset",
        "objectType": config["subjectType"],
        "source": {"platform": "Google Earth Engine", "project": PROJECT, "asset": ASSET,
                   "product": "Impact Observatory / Esri 10 m Annual Land Use Land Cover, 9-class"},
        "measure": "area of each land cover class inside the unit, km2",
        "method": ("ee.Image.pixelArea() summed per class through a grouped reducer, so ground "
                   "area is correct whatever projection the reduction lands in. Deriving area "
                   "from the scale would be wrong here: the collection mosaics UTM tiles, and a "
                   "nominal 10 m pixel covers 100·cos(latitude) m2 in the geographic fallback."),
        "scaleMetres": scale,
        "years": args.years,
        "counts": {"units": len(rows), "years": len(args.years), "rows": written + len(already)},
        "output": str(target.relative_to(ROOT)),
    }, ensure_ascii=False, indent=2), encoding="utf8")

    print(f"\n  {written:,} rows written · {(time.time() - started) / 60:.1f} min")
    print(f"  -> {target.relative_to(ROOT)}")
    print(f"  -> {MANIFEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
