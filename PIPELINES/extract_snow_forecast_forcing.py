"""Daily ERA5-Land snow and weather for the grid cells over one gauged basin.

Seasonal flow forecasting from snow (after Barnhart et al., USGS, for the
Kashkadarya) needs basin and elevation-band snow water equivalent, precipitation
and temperature for as many years as the gauge has flow. Their snow comes from
SnowModel run on a 100 m grid; this extractor supplies the coarser substitute that
exists everywhere: ERA5-Land DAILY_AGGR on its native 0.1 degree grid, 1950 on.

For each year one GeoTIFF of daily bands is downloaded for the basin's bounding
box. Each cell keeps its fractional overlap with the gauge basin and its mean SRTM
elevation, so the forecast build can form elevation bands.

    python PIPELINES/extract_snow_forecast_forcing.py --gauge 16290
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import math
from pathlib import Path
import sys
import time

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pyogrio
import rasterio
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
GAUGES = ROOT / "GEODATA/ca-discharge-2023/CA-discharge.gpkg"
OUT = ROOT / "RESEARCH/snow-forecast"
CACHE = ROOT / "WORKSPACE/derived/snow-forecast"
ASSET = "ECMWF/ERA5_LAND/DAILY_AGGR"
BANDS = (("swe_mm", "snow_depth_water_equivalent", 1000, 0),
         ("ppt_mm", "total_precipitation_sum", 1000, 0),
         ("t2m_c", "temperature_2m", 1, -273.15))


def basin(code):
    frame = pyogrio.read_dataframe(GAUGES, layer="basins", where=f"CODE='{code}'")
    if frame.empty:
        raise ValueError(f"No CA-discharge basin for gauge {code}")
    return frame.geometry.iloc[0], float(frame.area_km2.iloc[0])


def cells(geometry, transform, width, height):
    """Every grid cell the basin touches, with its share of the basin area."""
    west, north, dx, dy = transform.c, transform.f, transform.a, -transform.e
    found = []
    for row in range(height):
        top = north - row * dy
        for col in range(width):
            left = west + col * dx
            part = geometry.intersection(box(left, top - dy, left + dx, top))
            if not part.is_empty and part.area > 0:
                found.append({"cell": row * width + col, "row": row, "col": col,
                              "lon": round(left + dx / 2, 4), "lat": round(top - dy / 2, 4),
                              "area": part.area * math.cos(math.radians(top - dy / 2))})
    total = sum(c["area"] for c in found)
    for c in found:
        c["weight"] = c.pop("area") / total
    return found


def download(image, region, projection, path):
    import requests
    url = image.getDownloadURL({"region": region, "crs": projection["crs"],
                                "crs_transform": projection["transform"], "format": "GEO_TIFF"})
    for attempt in range(4):
        try:
            response = requests.get(url, timeout=300)
            response.raise_for_status()
            path.write_bytes(response.content)
            return
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gauge", required=True, help="CA-discharge gauge CODE, e.g. 16290 for Pskem-Mullala")
    parser.add_argument("--years", default="1950-2025")
    args = parser.parse_args()
    import ee
    ee.Initialize(project="ee-sabitovty")

    geometry, area_km2 = basin(args.gauge)
    minx, miny, maxx, maxy = geometry.bounds
    region = ee.Geometry.Rectangle([minx - .06, miny - .06, maxx + .06, maxy + .06])
    collection = ee.ImageCollection(ASSET)
    projection = collection.first().select("temperature_2m").projection().getInfo()
    out = OUT / args.gauge
    cache = CACHE / args.gauge
    out.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)

    # Cell elevation: SRTM 90 m averaged onto the ERA5-Land grid.
    dem_path = cache / "elevation.tif"
    if not dem_path.exists():
        dem = (ee.Image("CGIAR/SRTM90_V4").select("elevation")
               .reduceResolution(ee.Reducer.mean(), maxPixels=65535)
               .reproject(crs=projection["crs"], crsTransform=projection["transform"]))
        download(dem, region, projection, dem_path)
    with rasterio.open(dem_path) as dataset:
        transform, width, height = dataset.transform, dataset.width, dataset.height
        elevation = dataset.read(1)
    grid = cells(geometry, transform, width, height)
    for c in grid:
        c["elevation_m"] = round(float(elevation[c["row"], c["col"]]), 1)

    start, _, end = args.years.partition("-")
    rows_written = 0
    for year in range(int(start), int(end or start) + 1):
        path = out / f"year={year}.parquet"
        if path.exists() and year < date.today().year - 1:
            continue
        rows, count = [], 0
        # Three variables x 366 days passes Earth Engine's 1,024-band download limit,
        # so each year is fetched in two halves.
        for half, (first, stop) in enumerate(((f"{year}-01-01", f"{year}-07-01"),
                                              (f"{year}-07-01", f"{year + 1}-01-01"))):
            daily = collection.filterDate(first, stop)
            days = daily.aggregate_array("system:index").getInfo()
            if not days:
                continue
            tif = cache / f"{year}-{half}.tif"
            download(daily.select([b[1] for b in BANDS]).toBands(), region, projection, tif)
            with rasterio.open(tif) as dataset:
                if (dataset.width, dataset.height) != (width, height):
                    raise ValueError(f"{year}: grid {dataset.width}x{dataset.height} differs from elevation grid")
                data = dataset.read()
            for d, day in enumerate(days):
                stamp = f"{day[:4]}-{day[4:6]}-{day[6:8]}"
                for b, (name, _, scale, offset) in enumerate(BANDS):
                    layer = data[d * len(BANDS) + b]
                    for c in grid:
                        value = float(layer[c["row"], c["col"]])
                        rows.append({"date": stamp, "cell": c["cell"], "variable": name,
                                     "value": value * scale + offset if np.isfinite(value) else None})
            count += len(days)
        if not rows:
            continue
        pq.write_table(pa.Table.from_pylist(rows), path, compression="zstd")
        rows_written += len(rows)
        print(f"{args.gauge} {year}: {count} days x {len(grid)} cells", flush=True)

    (out / "cells.json").write_text(json.dumps({
        "gauge": args.gauge, "basin_area_km2": area_km2, "source": ASSET,
        "grid": "native ERA5-Land 0.1 degree", "elevation": "CGIAR SRTM 90 m mean per cell",
        "cells": [{k: v for k, v in c.items() if k not in ("row", "col")} for c in grid],
    }, indent=2) + "\n")
    print(f"{args.gauge}: {len(grid)} cells, {rows_written:,} new rows", flush=True)


if __name__ == "__main__":
    main()
