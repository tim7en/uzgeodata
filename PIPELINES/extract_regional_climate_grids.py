"""Reduce ERA5-Land and TerraClimate v1.1 grids onto all level-12 river basins.

ERA is acquired as one native-grid annual GeoTIFF from Earth Engine. TerraClimate
v1.1 is read from its producer's yearly NetCDF files using HTTP range requests;
only the Amu/Syr window is read. Both are reduced by fractional cell overlap.
Source versions and spatial support stay separate from the existing atlas cube.
"""
from __future__ import annotations

import argparse
import calendar
import json
import math
import os
from pathlib import Path
import sys
import time
import warnings

os.environ.setdefault("GDAL_SKIP", "netCDF")  # Permit remote HDF5 range access on macOS.

import geopandas as gpd
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import rasterio
from rasterio.errors import NotGeoreferencedWarning
from rasterio.transform import from_origin
from rasterio.windows import from_bounds, transform as window_transform
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FRAME = ROOT / "GEODATA/transboundary_basins_v2/hydroatlas-level12-full-basins.geojson"
OUT = ROOT / "PUBLISHED/data/atlas/climate-continuation"
CACHE = ROOT / "WORKSPACE/derived/regional-climate-grids"
ERA_ASSET = "ECMWF/ERA5_LAND/MONTHLY_AGGR"
TC_BASE = "https://climate.northwestknowledge.net/TERRACLIMATE-DATA"
TC_VARIABLES = ("ppt", "tmin", "tmax", "aet", "def", "pet", "q", "soil",
                "srad", "swe", "vap", "ws", "vpd", "PDSI")
ERA_EXTENDED = (
    ("tmin_c", "temperature_2m_min", "degrees Celsius", -273.15, 1),
    ("tmax_c", "temperature_2m_max", "degrees Celsius", -273.15, 1),
    ("dewpoint_c", "dewpoint_temperature_2m", "degrees Celsius", -273.15, 1),
    ("aet_mm", "total_evaporation_sum", "millimetres per month", 0, -1000),
    ("pet_mm", "potential_evaporation_sum", "millimetres per month", 0, -1000),
    ("runoff_mm", "runoff_sum", "millimetres per month", 0, 1000),
    ("soil_fraction", "volumetric_soil_water_layer_2", "fraction", 0, 1),
    ("swe_mm", "snow_depth_water_equivalent", "millimetres", 0, 1000),
    ("srad_wm2", "surface_solar_radiation_downwards_sum", "watts per square metre", 0, None),
    ("wind_u_ms", "u_component_of_wind_10m", "metres per second", 0, 1),
    ("wind_v_ms", "v_component_of_wind_10m", "metres per second", 0, 1),
    ("snowmelt_mm", "snowmelt_sum", "millimetres per month", 0, 1000),
)
TC_UNITS = {"ppt": "millimetres per month", "tmin": "degrees Celsius",
            "tmax": "degrees Celsius", "aet": "millimetres per month",
            "def": "millimetres per month", "pet": "millimetres per month",
            "q": "millimetres per month", "soil": "millimetres of soil moisture",
            "srad": "watts per square metre", "swe": "millimetres of snow water equivalent",
            "vap": "kilopascals", "ws": "metres per second", "vpd": "kilopascals",
            "PDSI": "index"}
TC_TRANSFORM = from_origin(-180, 90, 1 / 24, 1 / 24)
BOUNDS = (58.1, 34.45, 78.4, 47.25)


def frame():
    result = gpd.read_file(FRAME)[["HYBAS_ID", "NEXT_DOWN", "SUB_AREA", "system_id", "geometry"]]
    result["basin_id"] = result.HYBAS_ID.astype("int64").astype(str)
    return result.sort_values("basin_id").reset_index(drop=True)


