"""Small-domain source adapters and numeric kernels for Pskem atlas candidates.

Reference imports are handled separately by the runner. This module never uses
reference attribute values to reconstruct an attribute.
"""
from __future__ import annotations
from collections import defaultdict
import json
import math
from pathlib import Path
import re
import time

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.features import rasterize
from rasterio.enums import MergeAlg
from shapely.geometry import shape
from shapely.ops import unary_union

from ATLAS_MODULES.core.runtime import sha256, write_json, utc_now
from ATLAS_MODULES.core.zonal import grouped_statistics, parts_by_id
from ATLAS_MODULES.hydrosheds.functions.elevation import (
    CELL, acquire_tile, unpack_tile, aggregate_tile, cell_areas, required_tiles)


def physical_encoding(column, stored_unit):
    """A reversible conversion; retain raw values and original units alongside it."""
    multiplier = re.search(r"\(x(\d+)\)", stored_unit)
    factor = 1 / int(multiplier.group(1)) if multiplier else 1.0
    unit = re.sub(r"\s*\(x\d+\)", "", stored_unit)
    if column.startswith("pop_ct_"):
        factor, unit = 1000.0, "people"
    elif "million cubic meters" in stored_unit:
        factor, unit = 1_000_000.0, "cubic meters"
    elif "thousand cubic meters" in stored_unit:
        factor, unit = 1000.0, "cubic meters"
    return factor, unit


def clean_value(value):
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number) or number == -9999:
        return None
    return number


def upstream_members(features, full_routing):
    """Validate the pilot is upstream-closed, then trace unique local units."""
    ids = {str(int(f["properties"]["HYBAS_ID"])) for f in features}
    incoming = defaultdict(list)
    for row in full_routing:
        bid = str(int(float(row["hybas_id"])))
        down = str(int(float(row["next_down"])))
        if down in ids and bid not in ids:
            raise ValueError(f"Pilot omits contributing basin {bid} -> {down}")
    for f in features:
        bid = str(int(f["properties"]["HYBAS_ID"]))
        down = str(int(f["properties"]["NEXT_DOWN"]))
        if down in ids:
            incoming[down].append(bid)
    result = {}
    for outlet in ids:
        seen, stack = set(), [outlet]
        while stack:
            bid = stack.pop()
            if bid in seen:
                raise ValueError("Cycle or repeated contribution in pilot routing")
            seen.add(bid)
            stack.extend(incoming[bid])
        result[outlet] = seen
    return result


def zones_for(features, transform, dimensions):
    zones = rasterize([(f["geometry"], i + 1) for i, f in enumerate(features)],
                      out_shape=dimensions, transform=transform, fill=0, dtype="int32", all_touched=False)
    overlaps = rasterize([(f["geometry"], 1) for f in features], out_shape=dimensions,
                         transform=transform, fill=0, dtype="uint16", all_touched=False, merge_alg=MergeAlg.add)
    if np.any(overlaps > 1):
        raise ValueError("Overlapping native-polygon zones at cell centers")
    return zones


def reduce_field(values, features, zones, areas, members, support, statistic="mean"):
    """Local arithmetic mean/extrema or upstream cell-area-weighted mean."""
    ids = [str(int(f["properties"]["HYBAS_ID"])) for f in features]
    local = parts_by_id(grouped_statistics(values, zones, areas, len(ids), extremes=True),
                        ids, extremes=True)
    result = {}
    for bid in ids:
        selected = [local[key] for key in sorted(members[bid])] if support == "u" else [local[bid]]
        valid = sum(r["count"] for r in selected)
        expected = sum(r["expected"] for r in selected)
        if not valid:
            value = None
        elif support == "u":
            total_area = sum(r["area"] for r in selected)
            value = sum(r["weighted"] for r in selected) / total_area if total_area else None
        elif statistic == "minimum":
            value = selected[0]["minimum"]
        elif statistic == "maximum":
            value = selected[0]["maximum"]
        else:
            value = selected[0]["sum"] / valid
        result[bid] = {"raw_value": value, "valid_cells": valid, "expected_cells": expected,
                       "coverage_fraction": valid / expected if expected else 0.0,
                       "support_basin_count": len(selected)}
    return result


def climate_fields(monthly):
    """Period reduction precedes spatial reduction; temperature extremes use tavg."""
    fields = {}
    for variable in ("tmp", "pre"):
        stack = np.stack([monthly[f"{variable}_{m:02d}"] for m in range(1, 13)])
        for m in range(1, 13):
            fields[f"{variable}_{'dc' if variable == 'tmp' else 'mm'}_s{m:02d}"] = stack[m - 1]
        annual = stack.mean(axis=0) if variable == "tmp" else stack.sum(axis=0)
        for support in ("s", "u"):
            fields[f"{variable}_{'dc' if variable == 'tmp' else 'mm'}_{support}yr"] = annual
        if variable == "tmp":
            fields["tmp_dc_smn"] = stack.min(axis=0)
            fields["tmp_dc_smx"] = stack.max(axis=0)
    return fields


