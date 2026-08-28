"""Convert every Uzbekistan environmental atlas package to an on-demand web layer."""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import warnings
from pathlib import Path

import geopandas as gpd
import libarchive
import matplotlib
import numpy as np
import pyogrio
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds

from inspect_packages import extract_package

warnings.filterwarnings("ignore", category=RuntimeWarning)
matplotlib.use("Agg")
from matplotlib import colormaps  # noqa: E402


MAX_VECTOR_FEATURES = 50_000
MAX_RASTER_EDGE = 1800
GIB = 1024**3


def within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def clean_work_folder(folder: Path, working_root: Path) -> None:
    if folder.exists():
        if not within(folder, working_root) or folder.resolve() == working_root.resolve():
            raise RuntimeError(f"Refusing to clean unsafe working folder: {folder}")
        shutil.rmtree(folder)


def folder_size(folder: Path) -> int:
    if not folder.exists():
        return 0
    return sum(path.stat().st_size for path in folder.rglob("*") if path.is_file())


def expanded_package_size(package: Path) -> int:
    with libarchive.file_reader(str(package)) as archive:
        return sum(max(0, int(entry.size or 0)) for entry in archive)


def atomic_manifest_write(target: Path, payload: list[dict]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f"{target.suffix}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary, target)


def dataset_item(dataset: dict, package: Path) -> dict:
    source_key = str(dataset.get("sourceKey") or "")
    source_title = Path(source_key).stem if source_key else Path(dataset.get("files", [{}])[0].get("originalName", package.stem)).stem
    match = re.match(r"(\d+)", source_title)
    return {
        "atlasNumber": int(match.group(1)) if match else None,
        "title": dataset.get("title") or source_title,
        "category": dataset.get("category") or "Other",
        "access": dataset.get("access") or "Request",
        "description": dataset.get("description") or "",
        "sourceTitle": source_title,
        "package": package.name,
    }


def first_vector(folder: Path) -> tuple[Path, str | None, dict] | None:
    for database in folder.rglob("*.gdb"):
        try:
            layers = pyogrio.list_layers(database)
            if len(layers):
                layer = str(layers[0][0])
                return database, layer, pyogrio.read_info(database, layer=layer)
        except Exception:
            pass
    for vector in [*folder.rglob("*.shp"), *folder.rglob("*.geojson"), *folder.rglob("*.gpkg")]:
        try:
            return vector, None, pyogrio.read_info(vector)
        except Exception:
            pass
    return None


def first_raster(folder: Path) -> Path | None:
    candidates = [*folder.rglob("*.tif"), *folder.rglob("*.tiff"), *folder.rglob("*.img")]
    candidates.extend(folder.rglob("*.gdb"))
    for candidate in candidates:
        try:
            with rasterio.open(candidate) as source:
                if source.count > 0 and source.width > 0 and source.height > 0:
                    return candidate
        except Exception:
            pass
    return None


def useful_fields(data: gpd.GeoDataFrame) -> list[str]:
    fields = []
    for column in data.columns:
        if column == "geometry" or column.lower().startswith("shape_"):
            continue
        sample = data[column].dropna().head(50)
        if any(isinstance(value, (bytes, bytearray, memoryview)) for value in sample):
            continue
        fields.append(column)
    preferred_words = ("name", "type", "title", "class", "label", "risk", "region", "place", "date", "year", "mag", "depth", "area", "index", "value")
    preferred = [column for column in fields if any(word in column.lower() for word in preferred_words)]
    text = [column for column in fields if data[column].dtype == "object" and column not in preferred]
    numeric = [column for column in fields if column not in preferred and column not in text]
    return (preferred + text + numeric)[:8]


def vector_layer(source_path: Path, layer: str | None, info: dict, target: Path) -> dict:
    original_count = int(info.get("features") or 0)
    data = pyogrio.read_dataframe(source_path, layer=layer, max_features=MAX_VECTOR_FEATURES)
    if data.crs is None:
        data = data.set_crs(4326)
    try:
        data = data.to_crs(4326)
    except Exception:
        data = data.set_crs(4326, allow_override=True)
    fields = useful_fields(data)
    data = data[fields + ["geometry"]]
    data = data[data.geometry.notna() & ~data.geometry.is_empty]
    geometry_types = set(data.geometry.geom_type.dropna())
    is_point = bool(geometry_types) and all(kind in {"Point", "MultiPoint"} for kind in geometry_types)
    if not is_point and len(data):
        tolerance = 200 if original_count < 500 else 500 if original_count < 5_000 else 1_000 if original_count < 30_000 else 2_000
        projected = data.to_crs(3857)
        projected.geometry = projected.geometry.simplify(tolerance, preserve_topology=True)
        data = projected.to_crs(4326)
    for column in fields:
        if str(data[column].dtype).startswith("datetime"):
            data[column] = data[column].astype(str)
    payload = data.to_json(drop_id=True, to_wgs84=True, separators=(",", ":"))
    target.write_text(payload, encoding="utf-8")
    bounds = data.total_bounds.tolist() if len(data) else [55.9, 37.1, 73.2, 45.7]
    return {
        "kind": "vector", "geometry": "point" if is_point else "shape", "url": f"/data/layers/{target.name}",
        "features": len(data), "sourceFeatures": original_count or len(data), "bounds": bounds,
        "fields": fields, "bytes": target.stat().st_size,
    }


def raster_layer(source_path: Path, target: Path) -> dict:
    with rasterio.open(source_path) as source:
        scale = min(1.0, MAX_RASTER_EDGE / max(source.width, source.height))
        width = max(1, round(source.width * scale)); height = max(1, round(source.height * scale))
        indexes = list(range(1, min(source.count, 3) + 1))
        resampling = Resampling.nearest if source.dtypes[0].startswith(("uint", "int")) else Resampling.bilinear
        values = source.read(indexes, out_shape=(len(indexes), height, width), masked=True, resampling=resampling)
        mask = np.logical_or.reduce(np.ma.getmaskarray(values), axis=0)
        if len(indexes) >= 3:
            rgb = np.moveaxis(values[:3].filled(0).astype(np.float32), 0, -1)
            for band in range(3):
                valid = rgb[..., band][~mask]
                low, high = np.percentile(valid, [2, 98]) if valid.size else (0, 1)
                rgb[..., band] = np.clip((rgb[..., band] - low) / max(high - low, 1e-9), 0, 1)
            rgba = np.dstack([(rgb * 255).astype(np.uint8), (~mask).astype(np.uint8) * 220])
            legend = {"type": "rgb"}
        else:
            band = np.asarray(values[0].data, dtype=np.float64)
            band[mask] = np.nan
            valid = band[~mask & np.isfinite(band)]
            unique = np.unique(valid) if valid.size and valid.size < 2_000_000 else np.unique(valid[:: max(1, valid.size // 500_000)])
            categorical = source.dtypes[0].startswith(("uint", "int")) and len(unique) <= 40
            if categorical:
                palette = (colormaps["turbo"](np.linspace(.05, .95, max(len(unique), 2))) * 255).astype(np.uint8)
                rgba = np.zeros((height, width, 4), dtype=np.uint8)
                for index, value in enumerate(unique):
                    rgba[band == value] = palette[index]
                rgba[..., 3] = np.where(mask | ~np.isfinite(band), 0, 205)
                legend = {"type": "categorical", "classes": [float(value) for value in unique[:40]]}
            else:
                low, high = np.percentile(valid, [2, 98]) if valid.size else (0, 1)
                normalized = np.clip((np.nan_to_num(band, nan=low) - low) / max(high - low, 1e-9), 0, 1)
                rgba = (colormaps["magma"](normalized) * 255).astype(np.uint8)
                rgba[..., 3] = np.where(mask | ~np.isfinite(band), 0, 210)
                legend = {"type": "continuous", "min": round(float(low), 3), "max": round(float(high), 3)}
        Image.fromarray(rgba, "RGBA").save(target, optimize=True, compress_level=8)
        if source.crs:
            west, south, east, north = transform_bounds(source.crs, "EPSG:4326", *source.bounds, densify_pts=21)
        else:
            west, south, east, north = source.bounds
        return {
            "kind": "raster", "url": f"/data/layers/{target.name}", "features": source.width * source.height,
            "sourceFeatures": source.width * source.height, "bounds": [west, south, east, north],
            "dimensions": [source.width, source.height], "previewDimensions": [width, height], "legend": legend,
            "bytes": target.stat().st_size,
        }


def preview_layer(folder: Path, target: Path) -> dict:
    thumbnail = next(folder.rglob("thumbnail.png"), None)
    if thumbnail:
        shutil.copy2(thumbnail, target)
        return {"kind": "preview", "url": f"/data/layers/{target.name}", "features": 0, "sourceFeatures": 0, "bytes": target.stat().st_size}
    return {"kind": "unavailable", "features": 0, "sourceFeatures": 0, "bytes": 0}


def archive_preview(package: Path, target: Path, max_bytes: int = 25 * 1024 * 1024) -> dict:
    """Extract only an embedded package thumbnail without expanding the package."""
    temporary = target.with_suffix(f"{target.suffix}.tmp")
    temporary.unlink(missing_ok=True)
    try:
        with libarchive.file_reader(str(package)) as archive:
            for entry in archive:
                if Path(entry.pathname).name.casefold() != "thumbnail.png":
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                written = 0
                with temporary.open("wb") as output:
                    for block in entry.get_blocks():
                        written += len(block)
                        if written > max_bytes:
                            raise RuntimeError("Embedded preview exceeds the 25 MiB safety limit")
                        output.write(block)
                os.replace(temporary, target)
                return {
                    "kind": "preview", "url": f"/data/layers/{target.name}",
                    "features": 0, "sourceFeatures": 0, "bytes": target.stat().st_size,
                    "note": "Preview only: expanded source package exceeds the working-storage limit.",
                }
        raise RuntimeError("Expanded package exceeds the working-storage limit and has no embedded preview")
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--catalog", type=Path, default=Path("public/data/archive-catalog.json"))
    parser.add_argument("--datasets", type=Path, default=Path("storage/datasets.json"))
    parser.add_argument("--output", type=Path, default=Path("public/data/layers"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--working", type=Path, default=Path("tmp/all-layer-build"))
    parser.add_argument("--max-output-gb", type=float, default=5.0)
    parser.add_argument("--max-package-gb", type=float, default=5.0)
    parser.add_argument("--start", type=int, default=1, help="One-based package index to start from")
    parser.add_argument("--limit", type=int, help="Maximum number of packages to process")
    args = parser.parse_args()
    if args.max_output_gb <= 0 or args.max_package_gb <= 0:
        raise SystemExit("Storage limits must be greater than zero")
    args.output.mkdir(parents=True, exist_ok=True); args.working.mkdir(parents=True, exist_ok=True)
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    by_source = {item["sourceTitle"]: item for item in catalog}
    datasets = json.loads(args.datasets.read_text(encoding="utf-8")) if args.datasets.exists() else []
    by_stored_name = {
        file["storedName"]: dataset
        for dataset in datasets
        for file in dataset.get("files", [])
        if file.get("storedName")
    }
    manifest_path = args.manifest or args.output.parent / "all-map-layers.json"
    max_output_bytes = int(args.max_output_gb * GIB)
    max_package_bytes = int(args.max_package_gb * GIB)
    output_bytes = folder_size(args.output)
    packages = sorted(args.source.glob("*.lpkx"), key=lambda item: item.name.casefold())
    partial_run = args.start != 1 or args.limit is not None
    existing_manifest = []
    if partial_run and manifest_path.exists():
        existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_by_package = {
        item["package"]: item for item in existing_manifest if item.get("package")
    }
    package_order = {package.name: index for index, package in enumerate(packages, 1)}
    manifest = list(manifest_by_package.values())
    selected = list(enumerate(packages, 1))[max(0, args.start - 1):]
    if args.limit is not None:
        selected = selected[:max(0, args.limit)]
    for position, (index, package) in enumerate(selected, 1):
        catalog_match = by_source.get(package.stem)
        dataset_match = by_stored_name.get(package.name)
        item = catalog_match.copy() if catalog_match else dataset_item(dataset_match, package) if dataset_match else {
            "atlasNumber": None, "title": package.stem, "category": "Other", "access": "Request",
            "description": "", "sourceTitle": package.stem, "package": package.name,
        }
        folder = args.working / f"package-{index:03d}"
        try:
            expanded_bytes = expanded_package_size(package)
            if expanded_bytes > max_package_bytes:
                target = args.output / f"layer-{index:03d}-preview.png"
                previous_bytes = target.stat().st_size if target.exists() else 0
                generated = archive_preview(package, target)
                generated["expandedBytes"] = expanded_bytes
                generated["workingLimitBytes"] = max_package_bytes
            else:
                clean_work_folder(folder, args.working); extract_package(package, folder)
                vector = first_vector(folder)
                if vector:
                    target = args.output / f"layer-{index:03d}.geojson"
                    previous_bytes = target.stat().st_size if target.exists() else 0
                    generated = vector_layer(*vector, target)
                else:
                    raster = first_raster(folder)
                    target = args.output / (f"layer-{index:03d}.png" if raster else f"layer-{index:03d}-preview.png")
                    previous_bytes = target.stat().st_size if target.exists() else 0
                    generated = raster_layer(raster, target) if raster else preview_layer(folder, target)
            projected_output_bytes = output_bytes - previous_bytes + generated["bytes"]
            if projected_output_bytes > max_output_bytes:
                target.unlink(missing_ok=True)
                raise RuntimeError(
                    f"Derived output would exceed the {args.max_output_gb:g} GiB store limit"
                )
            output_bytes = projected_output_bytes
            item.update(generated); item["status"] = "ready" if generated["kind"] in {"vector", "raster"} else "preview"
            item["sequence"] = index
            manifest_by_package[package.name] = item
            print(f"[{position:03d}/{len(selected)} | atlas {index:03d}/{len(packages)}] {generated['kind']:<7} {item['title']}", flush=True)
        except Exception as error:
            item.update({"kind": "error", "status": "error", "error": str(error), "features": 0, "sourceFeatures": 0, "bytes": 0})
            item["sequence"] = index
            manifest_by_package[package.name] = item
            print(f"[{position:03d}/{len(selected)} | atlas {index:03d}/{len(packages)}] ERROR   {item['title']}: {error}", flush=True)
        finally:
            clean_work_folder(folder, args.working)
        manifest = sorted(manifest_by_package.values(), key=lambda entry: package_order.get(entry.get("package"), 10**9))
        atomic_manifest_write(manifest_path, manifest)
    ready = sum(item["status"] == "ready" for item in manifest)
    previews = sum(item["status"] == "preview" for item in manifest)
    errors = sum(item["status"] == "error" for item in manifest)
    print(json.dumps({
        "total": len(manifest), "ready": ready, "previews": previews, "errors": errors,
        "outputMB": round(output_bytes / 1024 / 1024, 2),
        "outputLimitGB": args.max_output_gb, "manifest": str(manifest_path),
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