def grid_weights(basins, transform, width, height):
    """Fractional overlap, with spherical-area approximation within each basin."""
    key = f"{transform.a:.9f}_{transform.c:.5f}_{transform.e:.9f}_{transform.f:.5f}_{width}_{height}"
    path = CACHE / f"weights-{key}.npz"
    if path.exists():
        try:
            saved = np.load(path)
            if list(saved["basin_id"]) == list(basins.basin_id):
                return saved["basin_index"], saved["flat_cell"], saved["weight"]
        except ValueError:  # Replace an older cache with a non-object identifier array.
            pass
    basin_index, flat_cell, weights = [], [], []
    west, north, dx, dy = transform.c, transform.f, transform.a, -transform.e
    for index, geom in enumerate(basins.geometry):
        minx, miny, maxx, maxy = geom.bounds
        c0 = max(0, int(math.floor((minx - west) / dx)))
        c1 = min(width, int(math.ceil((maxx - west) / dx)))
        r0 = max(0, int(math.floor((north - maxy) / dy)))
        r1 = min(height, int(math.ceil((north - miny) / dy)))
        local = []
        for row in range(r0, r1):
            top = north - row * dy
            for col in range(c0, c1):
                left = west + col * dx
                intersection = geom.intersection(box(left, top - dy, left + dx, top))
                if not intersection.is_empty and intersection.area > 0:
                    area = intersection.area * math.cos(math.radians(top - dy / 2))
                    local.append((row * width + col, area))
        if not local:
            point = geom.representative_point()
            col = min(width - 1, max(0, int((point.x - west) / dx)))
            row = min(height - 1, max(0, int((north - point.y) / dy)))
            local = [(row * width + col, 1.0)]
        total = sum(area for _, area in local)
        for cell, area in local:
            basin_index.append(index)
            flat_cell.append(cell)
            weights.append(area / total)
    CACHE.mkdir(parents=True, exist_ok=True)
    arrays = (np.asarray(basin_index, dtype=np.int32), np.asarray(flat_cell, dtype=np.int32),
              np.asarray(weights, dtype=np.float64))
    np.savez_compressed(path, basin_id=np.asarray(basins.basin_id, dtype=str), basin_index=arrays[0],
                        flat_cell=arrays[1], weight=arrays[2])
    return arrays


def reduce_grid(values, basin_index, flat_cell, weight, n_basins, nodata=None):
    sampled = values.ravel()[flat_cell].astype(np.float64)
    valid = np.isfinite(sampled) & (sampled > -9000)
    if nodata is not None and nodata < -9000:
        valid &= sampled != nodata
    covered = np.bincount(basin_index, weights=weight * valid, minlength=n_basins)
    summed = np.bincount(basin_index, weights=weight * np.where(valid, sampled, 0),
                         minlength=n_basins)
    return np.divide(summed, covered, out=np.full(n_basins, np.nan), where=covered > 0), covered


def write_rows(path, rows, metadata):
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path, compression="zstd")
    path.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")


def era_year(year, basins, latest):
    import ee
    import requests

    output = OUT / "era5-land" / f"year={year}.parquet"
    if output.exists() and year < latest.year:
        metadata = output.with_suffix(".json")
        if metadata.exists() and json.loads(metadata.read_text()).get("months") == list(range(1, 13)):
            print(f"ERA {year}: cached", flush=True)
            return
    months = range(1, 13) if year < latest.year else range(1, latest.month + 1)
    collection = ee.ImageCollection(ERA_ASSET)
    projection = collection.first().select("temperature_2m").projection().getInfo()
    layers = []
    for month in months:
        start = f"{year}-{month:02d}-01"
        end = f"{year + 1}-01-01" if month == 12 else f"{year}-{month + 1:02d}-01"
        image = ee.Image(collection.filterDate(start, end).first())
        layers.extend((image.select("temperature_2m").subtract(273.15).rename(f"t_{month:02d}"),
                       image.select("total_precipitation_sum").multiply(1000).rename(f"p_{month:02d}")))
    if not layers:
        return
    image = ee.Image.cat(layers).unmask(-9999)
    url = image.getDownloadURL({"region": ee.Geometry.Rectangle(list(BOUNDS)),
                                "crs": projection["crs"], "crs_transform": projection["transform"],
                                "format": "GEO_TIFF", "filePerBand": False})
    cache = CACHE / f"era-{year}.tif"
    cache.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            response = requests.get(url, timeout=120)
            response.raise_for_status()
            cache.write_bytes(response.content)
            break
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    rows = []
    with rasterio.open(cache) as dataset:
        assert dataset.count == 2 * len(months)
        basin_index, flat_cell, weight = grid_weights(basins, dataset.transform,
                                                       dataset.width, dataset.height)
        for position, month in enumerate(months):
            for band, variable, unit in ((2 * position + 1, "temperature_c", "degrees Celsius"),
                                         (2 * position + 2, "precipitation_mm", "millimetres per month")):
                values, coverage = reduce_grid(dataset.read(band), basin_index, flat_cell,
                                               weight, len(basins), dataset.nodata)
                rows.extend({"basin_id": basin, "year": year, "month": month,
                             "variable": variable, "value": float(value) if np.isfinite(value) else None,
                             "coverage": float(share), "unit": unit}
                            for basin, value, share in zip(basins.basin_id, values, coverage))
    write_rows(output, rows, {"source": ERA_ASSET, "year": year, "months": list(months),
                              "basins": len(basins), "grid": "native ERA5-Land 0.1 degree",
                              "reduction": "fractional cell overlap with basin polygons",
                              "source_transform": projection["transform"]})
    print(f"ERA {year}: {len(rows):,} rows", flush=True)


