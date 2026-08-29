"""Profile a folder of data someone has dropped on the project.

Answers the only questions that matter before anything is ingested: what is in
here, what is it really (measured, not claimed), and which parts does the system
already have?

For every vector file it records driver, CRS, geometry type, feature count,
fields and bounds - read from the dataset header where the format allows, so a
500 MB GeoJSON costs a scan rather than a load. For spreadsheets it records sheet
names, shape and column headers. Everything else is recorded by type and size.

The result is a JSON inventory that `ingest_external_source.py` turns into
ontology entities. Nothing is copied and nothing is converted here.

Usage:
    python PIPELINES/ontology/profile_external_source.py "C:/Users/User/Desktop/MAPS" \
        --name maps-drop-2026-08 --out ONTOLOGY/instances/external/maps-drop.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

VECTOR_SUFFIXES = {".geojson", ".shp", ".kml", ".gml"}
MULTILAYER_SUFFIXES = {".gpkg", ".gdb"}
RASTER_SUFFIXES = {".tif", ".tiff", ".img", ".asc"}
TABLE_SUFFIXES = {".xlsx", ".xls", ".csv"}
DOC_SUFFIXES = {".pdf", ".docx", ".doc", ".txt", ".md"}
ARCHIVE_SUFFIXES = {".zip", ".rar", ".7z", ".tar", ".gz"}
# Shapefile siblings: reported through the .shp, never as separate assets.
SHAPEFILE_SIDECARS = {".shx", ".dbf", ".prj", ".cpg", ".sbn", ".sbx", ".qmd", ".xml", ".qix", ".fix"}

MAX_FIELDS = 60


def sha_short(text: str, length: int = 10) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


def looks_like_geojson(path: Path) -> bool:
    """A .json file is only a vector if it says so in its first kilobyte."""
    try:
        head = path.open("rb").read(1024).decode("utf-8", "ignore")
    except OSError:
        return False
    return '"FeatureCollection"' in head or '"geometry"' in head


def classify(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in MULTILAYER_SUFFIXES:
        return "geodatabase"
    if suffix in VECTOR_SUFFIXES:
        return "vector"
    if suffix == ".json":
        return "vector" if looks_like_geojson(path) else "other"
    if suffix in RASTER_SUFFIXES:
        return "raster"
    if suffix in TABLE_SUFFIXES:
        return "table"
    if suffix in DOC_SUFFIXES:
        return "document"
    if suffix in ARCHIVE_SUFFIXES:
        return "archive"
    return "other"


def profile_vector(path: Path) -> dict:
    from pyogrio import read_info

    started = time.time()
    info = read_info(path)
    # pyogrio returns numpy arrays; `or` and `if array` raise, so test for None.
    raw_fields = info.get("fields")
    fields = [] if raw_fields is None else [str(f) for f in raw_fields]
    crs = info.get("crs")
    bounds = info.get("total_bounds")
    return {
        "driver": info.get("driver"),
        "crs": str(crs) if crs else None,
        "geometryType": str(info["geometry_type"]) if info.get("geometry_type") is not None else None,
        "features": int(info["features"]) if info.get("features") is not None else None,
        "fieldCount": len(fields),
        "fields": fields[:MAX_FIELDS],
        "bounds": [round(float(v), 6) for v in bounds] if bounds is not None else None,
        "profileSeconds": round(time.time() - started, 2),
    }


def profile_raster(path: Path) -> dict:
    import rasterio

    with rasterio.open(path) as source:
        bounds = source.bounds
        return {
            "driver": source.driver,
            "crs": str(source.crs) if source.crs else None,
            "bands": source.count,
            "dtypes": [str(d) for d in source.dtypes],
            "width": source.width,
            "height": source.height,
            "nodata": source.nodata,
            "bounds": [round(v, 6) for v in (bounds.left, bounds.bottom, bounds.right, bounds.top)],
        }


def profile_geodatabase(path: Path) -> dict:
    """A file geodatabase is one container, not the 80 binary files inside it."""
    from pyogrio import list_layers

    layers = list_layers(path)
    return {
        "layers": [{"name": str(name), "geometry": str(geometry)} for name, geometry in layers],
        "layerCount": len(layers),
    }


def profile_table(path: Path) -> dict:
    import pandas as pd

    suffix = path.suffix.lower()
    if suffix == ".csv":
        frame = pd.read_csv(path, nrows=200)
        rows = sum(1 for _ in path.open(encoding="utf-8", errors="ignore")) - 1
        return {
            "sheets": [
                {"name": path.stem, "rows": rows, "columns": len(frame.columns),
                 "header": [str(c) for c in frame.columns][:MAX_FIELDS]}
            ]
        }
    sheets = []
    try:
        book = pd.ExcelFile(path)
    except Exception as error:  # a workbook we cannot open is still worth listing
        return {"error": f"{type(error).__name__}: {error}"}
    for name in book.sheet_names[:12]:
        try:
            frame = book.parse(name, nrows=80)
        except Exception as error:
            sheets.append({"name": name, "error": f"{type(error).__name__}: {error}"})
            continue
        header = [str(c) for c in frame.columns][:MAX_FIELDS]
        sheets.append({
            "name": name,
            "rowsSampled": len(frame),
            "columns": len(frame.columns),
            "header": header,
            "sample": [str(v) for v in frame.iloc[0].tolist()[:8]] if len(frame) else [],
        })
    return {"sheets": sheets, "sheetCount": len(book.sheet_names)}


def profile_file(path: Path, root: Path, skip_slow_over_mb: float | None) -> dict:
    kind = classify(path)
    size = path.stat().st_size
    record = {
        "path": str(path.relative_to(root)).replace("\\", "/"),
        "name": path.name,
        "kind": kind,
        "suffix": path.suffix.lower(),
        "bytes": size,
        "modified": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
    }
    too_big = skip_slow_over_mb is not None and size > skip_slow_over_mb * 1024 * 1024
    try:
        if kind == "geodatabase":
            record["profile"] = profile_geodatabase(path)
        elif kind == "vector" and not too_big:
            record["profile"] = profile_vector(path)
        elif kind == "vector":
            record["profile"] = {"skipped": f"larger than {skip_slow_over_mb} MB"}
        elif kind == "raster":
            record["profile"] = profile_raster(path)
        elif kind == "table":
            record["profile"] = profile_table(path)
    except Exception as error:
        record["profile"] = {"error": f"{type(error).__name__}: {error}"}
    return record


def known_assets(repo_root: Path) -> dict[str, str]:
    """Files the project already holds, keyed by name and by size.

    Matching on size as well as name catches the same asset arriving under a
    different filename, which is how the atlas packages were stored (UUID names).
    """
    known: dict[str, str] = {}
    for registry, label in (
        ("WORKSPACE/derived/osm-layers.json", "converted to WORKSPACE/derived/osm-geojson"),
        ("WORKSPACE/derived/raster-geojson.json", "polygonised into WORKSPACE/derived/raster-geojson"),
    ):
        path = repo_root / registry
        if not path.exists():
            continue
        for entry in json.loads(path.read_text(encoding="utf-8")):
            source = entry.get("source") or entry.get("sourceRaster") or ""
            if source:
                known[Path(str(source)).name.lower()] = label

    datasets = repo_root / "WORKSPACE" / "datasets.json"
    if datasets.exists():
        for record in json.loads(datasets.read_text(encoding="utf-8")):
            for file_record in record.get("files", []):
                original = (file_record.get("originalName") or "").lower()
                if original:
                    known[original] = "in the private repository"
                known[f"size:{file_record.get('size')}"] = "in the private repository"
    return known


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path, help="folder to profile")
    parser.add_argument("--name", required=True, help="short identifier for this drop")
    parser.add_argument("--out", type=Path, help="where to write the inventory JSON")
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--skip-vector-over-mb", type=float, default=600.0,
                        help="do not scan vector files larger than this")
    parser.add_argument("--max-depth", type=int, default=8)
    args = parser.parse_args(argv)

    # Cyrillic filenames must survive a cp1251 console.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    root = args.source.resolve()
    if not root.is_dir():
        print(f"not a folder: {root}", file=sys.stderr)
        return 1
    repo_root = args.repo_root.resolve()
    known = known_assets(repo_root)

    files = []
    too_deep = []
    # Container directories are catalogued as a single asset and not walked into.
    containers = sorted(p for p in root.rglob("*")
                        if p.is_dir() and p.suffix.lower() == ".gdb" and any(p.glob("*.gdbtable")))
    for container in containers:
        size = sum(p.stat().st_size for p in container.rglob("*") if p.is_file())
        record = {
            "path": str(container.relative_to(root)).replace("\\", "/"),
            "name": container.name,
            "kind": "geodatabase",
            "suffix": ".gdb",
            "bytes": size,
            "modified": datetime.fromtimestamp(container.stat().st_mtime, timezone.utc).isoformat(),
        }
        try:
            record["profile"] = profile_geodatabase(container)
        except Exception as error:
            record["profile"] = {"error": f"{type(error).__name__}: {error}"}
        record["alreadyHeld"] = None
        files.append(record)
        layers = (record.get("profile") or {}).get("layerCount")
        print(f"  NEW  {size / 1e6:8.1f} MB  {record['path'][:64]:66s} "
              f"{layers if layers is not None else ''} layer(s)")

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(parent in containers for parent in path.parents):
            continue
        if len(path.relative_to(root).parts) > args.max_depth:
            # Recorded, not silently dropped: a delivery that nests deeper than
            # expected must not disappear from the inventory without saying so.
            too_deep.append(str(path.relative_to(root)).replace("\\", "/"))
            continue
        if path.suffix.lower() in SHAPEFILE_SIDECARS and path.with_suffix(".shp").exists():
            continue
        record = profile_file(path, root, args.skip_vector_over_mb)
        match = known.get(path.name.lower()) or known.get(f"size:{path.stat().st_size}")
        record["alreadyHeld"] = match
        files.append(record)
        status = "held" if match else "NEW "
        detail = ""
        profile = record.get("profile") or {}
        if profile.get("features") is not None:
            detail = f"{profile['features']:,} features, {profile.get('geometryType')}"
        elif profile.get("sheets"):
            detail = f"{profile.get('sheetCount', len(profile['sheets']))} sheet(s)"
        elif profile.get("error"):
            detail = profile["error"][:60]
        print(f"  {status} {record['bytes'] / 1e6:8.1f} MB  {record['path'][:64]:66s} {detail}")

    inventory = {
        "version": "1.0",
        "name": args.name,
        "source": str(root),
        "profiledAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "fingerprint": sha_short(str(root)),
        "counts": {
            "files": len(files),
            "new": sum(1 for f in files if not f["alreadyHeld"]),
            "bytes": sum(f["bytes"] for f in files),
        },
        "skippedTooDeep": too_deep,
        "byKind": {
            kind: sum(1 for f in files if f["kind"] == kind)
            for kind in sorted({f["kind"] for f in files})
        },
        "files": files,
    }

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(inventory, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        print(f"\nwrote {args.out}")
    if too_deep:
        print(f"{len(too_deep)} files below the depth limit were NOT profiled, "
              f"e.g. {too_deep[0]}")
    counts = inventory["counts"]
    print(f"{counts['files']} files, {counts['new']} not held by the project, "
          f"{counts['bytes'] / 1e9:.2f} GB")
    print("by kind: " + ", ".join(f"{k} {v}" for k, v in inventory["byKind"].items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
