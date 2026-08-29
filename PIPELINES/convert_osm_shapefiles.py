"""Convert the supplied OpenStreetMap shapefiles into validated GeoJSON layers."""
from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from shapely import make_valid


GIB = 1024**3
SOURCE_DATE = "2014-09-03T20:22:02Z"
LICENSE = "Open Database License 1.0 (ODbL)"
STANDARD_LAYERS = ("buildings", "waterways", "railways", "landuse", "natural", "places", "points")
WATER_TYPES = {
    "natural": {"water", "riverbank"},
    "landuse": {"reservoir", "basin"},
}


class QuotaExceeded(RuntimeError):
    """Raised when a generated layer would exceed the derived-store quota."""


def folder_size(folder: Path) -> int:
    if not folder.exists():
        return 0
    return sum(path.stat().st_size for path in folder.rglob("*") if path.is_file())


def json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def atomic_json_write(target: Path, payload: object) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f"{target.suffix}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    os.replace(temporary, target)


def read_layer(source: Path) -> tuple[gpd.GeoDataFrame, int]:
    data = pyogrio.read_dataframe(source)
    if data.crs is None:
        raise ValueError(f"Source has no CRS: {source}")
    data = data.to_crs(4326)
    data = data[data.geometry.notna() & ~data.geometry.is_empty].copy()
    invalid = ~data.geometry.is_valid
    repaired = int(invalid.sum())
    if repaired:
        data.loc[invalid, "geometry"] = data.loc[invalid, "geometry"].map(make_valid)
        data = data[data.geometry.notna() & ~data.geometry.is_empty & data.geometry.is_valid].copy()
    return data, repaired


def write_geojson(
    target: Path,
    data: gpd.GeoDataFrame,
    metadata: dict,
    available_bytes: int,
) -> int:
    temporary = target.with_suffix(f"{target.suffix}.tmp")
    temporary.unlink(missing_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    written = 0

    def append(output, payload: bytes) -> None:
        nonlocal written
        if written + len(payload) > available_bytes:
            raise QuotaExceeded(
                f"{target.name} would exceed the remaining derived-store quota "
                f"({available_bytes / GIB:.2f} GiB available)"
            )
        output.write(payload)
        written += len(payload)

    try:
        with temporary.open("wb") as output:
            prefix = json.dumps(
                {"type": "FeatureCollection", "metadata": metadata},
                ensure_ascii=False,
                separators=(",", ":"),
                default=json_default,
            )[:-1].encode("utf-8") + b',"features":['
            append(output, prefix)
            for index, feature in enumerate(data.iterfeatures(drop_id=True, na="null")):
                encoded = json.dumps(
                    feature,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    default=json_default,
                ).encode("utf-8")
                append(output, (b"," if index else b"") + encoded)
            append(output, b"]}")
        os.replace(temporary, target)
        return target.stat().st_size
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def layer_metadata(name: str, source: str, data: gpd.GeoDataFrame, repaired: int) -> dict:
    bounds = [float(value) for value in data.total_bounds] if len(data) else []
    geometry_types = sorted(set(data.geometry.geom_type.dropna()))
    return {
        "name": name,
        "source": source,
        "source_date": SOURCE_DATE,
        "license": LICENSE,
        "crs": "EPSG:4326",
        "features": len(data),
        "geometry_types": geometry_types,
        "bounds": bounds,
        "invalid_geometries_repaired": repaired,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert OSM shapefiles to quota-controlled GeoJSON.")
    parser.add_argument("source", type=Path, help="Folder containing buildings/, waterways/, etc.")
    parser.add_argument("--output", type=Path, default=Path("WORKSPACE/derived/osm-geojson"))
    parser.add_argument("--manifest", type=Path, default=Path("WORKSPACE/derived/osm-layers.json"))
    parser.add_argument("--quota-root", type=Path, default=Path("WORKSPACE/derived"))
    parser.add_argument("--max-store-gb", type=float, default=5.0)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.max_store_gb <= 0:
        raise SystemExit("--max-store-gb must be greater than zero")

    source_root = args.source.resolve()
    output_root = args.output.resolve()
    quota_root = args.quota_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    quota_root.mkdir(parents=True, exist_ok=True)
    max_store_bytes = int(args.max_store_gb * GIB)
    manifest: list[dict] = []
    loaded: dict[str, tuple[gpd.GeoDataFrame, int, Path]] = {}

    for name in STANDARD_LAYERS:
        source = source_root / name / f"{name}.shp"
        if not source.exists():
            print(f"SKIP  {name}: source shapefile not found", flush=True)
            continue
        data, repaired = read_layer(source)
        loaded[name] = (data, repaired, source)
        target = output_root / f"{name}.geojson"
        previous_bytes = target.stat().st_size if target.exists() else 0
        if target.exists() and not args.overwrite:
            print(f"SKIP  {name}: {target.name} already exists", flush=True)
            continue
        available = max_store_bytes - (folder_size(quota_root) - previous_bytes)
        metadata = layer_metadata(name, str(source.relative_to(source_root)), data, repaired)
        size = write_geojson(target, data, metadata, available)
        entry = {**metadata, "stored_name": target.name, "bytes": size}
        manifest.append(entry)
        print(f"OK    {name}: {len(data):,} features, {size / 1024 / 1024:.2f} MiB", flush=True)

    water_frames = []
    repaired_total = 0
    water_sources = []
    for source_name, accepted_types in WATER_TYPES.items():
        if source_name not in loaded:
            continue
        data, repaired, source = loaded[source_name]
        selected = data[data["type"].isin(accepted_types)].copy()
        selected["source_layer"] = source_name
        water_frames.append(selected)
        repaired_total += repaired
        water_sources.append(str(source.relative_to(source_root)))
    if water_frames:
        water = gpd.GeoDataFrame(
            pd.concat(water_frames, ignore_index=True),
            geometry="geometry",
            crs="EPSG:4326",
        )
        target = output_root / "water-bodies.geojson"
        previous_bytes = target.stat().st_size if target.exists() else 0
        if not target.exists() or args.overwrite:
            available = max_store_bytes - (folder_size(quota_root) - previous_bytes)
            metadata = layer_metadata("water-bodies", ", ".join(water_sources), water, repaired_total)
            metadata["filter"] = {name: sorted(types) for name, types in WATER_TYPES.items()}
            size = write_geojson(target, water, metadata, available)
            manifest.append({**metadata, "stored_name": target.name, "bytes": size})
            print(f"OK    water-bodies: {len(water):,} features, {size / 1024 / 1024:.2f} MiB", flush=True)
        else:
            print(f"SKIP  water-bodies: {target.name} already exists", flush=True)

    existing = []
    if args.manifest.exists() and not args.overwrite:
        existing = json.loads(args.manifest.read_text(encoding="utf-8"))
    by_name = {item["name"]: item for item in existing}
    by_name.update({item["name"]: item for item in manifest})
    final_manifest = sorted(by_name.values(), key=lambda item: item["name"])
    atomic_json_write(args.manifest, final_manifest)
    stored_bytes = folder_size(quota_root)
    print(json.dumps({
        "layers": len(final_manifest),
        "features": sum(item["features"] for item in final_manifest),
        "derivedStoreBytes": stored_bytes,
        "derivedStoreLimitBytes": max_store_bytes,
        "remainingBytes": max(0, max_store_bytes - stored_bytes),
        "output": str(output_root),
        "manifest": str(args.manifest.resolve()),
    }, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
