"""Convert every Uzbekistan environmental atlas package to an on-demand web layer."""
from __future__ import annotations

import argparse
import json
import math
import shutil
import warnings
from pathlib import Path

import geopandas as gpd
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
    fields = [column for column in data.columns if column != "geometry" and not column.lower().startswith("shape_")]
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
            band = values[0].filled(np.nan).astype(np.float64)
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--catalog", type=Path, default=Path("public/data/archive-catalog.json"))
    parser.add_argument("--output", type=Path, default=Path("public/data/layers"))
    parser.add_argument("--working", type=Path, default=Path("tmp/all-layer-build"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True); args.working.mkdir(parents=True, exist_ok=True)
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    by_source = {item["sourceTitle"]: item for item in catalog}
    manifest = []
    packages = sorted(args.source.glob("*.lpkx"), key=lambda item: item.name.casefold())
    for index, package in enumerate(packages, 1):
        item = by_source[package.stem].copy(); folder = args.working / f"package-{index:03d}"
        try:
            clean_work_folder(folder, args.working); extract_package(package, folder)
            vector = first_vector(folder)
            if vector:
                generated = vector_layer(*vector, args.output / f"layer-{index:03d}.geojson")
            else:
                raster = first_raster(folder)
                generated = raster_layer(raster, args.output / f"layer-{index:03d}.png") if raster else preview_layer(folder, args.output / f"layer-{index:03d}-preview.png")
            item.update(generated); item["status"] = "ready" if generated["kind"] in {"vector", "raster"} else "preview"
            manifest.append(item)
            print(f"[{index:03d}/{len(packages)}] {generated['kind']:<7} {item['title']}", flush=True)
        except Exception as error:
            item.update({"kind": "error", "status": "error", "error": str(error), "features": 0, "sourceFeatures": 0, "bytes": 0})
            manifest.append(item); print(f"[{index:03d}/{len(packages)}] ERROR   {item['title']}: {error}", flush=True)
        finally:
            clean_work_folder(folder, args.working)
        (args.output.parent / "all-map-layers.json").write_text(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    ready = sum(item["status"] == "ready" for item in manifest)
    print(json.dumps({"total": len(manifest), "ready": ready, "errors": len(manifest) - ready, "outputMB": round(sum(item["bytes"] for item in manifest) / 1024 / 1024, 2)}, indent=2), flush=True)


if __name__ == "__main__":
    main()
