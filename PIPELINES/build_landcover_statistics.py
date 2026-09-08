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

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parent.parent
from ontology_paths import dataset_dir
MANIFEST = ROOT / "ONTOLOGY" / "instances" / "landcover-statistics.json"

PROJECT = "ee-sabitovty"
ASSET = "projects/sat-io/open-datasets/landcover/ESRI_Global-LULC_10m_TS"
BATCH_SIZE = 250

CLASSES = {
    1: "Water", 2: "Trees", 4: "Flooded vegetation", 5: "Crops",
    7: "Built area", 8: "Bare ground", 9: "Snow/ice", 10: "Clouds", 11: "Rangeland",
}

SOURCES = {
    "admin": {
        "path": "PUBLISHED/data/admin/adm2.geojson",
        "key": "pcode",
        "label": "nameEn",
        "folder": "LANDCOVER_ADMIN_YEAR", "file": "landcover-admin-year.csv",
        "unitColumn": "pcode",
        "subjectType": "AdminArea",
        "sourceId": "esri-io-landcover-10m",
        "predicate": "uz:hasAdminStatistic",
        "scale": 10,
    },
    "basin": {
        "path": "PUBLISHED/data/review/basinatlas/basinatlas_uz_lev12.geojson",
        "key": "HYBAS_ID",
        "label": "HYBAS_ID",
        "folder": "LANDCOVER_BASIN_YEAR", "file": "landcover-basin-year.csv",
        "unitColumn": "basin_id",
        "subjectType": "Basin",
        "sourceId": "esri-io-landcover-10m",
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


def table_counts(target: Path, unit_column: str) -> tuple[int, int]:
    """Return physical rows and complete unit-year keys in the stored table."""
    if not target.exists():
        return 0, 0
    with target.open(encoding="utf8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return len(rows), len({(row[unit_column], int(row["year"])) for row in rows})


def normalize_existing_table(target: Path) -> tuple[int, int]:
    """Keep the stored relationship table inside the product's 9-class domain.

    The upstream tiled collection contains a minute number of pixels with legacy
    values 3 and 6, although neither value belongs to the published 9-class time
    series.  They are excluded instead of being silently presented as new land-
    cover classes.  Known class labels are normalized at the same time.
    """
    if not target.exists():
        return 0, 0
    with target.open(encoding="utf8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        rows = list(reader)
    if not fieldnames:
        return 0, 0

    kept = []
    removed = changed = 0
    for row in rows:
        try:
            code = int(row["class_code"])
        except (KeyError, TypeError, ValueError):
            removed += 1
            continue
        if code not in CLASSES:
            removed += 1
            continue
        if row.get("class_name") != CLASSES[code]:
            row["class_name"] = CLASSES[code]
            changed += 1
        kept.append(row)

    if removed or changed:
        temporary = target.with_suffix(target.suffix + ".tmp")
        with temporary.open("w", encoding="utf8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(kept)
        temporary.replace(target)
    return removed, changed


def write_manifest(config: dict, target: Path, rows: list, years: list[int], scale: int) -> None:
    stored_rows, stored_unit_years = table_counts(target, config["unitColumn"])
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
        "years": years,
        "counts": {"units": len(rows), "years": len(years),
                   "unitYears": stored_unit_years, "rows": stored_rows},
        "output": str(target.relative_to(ROOT)),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--level", choices=sorted(SOURCES), default="admin")
    parser.add_argument("--years", nargs="*", type=int,
                        default=list(range(2017, 2026)), help="Years to measure.")
    parser.add_argument("--scale", type=int, help="Reduction scale in metres. Overrides the default.")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE,
                        help="Polygons per Earth Engine request (default: %(default)s).")
    parser.add_argument("--limit", type=int, help="Stop after this many units, for a trial run.")
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")

    config = SOURCES[args.level]
    scale = args.scale or config["scale"]
    target = dataset_dir(config["folder"], "LAND") / config["file"]
    unit_column = config["unitColumn"]

    rows = units(config)
    if args.limit:
        rows = rows[:args.limit]
    removed, normalized = normalize_existing_table(target)
    if removed or normalized:
        print(f"  normalized existing table: {removed:,} out-of-domain rows removed, "
              f"{normalized:,} labels corrected")
    already = done_already(target, unit_column)
    todo = [(unit, label, geometry, year)
            for year in args.years
            for unit, label, geometry in rows if (unit, year) not in already]

    print(f"{args.level}: {len(rows):,} units x {len(args.years)} years at {scale} m")
    print(f"  {len(already):,} unit-years already in {target.relative_to(ROOT)}, {len(todo):,} to measure")
    if not todo:
        write_manifest(config, target, rows, args.years, scale)
        print("  nothing to do")
        return

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

    target.parent.mkdir(parents=True, exist_ok=True)
    fresh = not target.exists()
    started = time.time()
    written = completed = 0

    with target.open("a", encoding="utf8", newline="") as handle:
        writer = csv.writer(handle)
        if fresh:
            writer.writerow(["dataset_id", unit_column, "unit_name", "year",
                             "class_code", "class_name", "km2"])
        for year in args.years:
            pending = [row for row in todo if row[3] == year]
            for start in range(0, len(pending), args.batch_size):
                batch = pending[start:start + args.batch_size]
                features = ee.FeatureCollection([
                    ee.Feature(ee.Geometry(geometry), {"unit": unit, "label": label})
                    for unit, label, geometry, _ in batch
                ])
                try:
                    result = ee.Image.pixelArea().addBands(mosaics[year]).reduceRegions(
                        reducer=ee.Reducer.sum().group(groupField=1, groupName="class"),
                        collection=features, scale=scale, tileScale=4,
                    ).getInfo()
                except Exception as error:
                    # A failed batch remains absent, so the next run retries it.
                    first, last = batch[0][0], batch[-1][0]
                    print(f"  ! {year} batch {first}..{last}: {str(error).strip()[:110]}",
                          flush=True)
                    continue
                for feature in result["features"]:
                    properties = feature["properties"]
                    for group in properties.get("groups", []):
                        code = int(group["class"])
                        if code not in CLASSES:
                            continue
                        writer.writerow([
                            config["sourceId"], properties["unit"], properties["label"], year,
                            code, CLASSES.get(code, str(code)), round(group["sum"] / 1e6, 4),
                        ])
                        written += 1
                completed += len(batch)
                handle.flush()
                rate = (time.time() - started) / completed
                left = (len(todo) - completed) * rate
                print(f"  {completed:,}/{len(todo):,} unit-years · {rate:.2f}s each · "
                      f"{left / 60:.0f} min left", flush=True)

    write_manifest(config, target, rows, args.years, scale)

    print(f"\n  {written:,} rows written · {(time.time() - started) / 60:.1f} min")
    print(f"  -> {target.relative_to(ROOT)}")
    print(f"  -> {MANIFEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