def era_extended_year(year, basins, latest):
    """Extract ERA water/energy predictors on their native grid for one year."""
    import ee
    import requests

    output = OUT / "era5-land-extended" / f"year={year}.parquet"
    months = list(range(1, 13 if year < latest.year else latest.month + 1))
    if output.exists():
        metadata = output.with_suffix(".json")
        if metadata.exists() and json.loads(metadata.read_text()).get("months") == months:
            print(f"ERA extended {year}: cached", flush=True)
            return
    collection = ee.ImageCollection(ERA_ASSET)
    projection = collection.first().select("temperature_2m").projection().getInfo()
    layers = []
    for month in months:
        start = f"{year}-{month:02d}-01"
        end = f"{year + 1}-01-01" if month == 12 else f"{year}-{month + 1:02d}-01"
        image = ee.Image(collection.filterDate(start, end).first())
        seconds = calendar.monthrange(year, month)[1] * 86400
        for variable, band, _, offset, scale in ERA_EXTENDED:
            selected = image.select(band)
            if offset:
                selected = selected.add(offset)
            selected = selected.multiply(1 / seconds if scale is None else scale)
            layers.append(selected.rename(f"{variable}_{month:02d}"))
    image = ee.Image.cat(layers).unmask(-9999)
    url = image.getDownloadURL({"region": ee.Geometry.Rectangle(list(BOUNDS)),
                                "crs": projection["crs"], "crs_transform": projection["transform"],
                                "format": "GEO_TIFF", "filePerBand": False})
    cache = CACHE / f"era-extended-{year}.tif"
    cache.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            response = requests.get(url, timeout=180)
            response.raise_for_status()
            cache.write_bytes(response.content)
            break
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    rows = []
    with rasterio.open(cache) as dataset:
        assert dataset.count == len(ERA_EXTENDED) * len(months)
        basin_index, flat_cell, weight = grid_weights(basins, dataset.transform,
                                                       dataset.width, dataset.height)
        for position, month in enumerate(months):
            for offset, (variable, _, unit, _, _) in enumerate(ERA_EXTENDED):
                band = position * len(ERA_EXTENDED) + offset + 1
                values, coverage = reduce_grid(dataset.read(band), basin_index, flat_cell,
                                               weight, len(basins), dataset.nodata)
                rows.extend({"basin_id": basin, "year": year, "month": month,
                             "variable": variable, "value": float(value) if np.isfinite(value) else None,
                             "coverage": float(share), "unit": unit}
                            for basin, value, share in zip(basins.basin_id, values, coverage))
    write_rows(output, rows, {"source": ERA_ASSET, "year": year, "months": months,
                              "basins": len(basins), "grid": "native ERA5-Land 0.1 degree",
                              "variables": [v[0] for v in ERA_EXTENDED],
                              "reduction": "fractional cell overlap with basin polygons",
                              "source_transform": projection["transform"]})
    print(f"ERA extended {year}: {len(rows):,} rows", flush=True)


