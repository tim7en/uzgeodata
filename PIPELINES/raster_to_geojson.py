"""Convert GeoTIFF rasters (including TIFFs inside LPKX files) to stored GeoJSON.

The converter is intentionally conservative: it downsamples very large rasters,
bins continuous values before polygonizing them, writes atomically, and enforces
an aggregate quota for the derived-data directory. The default quota is 5 GiB.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterator

import libarchive
import numpy as np
import rasterio
from affine import Affine
from rasterio import features
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds, transform_geom


GIB = 1024**3
DEFAULT_STORE_LIMIT = 5 * GIB
DEFAULT_MAX_PIXELS = 2_000_000
DEFAULT_MAX_FEATURES = 500_000
TIFF_SUFFIXES = {".tif", ".tiff"}


class QuotaExceeded(RuntimeError):
    """Raised before a derived output would exceed its configured quota."""


class FeatureLimitExceeded(RuntimeError):
    """Raised when raster polygonization produces an unsafe feature count."""


def folder_size(folder: Path) -> int:
    if not folder.exists():
        return 0
    return sum(path.stat().st_size for path in folder.rglob("*") if path.is_file())


def atomic_json_write(target: Path, payload: object) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f"{target.suffix}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, target)


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug[:70] or "raster"


def output_name(source_label: str, raster_name: str) -> str:
    identity = f"{source_label}|{raster_name}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:10]
    return f"{safe_slug(Path(source_label).stem)}-{safe_slug(Path(raster_name).stem)}-{digest}.geojson"


def reduced_dimensions(width: int, height: int, max_pixels: int) -> tuple[int, int]:
    if max_pixels <= 0 or width * height <= max_pixels:
        return width, height
    scale = math.sqrt(max_pixels / (width * height))
    return max(1, int(width * scale)), max(1, int(height * scale))


def classify_values(
    data: np.ma.MaskedArray,
    mode: str,
    bins: int,
    max_categories: int,
) -> tuple[np.ndarray, np.ndarray, str, list[dict]]:
    raw = np.asarray(data.data)
    mask = ~np.ma.getmaskarray(data) & np.isfinite(raw)
    valid = np.asarray(raw[mask])
    if not valid.size:
        raise ValueError("Raster band contains no valid pixels")

    unique = np.unique(valid)
    integer_values = np.issubdtype(data.dtype, np.integer) or np.all(np.equal(valid, np.floor(valid)))
    categorical = mode == "yes" or (mode == "auto" and integer_values and len(unique) <= max_categories)

    classified = np.full(data.shape, -1, dtype=np.int32)
    if categorical:
        if len(unique) > max_categories and mode != "yes":
            categorical = False
        else:
            classified[mask] = np.searchsorted(unique, valid).astype(np.int32)
            classes = [
                {"class_id": index, "value": float(value)}
                for index, value in enumerate(unique)
            ]
            return classified, mask, "categorical", classes

    bin_count = max(2, min(int(bins), 256))
    low = float(np.min(valid))
    high = float(np.max(valid))
    if math.isclose(low, high):
        classified[mask] = 0
        return classified, mask, "continuous", [{"class_id": 0, "min": low, "max": high}]

    edges = np.unique(np.quantile(valid.astype(np.float64), np.linspace(0, 1, bin_count + 1)))
    if len(edges) < 2:
        edges = np.array([low, high], dtype=np.float64)
    classified[mask] = np.clip(np.digitize(valid, edges[1:-1], right=False), 0, len(edges) - 2)
    classes = [
        {"class_id": index, "min": float(edges[index]), "max": float(edges[index + 1])}
        for index in range(len(edges) - 1)
    ]
    return classified, mask, "continuous", classes


def write_piece(output, payload: bytes, written: int, byte_limit: int) -> int:
    if written + len(payload) > byte_limit:
        raise QuotaExceeded(
            f"GeoJSON would exceed the remaining derived-store quota "
            f"({byte_limit / GIB:.2f} GiB available)"
        )
    output.write(payload)
    return written + len(payload)


def vectorize_raster(
    raster_path: Path,
    target: Path,
    source_label: str,
    byte_limit: int,
    band: int,
    max_pixels: int,
    max_features: int,
    bins: int,
    categorical: str,
    max_categories: int,
    source_crs: str | None,
) -> dict:
    temporary = target.with_suffix(f"{target.suffix}.tmp")
    temporary.unlink(missing_ok=True)
    try:
        with rasterio.open(raster_path) as source:
            if band < 1 or band > source.count:
                raise ValueError(f"Band {band} does not exist; raster has {source.count} band(s)")
            crs = source_crs or source.crs
            if not crs:
                raise ValueError("Raster has no CRS; pass --source-crs (for example EPSG:4326)")

            width, height = reduced_dimensions(source.width, source.height, max_pixels)
            output_transform = source.transform * Affine.scale(source.width / width, source.height / height)
            sampled = source.read(
                band,
                out_shape=(height, width),
                masked=True,
                resampling=Resampling.nearest,
            )
            classified, valid_mask, value_type, classes = classify_values(
                sampled, categorical, bins, max_categories
            )
            if value_type == "continuous" and (width, height) != (source.width, source.height):
                sampled = source.read(
                    band,
                    out_shape=(height, width),
                    masked=True,
                    resampling=Resampling.bilinear,
                )
                classified, valid_mask, value_type, classes = classify_values(
                    sampled, "no", bins, max_categories
                )

            west, south, east, north = transform_bounds(
                crs, "EPSG:4326", *source.bounds, densify_pts=21
            )
            metadata = {
                "source": source_label,
                "raster": raster_path.name,
                "band": band,
                "source_crs": str(crs),
                "source_dimensions": [source.width, source.height],
                "processed_dimensions": [width, height],
                "value_type": value_type,
                "classes": classes,
                "bbox": [west, south, east, north],
            }

            target.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            feature_count = 0
            with temporary.open("wb") as output:
                prefix = json.dumps(
                    {"type": "FeatureCollection", "metadata": metadata},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )[:-1].encode("utf-8") + b',"features":['
                written = write_piece(output, prefix, written, byte_limit)

                class_lookup = {item["class_id"]: item for item in classes}
                for geometry, class_value in features.shapes(
                    classified,
                    mask=valid_mask,
                    transform=output_transform,
                    connectivity=8,
                ):
                    feature_count += 1
                    if max_features > 0 and feature_count > max_features:
                        raise FeatureLimitExceeded(
                            f"Raster produced more than {max_features:,} polygons; "
                            "reduce --max-pixels or --bins"
                        )
                    class_id = int(class_value)
                    geometry = transform_geom(crs, "EPSG:4326", geometry, precision=6)
                    properties = class_lookup[class_id].copy()
                    feature = {
                        "type": "Feature",
                        "properties": properties,
                        "geometry": geometry,
                    }
                    encoded = json.dumps(feature, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                    if feature_count > 1:
                        encoded = b"," + encoded
                    written = write_piece(output, encoded, written, byte_limit)
                written = write_piece(output, b"]}", written, byte_limit)

        os.replace(temporary, target)
        return {
            "id": target.stem,
            "source": source_label,
            "sourceRaster": raster_path.name,
            "storedName": target.name,
            "path": str(target),
            "bytes": target.stat().st_size,
            "features": feature_count,
            "band": band,
            "valueType": value_type,
            "classes": len(classes),
            "bounds": [west, south, east, north],
            "sourceDimensions": [source.width, source.height],
            "processedDimensions": [width, height],
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def supported_files_in_directory(folder: Path) -> Iterator[Path]:
    suffixes = TIFF_SUFFIXES | {".lpkx"}
    yield from sorted(
        (path for path in folder.rglob("*") if path.is_file() and path.suffix.casefold() in suffixes),
        key=lambda path: str(path).casefold(),
    )


def extract_lpkx_tiffs(package: Path, destination: Path, max_temp_bytes: int) -> list[tuple[Path, str]]:
    extracted: list[tuple[Path, str]] = []
    total = 0
    with libarchive.file_reader(str(package)) as archive:
        for entry in archive:
            member = PurePosixPath(entry.pathname)
            if entry.isdir or member.suffix.casefold() not in TIFF_SUFFIXES:
                continue
            total += max(0, int(entry.size or 0))
            if total > max_temp_bytes:
                raise QuotaExceeded(
                    f"TIFF members in {package.name} exceed the temporary extraction limit "
                    f"of {max_temp_bytes / GIB:.2f} GiB"
                )
            digest = hashlib.sha256(entry.pathname.encode("utf-8")).hexdigest()[:10]
            target = destination / f"{safe_slug(member.stem)}-{digest}{member.suffix.casefold()}"
            with target.open("wb") as output:
                actual = 0
                for block in entry.get_blocks():
                    actual += len(block)
                    if actual > max_temp_bytes or total - int(entry.size or 0) + actual > max_temp_bytes:
                        raise QuotaExceeded("Temporary TIFF extraction exceeded its configured limit")
                    output.write(block)
            extracted.append((target, entry.pathname))
    return extracted


def load_registry(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Registry must contain a JSON array: {path}")
    return payload


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Polygonize TIFF rasters into quota-limited GeoJSON files.",
        epilog=(
            "Examples:\n"
            "  python PIPELINES/raster_to_geojson.py map.tif\n"
            "  python PIPELINES/raster_to_geojson.py atlas.lpkx --max-store-gb 5 --max-pixels 1000000\n"
            "  python PIPELINES/raster_to_geojson.py rasters/ --categorical yes --overwrite"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    result.add_argument("sources", nargs="+", type=Path, help="TIFF, LPKX, or directory containing either")
    result.add_argument("--output", type=Path, default=Path("WORKSPACE/derived/raster-geojson"))
    result.add_argument("--registry", type=Path, default=Path("WORKSPACE/derived/raster-geojson.json"))
    result.add_argument("--max-store-gb", type=float, default=5.0, help="Aggregate output quota in GiB")
    result.add_argument("--max-temp-gb", type=float, default=5.0, help="LPKX TIFF extraction limit in GiB")
    result.add_argument("--max-pixels", type=int, default=DEFAULT_MAX_PIXELS)
    result.add_argument("--max-features", type=int, default=DEFAULT_MAX_FEATURES)
    result.add_argument("--band", type=int, default=1)
    result.add_argument("--bins", type=int, default=24, help="Quantile bins for continuous rasters")
    result.add_argument("--categorical", choices=("auto", "yes", "no"), default="auto")
    result.add_argument("--max-categories", type=int, default=64)
    result.add_argument("--source-crs", help="CRS override for rasters without CRS")
    result.add_argument("--overwrite", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    max_store_bytes = int(args.max_store_gb * GIB)
    max_temp_bytes = int(args.max_temp_gb * GIB)
    if max_store_bytes <= 0 or max_temp_bytes <= 0:
        raise SystemExit("Storage and temporary limits must be greater than zero")
    if args.max_pixels <= 0 or args.bins < 2 or args.max_categories < 2:
        raise SystemExit("--max-pixels must be positive; --bins and --max-categories must be at least 2")

    output_root = args.output.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    registry = load_registry(args.registry)
    registry_by_id = {entry["id"]: entry for entry in registry}
    used_bytes = folder_size(output_root)
    converted = skipped = failed = 0

    def convert(path: Path, source_label: str, raster_label: str) -> None:
        nonlocal used_bytes, converted, skipped, failed
        target = output_root / output_name(source_label, raster_label)
        target.with_suffix(f"{target.suffix}.tmp").unlink(missing_ok=True)
        used_bytes = folder_size(output_root)
        previous_bytes = target.stat().st_size if target.exists() else 0
        if target.exists() and not args.overwrite:
            print(f"SKIP  {raster_label}: {target.name} already exists", flush=True)
            skipped += 1
            return
        available = max_store_bytes - (used_bytes - previous_bytes)
        if available <= 0:
            print(f"ERROR {raster_label}: derived store has reached its {args.max_store_gb:g} GiB quota", flush=True)
            failed += 1
            return
        try:
            entry = vectorize_raster(
                path, target, source_label, available, args.band, args.max_pixels,
                args.max_features, args.bins, args.categorical, args.max_categories,
                args.source_crs,
            )
            used_bytes = folder_size(output_root)
            registry_by_id[entry["id"]] = entry
            atomic_json_write(args.registry, sorted(registry_by_id.values(), key=lambda item: item["id"]))
            converted += 1
            print(
                f"OK    {raster_label}: {entry['features']:,} features, "
                f"{entry['bytes'] / 1024 / 1024:.2f} MiB -> {target}",
                flush=True,
            )
        except Exception as error:
            failed += 1
            print(f"ERROR {raster_label}: {error}", flush=True)

    def convert_package(package: Path, source_label: str) -> None:
        nonlocal skipped, failed
        try:
            with tempfile.TemporaryDirectory(prefix="uzg-raster-") as temporary:
                rasters = extract_lpkx_tiffs(package, Path(temporary), max_temp_bytes)
                if not rasters:
                    print(f"SKIP  {source_label}: no TIFF members found", flush=True)
                    skipped += 1
                for raster, member_name in rasters:
                    convert(raster, source_label, member_name)
        except Exception as error:
            print(f"ERROR {source_label}: {error}", flush=True)
            failed += 1

    for raw_source in args.sources:
        source = raw_source.resolve()
        if not source.exists():
            print(f"ERROR {raw_source}: source does not exist", flush=True)
            failed += 1
            continue
        if source.is_dir():
            inputs = list(supported_files_in_directory(source))
            if not inputs:
                print(f"SKIP  {source}: no TIFF or LPKX files found", flush=True)
                skipped += 1
            for item in inputs:
                relative_name = str(item.relative_to(source))
                if item.suffix.casefold() == ".lpkx":
                    convert_package(item, relative_name)
                else:
                    convert(item, source.name, relative_name)
        elif source.suffix.casefold() in TIFF_SUFFIXES:
            convert(source, source.name, source.name)
        elif source.suffix.casefold() == ".lpkx":
            convert_package(source, source.name)
        else:
            print(f"ERROR {source}: expected a TIFF, LPKX, or directory", flush=True)
            failed += 1

    summary = {
        "converted": converted,
        "skipped": skipped,
        "failed": failed,
        "storedBytes": used_bytes,
        "storeLimitBytes": max_store_bytes,
        "remainingBytes": max(0, max_store_bytes - used_bytes),
        "output": str(output_root),
        "registry": str(args.registry.resolve()),
    }
    print(json.dumps(summary, indent=2), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
