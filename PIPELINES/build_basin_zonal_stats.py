"""Read the atlas rasters per level-12 basin.

`build_atlas_basin_links.py` answers "how much of this layer is in this basin",
which is the right question for a polygon, a line or a point. It is the wrong
question for a raster of NDVI or drought severity: binning a continuous surface
and measuring the area of each bin throws away the values. What a basin needs
from a surface is what it *reads* there.

So this is the other half: zonal statistics. For every atlas package whose raster
is georeferenced and carries a single data band, it reports per basin the pixel
count, mean, minimum, maximum and standard deviation, plus the majority class
where the raster is categorical rather than continuous.

The rasters are not TIFFs. Each `.lpkx` is a 7-zip archive holding an ESRI File
Geodatabase, and the raster lives inside that, which is why the TIFF-only
converter in `raster_to_geojson.py` never found them. GDAL's OpenFileGDB driver
reads them directly once the archive is unpacked.

Usage:
    python PIPELINES/build_basin_zonal_stats.py [--root .] [--level 12]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import py7zr
    import rasterio
    from rasterio.features import rasterize
    from rasterio.transform import Affine
except ImportError as error:  # pragma: no cover - depends on the workstation
    raise SystemExit(
        "geopandas, rasterio and py7zr are required. py7zr replaces libarchive, "
        "which has no usable Windows wheel."
    ) from error

VECTOR_CRS = "EPSG:4326"
# Above this the band is read decimated. A level-12 basin averages 113 km2, so
# even a decimated grid leaves hundreds of pixels in a typical basin, and the
# alternative is holding a multi-gigapixel array in memory.
DEFAULT_MAX_PIXELS = 40_000_000

# Several packages declare no nodata yet store 255 as fill in an 8-bit band. The
# legends in these rasters top out at 34 classes, so 255 is never a real value
# here, and leaving it in drags a basin mean towards a number that means nothing.
# The assumption is narrow and recorded in the manifest rather than hidden.
BYTE_FILL = 255


def fill_value_for(source) -> float | None:
    if source.nodata is not None:
        return None
    return BYTE_FILL if source.dtypes[0] == "uint8" else None


def infer_kind(declared: str, source, band) -> str:
    """Believe the registry, but name a kind when it had none.

    The band arrives as float64 whatever it was on disk, so the integer test has
    to read the source dtype, not the array's.
    """
    if declared in {"continuous", "categorical"}:
        return declared
    integral = np.dtype(source.dtypes[0]).kind in "iub"
    if integral and len(np.unique(band[np.isfinite(band)])) <= 64:
        return "categorical"
    return declared or "unknown"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def raster_packages(root: Path) -> list[dict]:
    """Atlas datasets whose only geometry is a raster inside a layer package."""
    entities = {e["id"]: e for e in
                read_json(root / "ONTOLOGY" / "instances" / "entities.json",
                          {"entities": []})["entities"]}
    assertions = read_json(root / "ONTOLOGY" / "instances" / "assertions.json",
                           {"assertions": []})["assertions"]
    registry = {r.get("atlasNumber"): r for r in
                read_json(root / "WORKSPACE" / "derived" / "all-map-layers.json", [])}

    distributions = defaultdict(list)
    for assertion in assertions:
        if assertion["predicate"] == "uz:hasDistribution":
            distributions[assertion["subject"]].append(assertion["object"])

    vector_roles = {"web-vector", "raster-polygonized"}
    packages = []
    for dataset in entities.values():
        if dataset.get("type") != "Dataset" or not dataset.get("catalogId"):
            continue
        held = [entities.get(d, {}) for d in distributions.get(dataset["id"], [])]
        if any(d.get("role") in vector_roles for d in held):
            continue  # already covered by the vector overlay
        source = next((d for d in held
                       if d.get("role") == "source-package" and d.get("storedName")), None)
        if source is None:
            continue
        path = root / "WORKSPACE" / "uploads" / source["storedName"]
        legend = (registry.get(dataset.get("atlasNumber"), {}).get("legend") or {})
        packages.append({
            "dataset": dataset["id"],
            "label": dataset["label"],
            "atlasNumber": dataset.get("atlasNumber"),
            "distribution": source["id"],
            "path": path,
            "exists": path.exists(),
            "valueKind": legend.get("type") or "unknown",
        })
    return sorted(packages, key=lambda item: item["atlasNumber"] or 0)


def unpack(archive: Path, into: Path) -> None:
    """Unpack a layer package.

    The archives carry no directory entries, so py7zr will not create the tree
    on its own; make it first or every extraction fails on a bad path.
    """
    with py7zr.SevenZipFile(archive, "r") as handle:
        names = handle.getnames()
    for name in names:
        (into / name).parent.mkdir(parents=True, exist_ok=True)
    with py7zr.SevenZipFile(archive, "r") as handle:
        handle.extractall(path=into)


def basin_labels(basins: gpd.GeoDataFrame, source, shape, transform) -> np.ndarray:
    """Paint each basin's row number onto the raster grid; 0 means no basin."""
    projected = basins.to_crs(source.crs) if source.crs else basins
    shapes = ((geometry, index + 1)
              for index, geometry in enumerate(projected.geometry)
              if geometry is not None and not geometry.is_empty)
    return rasterize(shapes, out_shape=shape, transform=transform,
                     fill=0, dtype="int32", all_touched=False)