def worldclim_source(features, cache, timer, offline=False):
    """Small original-V1 candidate subset; mask encoded explicitly, no live URL logged."""
    import requests
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    path, metadata_path = cache / "monthly-15s-v2.tif", cache / "source-v2.json"
    bounds = unary_union([shape(f["geometry"]) for f in features]).bounds
    west, south = [math.floor(bounds[i] / CELL) * CELL for i in (0, 1)]
    east, north = [math.ceil(bounds[i] / CELL) * CELL for i in (2, 3)]
    transform = [CELL, 0, west, 0, -CELL, north]
    order = [f"{v}_{m:02d}" for m in range(1, 13) for v in ("tmp", "pre")]
    if path.exists() and metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata["sha256"] != sha256(path) or metadata["transform"] != transform:
            raise ValueError("WorldClim cache content or pilot grid changed")
        timer.event("Verified cached WorldClim V1 pilot raster")
    else:
        if offline:
            raise FileNotFoundError("WorldClim V1 pilot raster is not cached")
        import ee
        ee.Initialize(project="ee-sabitovty")
        collection = ee.ImageCollection("WORLDCLIM/V1/MONTHLY")
        months = sorted(collection.aggregate_array("month").getInfo())
        if months != list(range(1, 13)):
            raise ValueError("WorldClim source lacks 12 unique calendar months")
        source_metadata = collection.first().getInfo()
        bands = []
        for m in range(1, 13):
            image = ee.Image(collection.filter(ee.Filter.eq("month", m)).first())
            bands.extend([image.select("tavg").rename(f"tmp_{m:02d}"), image.select("prec").rename(f"pre_{m:02d}")])
        image = ee.Image.cat(bands).unmask(-32768).toInt16()
        url = image.getDownloadURL({"crs": "EPSG:4326", "crs_transform": transform,
                                   "dimensions": [round((east-west)/CELL), round((north-south)/CELL)],
                                   "format": "GEO_TIFF", "filePerBand": False})
        response = requests.get(url, timeout=(30, 120))
        response.raise_for_status()
        temporary = path.with_suffix(".part.tif")
        temporary.write_bytes(response.content)
        with rasterio.open(temporary) as source:
            if source.count != 24:
                raise ValueError("WorldClim export must contain 24 bands")
        temporary.replace(path)
        metadata = {"asset": "WORLDCLIM/V1/MONTHLY", "sha256": sha256(path), "retrieved_at": utc_now(),
                    "transform": transform, "band_order": order, "nodata": -32768,
                    "source_metadata": source_metadata, "resampling": "nearest neighbor to aligned 15 arc-second grid",
                    "licence": "CC-BY-SA-4.0", "source_catalogue": "https://developers.google.com/earth-engine/datasets/catalog/WORLDCLIM_V1_MONTHLY",
                    "source_equivalence": "WorldClim V1 mirror; exact v1.4 vintage equivalence requires review"}
        write_json(metadata_path, metadata)
        timer.event(f"Downloaded masked WorldClim V1 subset: {len(response.content):,} bytes")
    with rasterio.open(path) as source:
        arrays = source.read().astype("float64")
        arrays[arrays == -32768] = np.nan
        output_transform = source.transform
    return {key: arrays[i] for i, key in enumerate(order)}, output_transform, metadata, path


def elevation_source(features, cache, workdir, timer):
    tiles = required_tiles(features)
    if tiles != [(40, 70)]:
        raise ValueError("This adapter is restricted to the Pskem single-tile footprint")
    record = acquire_tile(40, 70, cache, timer, sha256)
    native = unpack_tile(record, Path(workdir) / "native")
    values, counts, transform = aggregate_tile(native, record)
    # Do not silently apply incomplete 5x5 native support to a baseline candidate.
    values[counts != 25] = np.nan
    return values, transform, record


def compare_candidate(reference, candidate, absolute_tolerance):
    pairs = [(reference[bid], r["raw_value"]) for bid, r in candidate.items()
             if reference[bid] is not None and r["raw_value"] is not None]
    errors = [value - ref for ref, value in pairs]
    n = len(pairs)
    within = sum(abs(e) <= absolute_tolerance for e in errors)
    coverage = all(r["coverage_fraction"] == 1 for r in candidate.values())
    return {"paired": n, "expected": len(reference), "within_tolerance": within,
            "absolute_tolerance_raw": absolute_tolerance, "bias_raw": sum(errors)/n if n else None,
            "mae_raw": sum(map(abs, errors))/n if n else None,
            "rmse_raw": (sum(e*e for e in errors)/n)**0.5 if n else None,
            "max_absolute_error_raw": max(map(abs, errors)) if n else None,
            "coverage_pass": coverage,
            "pass": n == len(reference) and n > 0 and within == n and coverage}
