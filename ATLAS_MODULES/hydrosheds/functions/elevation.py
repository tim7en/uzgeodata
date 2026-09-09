"""EarthEnv-DEM90 -> BasinATLAS ele_mt_sav candidate reconstruction.

Scientific choices are explicit: 5x5 mean aggregation and unweighted local
zonal mean. Rebuilt vector zones remain candidate equivalents to native zones.
Area-weighted sufficient statistics are retained for later reviewed methods.
"""
from __future__ import annotations
import math
from pathlib import Path
import shutil
import tarfile
import time

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from pyproj import CRS, Geod
from shapely.geometry import box, shape

TILE_BASE = "https://de.cyverse.org/anon-files/iplant/home/shared/earthenv_dem_data/EarthEnv-DEM90/"
CELL = 15 / 3600
ATTRIBUTES = ("ele_mt_sav",)


def tile_name(south, west):
    return f"EarthEnv-DEM90_{'N' if south >= 0 else 'S'}{abs(south):02d}{'E' if west >= 0 else 'W'}{abs(west):03d}"


def required_tiles(features):
    """Return only 5-degree tiles with a positive-area intersection with a basin."""
    tiles = set()
    for feature in features:
        geometry = shape(feature["geometry"])
        xmin, ymin, xmax, ymax = geometry.bounds
        for west in range(math.floor(xmin / 5) * 5, math.ceil(xmax / 5) * 5, 5):
            for south in range(math.floor(ymin / 5) * 5, math.ceil(ymax / 5) * 5, 5):
                if geometry.intersection(box(west, south, west + 5, south + 5)).area > 0:
                    tiles.add((south, west))
    return sorted(tiles)


def acquire_tile(south, west, cache, timer, hash_file, expected=None):
    """Download original archives atomically; verify pinned bytes on cached reruns."""
    import requests
    name = tile_name(south, west)
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / (name + ".tar.gz")
    started = time.perf_counter()
    hit = archive.exists()
    url = TILE_BASE + archive.name
    if not hit:
        partial = archive.with_suffix(archive.suffix + ".part")
        try:
            with requests.get(url, stream=True, timeout=(30, 120)) as response:
                response.raise_for_status()
                iterator = response.iter_content(1024 * 1024)
                first = next(iterator)
                if not first.startswith(b"\x1f\x8b"):
                    raise ValueError("DEM response is not gzip data (possible HTML access page)")
                size, last_update = 0, time.perf_counter()
                with partial.open("wb") as output:
                    output.write(first)
                    size += len(first)
                    for chunk in iterator:
                        output.write(chunk)
                        size += len(chunk)
                        if time.perf_counter() - last_update >= 10:
                            timer.event(f"Downloading {name}: {size / 1e6:.1f} MB")
                            last_update = time.perf_counter()
                length = response.headers.get("Content-Length")
                if length and size != int(length):
                    raise ValueError(f"Incomplete tile: {size} of {length} bytes")
            # CRC and archive structure are checked before this input is accepted.
            with tarfile.open(partial, "r:gz") as tar:
                names = [Path(member.name).name for member in tar.getmembers()]
                if name + ".bil" not in names or name + ".hdr" not in names:
                    raise ValueError("Archive lacks expected elevation grid/header")
            partial.replace(archive)
        finally:
            partial.unlink(missing_ok=True)
    digest = hash_file(archive)
    if expected and digest != expected["sha256"]:
        raise ValueError(f"Source lock mismatch for {archive.name}")
    elapsed = time.perf_counter() - started
    timer.event(f"{'Verified cache' if hit else 'Downloaded'} {name}: {archive.stat().st_size / 1e6:.1f} MB in {elapsed:.2f}s")
    return {"name": name, "url": url, "path": str(archive), "sha256": digest,
            "bytes": archive.stat().st_size, "cache_hit": hit, "wall_seconds": elapsed,
            "south": south, "west": west}