def zonal(source, basins: gpd.GeoDataFrame, max_pixels: int):
    """Per-basin statistics for band 1, read decimated if the grid is huge."""
    scale = 1.0
    height, width = source.height, source.width
    if height * width > max_pixels:
        scale = (max_pixels / (height * width)) ** 0.5
        height, width = max(int(height * scale), 1), max(int(width * scale), 1)
    transform = source.transform * Affine.scale(source.width / width, source.height / height)

    band = source.read(1, out_shape=(height, width)).astype("float64")
    labels = basin_labels(basins, source, (height, width), transform)

    valid = labels > 0
    if source.nodata is not None:
        valid &= band != source.nodata
    fill = fill_value_for(source)
    if fill is not None:
        valid &= band != fill
    valid &= np.isfinite(band)
    if not valid.any():
        return None, scale, band

    frame = pd.DataFrame({"basin": labels[valid], "value": band[valid]})
    grouped = frame.groupby("basin")["value"].agg(["count", "mean", "min", "max", "std"])
    return grouped, scale, band


def majority(source, basins: gpd.GeoDataFrame, max_pixels: int):
    """The most common value per basin, for a categorical surface."""
    grouped, _ = None, None
    height, width = source.height, source.width
    if height * width > max_pixels:
        scale = (max_pixels / (height * width)) ** 0.5
        height, width = max(int(height * scale), 1), max(int(width * scale), 1)
    transform = source.transform * Affine.scale(source.width / width, source.height / height)
    band = source.read(1, out_shape=(height, width))
    labels = basin_labels(basins, source, (height, width), transform)
    valid = labels > 0
    if source.nodata is not None:
        valid &= band != source.nodata
    fill = fill_value_for(source)
    if fill is not None:
        valid &= band != fill
    if not valid.any():
        return {}
    frame = pd.DataFrame({"basin": labels[valid], "value": band[valid]})
    modes = frame.groupby("basin")["value"].agg(lambda values: values.value_counts().idxmax())
    return modes.to_dict()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--level", type=int, default=12)
    parser.add_argument("--max-pixels", type=int, default=DEFAULT_MAX_PIXELS)
    args = parser.parse_args(argv)
    root = args.root.resolve()

    package_dir = root / "GEODATA" / "uzbekistan_basinatlas_v10"
    gpkg = package_dir / "uzbekistan_basinatlas_v10.gpkg"
    if not gpkg.exists():
        raise SystemExit(f"Basin reference not found: {gpkg}")
    basins = gpd.read_file(gpkg, layer=f"basinatlas_uz_lev{args.level:02d}",
                           columns=["HYBAS_ID"]).to_crs(VECTOR_CRS)
    basins["HYBAS_ID"] = basins["HYBAS_ID"].astype("int64")
    ids = basins["HYBAS_ID"].to_numpy()
    print(f"basin reference: {len(basins):,} level-{args.level:02d} basins")

    packages = raster_packages(root)
    print(f"raster packages to read: {len(packages)}")

    rows: list[dict] = []
    report = []
    work_root = Path(tempfile.mkdtemp(prefix="uzgeo-raster-"))
    try:
        for index, package in enumerate(packages, start=1):
            entry = {"dataset": package["dataset"], "label": package["label"],
                     "valueKind": package["valueKind"]}
            if not package["exists"]:
                entry["status"] = "package not on disk"
                report.append(entry)
                print(f"  [{index:>2}/{len(packages)}] {package['label'][:40]:<42} not on disk")
                continue

            work = work_root / f"pkg{index}"
            try:
                unpack(package["path"], work)
                gdb = next((p for p in work.rglob("*.gdb") if p.is_dir()), None)
                if gdb is None:
                    entry["status"] = "no geodatabase in the package"
                    raise StopIteration
                with rasterio.open(gdb) as source:
                    identity = abs(source.transform.a - 1.0) < 1e-9
                    if source.count != 1:
                        entry["status"] = f"{source.count} bands, a rendered image not a surface"
                        raise StopIteration
                    if source.crs is None or identity:
                        entry["status"] = "no georeference; the package carries no CRS"
                        raise StopIteration
                    grouped, scale, sample = zonal(source, basins, args.max_pixels)
                    kind = infer_kind(package["valueKind"], source, sample)
                    package["valueKind"] = kind
                    entry["valueKind"] = kind
                    if grouped is None:
                        entry["status"] = "no pixel falls inside any basin"
                        raise StopIteration
                    modes = (majority(source, basins, args.max_pixels)
                             if kind == "categorical" else {})
                    for basin_row, stats in grouped.iterrows():
                        rows.append({
                            "dataset_id": package["dataset"],
                            "atlas_number": package["atlasNumber"],
                            "basin_id": int(ids[int(basin_row) - 1]),
                            "value_kind": package["valueKind"],
                            "pixels": int(stats["count"]),
                            "mean": round(float(stats["mean"]), 6),
                            "min": round(float(stats["min"]), 6),
                            "max": round(float(stats["max"]), 6),
                            "stddev": (None if pd.isna(stats["std"])
                                       else round(float(stats["std"]), 6)),
                            "majority": (None if basin_row not in modes
                                         else float(modes[basin_row])),
                            "raster_crs": str(source.crs),
                            "distribution": package["distribution"],
                        })
                    entry.update({"status": "ok", "basins": int(len(grouped)),
                                  "crs": str(source.crs), "readScale": round(scale, 4),
                                  "pixels": source.width * source.height})
            except StopIteration:
                pass
            except Exception as error:
                entry["status"] = f"{type(error).__name__}: {error}"[:160]
            finally:
                shutil.rmtree(work, ignore_errors=True)

            report.append(entry)
            print(f"  [{index:>2}/{len(packages)}] {package['label'][:40]:<42} "
                  f"{entry.get('status', '?')[:34]:<36}{entry.get('basins', '')}")
    finally:
        shutil.rmtree(work_root, ignore_errors=True)

    output = root / "WORKSPACE" / "derived" / "basin-zonal-stats.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    columns = ["dataset_id", "atlas_number", "basin_id", "value_kind", "pixels",
               "mean", "min", "max", "stddev", "majority", "raster_crs", "distribution"]
    table = pd.DataFrame(rows, columns=columns)
    table["atlas_number"] = table["atlas_number"].astype("Int64")
    table.to_csv(output, index=False, encoding="utf-8", lineterminator="\n")

    linked = sorted({row["dataset_id"] for row in rows})
    skipped = [e for e in report if e.get("status") != "ok"]
    manifest = {
        "version": "1.0",
        "generatedAt": utc_now(),
        "predicate": "uz:hasBasinStatistic",
        "subjectType": "Dataset",
        "objectType": "Basin",
        "basinLevel": args.level,
        "basinReference": f"uzbekistan_basinatlas_v10 :: basinatlas_uz_lev{args.level:02d}",
        "basins": int(len(basins)),
        "maxPixels": args.max_pixels,
        "statistics": ["pixels", "mean", "min", "max", "stddev", "majority"],
        "note": (
            "mean and stddev describe a continuous surface; for a categorical raster read "
            "majority instead, and treat the mean of class codes as meaningless. value_kind "
            "carries which one applies. Where a raster was larger than maxPixels it was read "
            "decimated, which leaves the mean stable and can soften the extremes. In an 8-bit "
            "band that declares no nodata, 255 is treated as fill: these legends top out at 34 "
            "classes, so it is never a real value here."
        ),
        "counts": {
            "basinStatistics": len(rows),
            "datasetsLinked": len(linked),
            "packagesRead": len(packages),
            "packagesSkipped": len(skipped),
        },
        "output": str(output.relative_to(root)).replace("\\", "/"),
        "perPackage": report,
        "skipped": [{"dataset": e["dataset"], "reason": e.get("status")} for e in skipped],
    }
    write_json(root / "ONTOLOGY" / "instances" / "basin-zonal-stats.json", manifest)

    print(f"\n{len(rows):,} basin statistics across {len(linked)} datasets -> {output}")
    print(f"{len(skipped)} packages skipped; the manifest says why for each")
    return 0


if __name__ == "__main__":
    sys.exit(main())