def tc_year(year, basins, refresh=False, variables=TC_VARIABLES):
    family = "terraclimate-v1.1" if tuple(variables) == TC_VARIABLES else "terraclimate-v1.1-primary"
    output = OUT / family / f"year={year}.parquet"
    if output.exists() and not refresh:
        print(f"TerraClimate v1.1 {year}: cached", flush=True)
        return
    window = from_bounds(*BOUNDS, transform=TC_TRANSFORM).round_offsets().round_lengths()
    transform = window_transform(window, TC_TRANSFORM)
    basin_index, flat_cell, weight = grid_weights(basins, transform,
                                                   int(window.width), int(window.height))
    rows = []
    source_files = {}
    for variable in variables:
        url = f"{TC_BASE}/TerraClimate_{variable}_{year}.nc"
        path = f"HDF5:/vsicurl/{url}://{variable}"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", NotGeoreferencedWarning)
            with rasterio.open(path) as dataset:
                if dataset.count != 12 or dataset.tags().get("version") != "V1.1":
                    raise ValueError(f"Unexpected TerraClimate release: {url}")
                source_files[variable] = {"url": url, "scale": dataset.scales[0],
                                          "offset": dataset.offsets[0],
                                          "nodata": dataset.nodata,
                                          "unit": dataset.tags(1).get("units"),
                                          "published_unit": TC_UNITS[variable]}
                for month in range(1, 13):
                    raw = dataset.read(month, window=window)
                    data = raw.astype(np.float64) * dataset.scales[month - 1] + dataset.offsets[month - 1]
                    data[raw == dataset.nodata] = -9999
                    values, coverage = reduce_grid(data, basin_index, flat_cell,
                                                   weight, len(basins))
                    rows.extend({"basin_id": basin, "year": year, "month": month,
                                 "variable": variable, "value": float(value) if np.isfinite(value) else None,
                                 "coverage": float(share), "unit": TC_UNITS[variable]}
                                for basin, value, share in zip(basins.basin_id, values, coverage))
        print(f"TerraClimate v1.1 {year}: {variable} complete", flush=True)
    write_rows(output, rows, {"source": "TerraClimate v1.1 producer NetCDF", "year": year,
                              "basins": len(basins), "months": list(range(1, 13)),
                              "grid": "1/24 degree", "reduction": "fractional cell overlap with basin polygons",
                              "source_files": source_files})
    print(f"TerraClimate v1.1 {year}: {len(rows):,} rows", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", choices=("era", "era-extended", "terraclimate-v11"))
    parser.add_argument("--years", help="YYYY-YYYY; defaults to full ERA history or available v1.1 years")
    parser.add_argument("--refresh", action="store_true", help="Re-read an existing v1.1 year after a producer revision")
    parser.add_argument("--variables", help="Comma-separated subset of v1.1 variables for version-overlap checks")
    args = parser.parse_args()
    basins = frame()
    if len(basins) != 7445:
        raise ValueError(f"Expected 7,445 regional basins, got {len(basins)}")
    if args.source in ("era", "era-extended"):
        import ee
        from datetime import datetime, timezone
        ee.Initialize(project="ee-sabitovty")
        last = ee.ImageCollection(ERA_ASSET).sort("system:time_start", False).first()
        latest = datetime.fromtimestamp(last.get("system:time_start").getInfo() / 1000, timezone.utc)
        # With no --years, run to the newest ERA year so a new year is picked up
        # without a code change.
        start, _, end = (args.years or f"2003-{latest.year}").partition("-")
        years = range(int(start), int(end or start) + 1)
        for year in years:
            if year <= latest.year:
                if args.source == "era":
                    era_year(year, basins, latest)
                else:
                    era_extended_year(year, basins, latest)
    else:
        import re
        import requests
        listing = requests.get(f"{TC_BASE}/", timeout=45)
        listing.raise_for_status()
        found = {int(y) for y in re.findall(r"TerraClimate_ppt_(\d{4})\.nc", listing.text)}
        if args.years:
            start, _, end = args.years.partition("-")
            years = range(int(start), int(end or start) + 1)
            missing = [y for y in years if y not in found]
            if missing:
                raise ValueError(f"TerraClimate v1.1 yearly files not yet published: {missing}")
        else:
            years = range(2025, max(found) + 1)
        variables = tuple(args.variables.split(",")) if args.variables else TC_VARIABLES
        if not set(variables) <= set(TC_VARIABLES):
            raise ValueError(f"Unknown TerraClimate variables: {set(variables) - set(TC_VARIABLES)}")
        for year in years:
            tc_year(year, basins, refresh=args.refresh, variables=variables)


if __name__ == "__main__":
    main()