def unpack_tile(record, directory):
    """Copy regular files by basename; archive paths and links cannot escape target."""
    target = Path(directory) / record["name"]
    target.mkdir(parents=True, exist_ok=True)
    allowed = {record["name"] + suffix for suffix in (".bil", ".hdr", ".prj", ".blw")}
    with tarfile.open(record["path"], "r:gz") as archive:
        for member in archive:
            basename = Path(member.name).name
            if member.isfile() and basename in allowed:
                with archive.extractfile(member) as source, (target / basename).open("wb") as output:
                    shutil.copyfileobj(source, output)
    return target / (record["name"] + ".bil")


def aggregate_5x5(values, valid=None):
    """Return floating-point block mean and native valid-cell count (0..25)."""
    values = np.asarray(values)
    if values.ndim != 2 or any(n % 5 for n in values.shape):
        raise ValueError("Native grid shape must be divisible by five")
    valid = np.isfinite(values) if valid is None else np.asarray(valid, dtype=bool) & np.isfinite(values)
    blocks = (values.shape[0] // 5, 5, values.shape[1] // 5, 5)
    counts = valid.reshape(blocks).sum(axis=(1, 3))
    total = np.where(valid, values, 0).reshape(blocks).sum(axis=(1, 3), dtype=np.float64)
    mean = np.divide(total, counts, out=np.full(total.shape, np.nan), where=counts > 0)
    return mean, counts


def aggregate_tile(path, record):
    with rasterio.open(path) as source:
        if source.crs is None or not CRS.from_user_input(source.crs).equals(CRS.from_epsg(4326), ignore_axis_order=True):
            raise ValueError("EarthEnv source CRS must be WGS84")
        expected = from_origin(record["west"], record["south"] + 5, 3 / 3600, 3 / 3600)
        if not source.transform.almost_equals(expected, precision=1e-8) or source.shape != (6000, 6000):
            raise ValueError(f"Unexpected source grid: {source.transform}, {source.shape}")
        native = source.read(1, masked=True)
        mean, counts = aggregate_5x5(native.data, ~np.ma.getmaskarray(native))
    return mean, counts, from_origin(record["west"], record["south"] + 5, CELL, CELL)


def cell_areas(transform, height):
    """WGS84 geodesic area for each latitude row, in square meters."""
    geod = Geod(ellps="WGS84")
    west = transform.c
    east = west + transform.a
    areas = []
    for row in range(height):
        north = transform.f + row * transform.e
        south = north + transform.e
        area, _ = geod.polygon_area_perimeter([west, east, east, west], [north, north, south, south])
        areas.append(abs(area))
    return np.asarray(areas)


def make_zones(features, transform, grid_shape):
    pairs = [(feature["geometry"], index + 1) for index, feature in enumerate(features)]
    return rasterize(pairs, out_shape=grid_shape, transform=transform, fill=0, dtype="int32", all_touched=False)


def zonal_statistics(values, zones, row_areas, n_zones, native_counts=None):
    """Sufficient statistics; means are calculated only after all tiles are reduced."""
    domain = zones > 0
    valid = domain & np.isfinite(values)
    labels = zones[valid]
    count = np.bincount(labels, minlength=n_zones + 1).astype(np.int64)
    total_count = np.bincount(zones[domain], minlength=n_zones + 1).astype(np.int64)
    areas = np.broadcast_to(np.asarray(row_areas)[:, None], zones.shape)
    valid_area = np.bincount(labels, weights=areas[valid], minlength=n_zones + 1)
    total_area = np.bincount(zones[domain], weights=areas[domain], minlength=n_zones + 1)
    sums = np.bincount(labels, weights=values[valid], minlength=n_zones + 1)
    weighted = np.bincount(labels, weights=values[valid] * areas[valid], minlength=n_zones + 1)
    partial = np.zeros(n_zones + 1, dtype=np.int64)
    if native_counts is not None:
        partial = np.bincount(zones[domain & (native_counts < 25)], minlength=n_zones + 1)
    return {"valid_cells": count, "total_cells": total_count, "sum_m": sums,
            "weighted_sum_m_m2": weighted, "valid_area_m2": valid_area,
            "total_area_m2": total_area,
            "partial_native_cells": partial}


def merge_statistics(left, right):
    if left is None:
        return right
    for key in left:
        left[key] += right[key]
    return left
