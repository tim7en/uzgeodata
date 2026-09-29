"""ERA5-Land snow-forecast predictors on the native grid for the whole Aral region.

The per-gauge extractor (extract_snow_forecast_forcing.py) stores every day for
every cell, which is right for trend work on one basin and far too much for the
Amu Darya at Kerki. A forecast issued on the 1st of January to April only needs:

  swe_issue<k>   SWE on the day before issue month k (31 Dec, 31 Jan, end Feb, 31 Mar)
  ppt_<m>        monthly precipitation, October to September
  t2m_<m>        monthly mean 2 m temperature
  swe_<m>        monthly mean SWE, for peak-SWE climatology and glacier screening

So each water year is one GeoTIFF of at most 40 bands over the regional bounding
box, and any polygon (a gauge catchment, a level-12 basin) is reduced from it
afterwards. The grids stay in WORKSPACE; they are rebuildable and not published.

    python PIPELINES/extract_snow_forecast_region.py --years 1951-2025
"""
from __future__ import annotations

import argparse
import calendar
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIPELINES.extract_regional_climate_grids import BOUNDS  # noqa: E402

OUT = ROOT / "WORKSPACE/derived/snow-forecast-region"
DAILY = "ECMWF/ERA5_LAND/DAILY_AGGR"
MONTHLY = "ECMWF/ERA5_LAND/MONTHLY_AGGR"
WATER_MONTHS = (10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9)


def download(image, region, projection, path):
    import requests
    url = image.getDownloadURL({"region": region, "crs": projection["crs"],
                                "crs_transform": projection["transform"], "format": "GEO_TIFF"})
    for attempt in range(4):
        try:
            response = requests.get(url, timeout=600)
            response.raise_for_status()
            path.write_bytes(response.content)
            return
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", default="1951-2025", help="water years, labelled by their ending year")
    args = parser.parse_args()
    import ee
    ee.Initialize(project="ee-sabitovty")
    OUT.mkdir(parents=True, exist_ok=True)
    region = ee.Geometry.Rectangle(list(BOUNDS))
    daily, monthly = ee.ImageCollection(DAILY), ee.ImageCollection(MONTHLY)
    projection = monthly.first().select("temperature_2m").projection().getInfo()

    elevation = OUT / "elevation.tif"
    if not elevation.exists():
        dem = (ee.Image("CGIAR/SRTM90_V4").select("elevation").unmask(0)
               .reduceResolution(ee.Reducer.mean(), maxPixels=65535)
               .reproject(crs=projection["crs"], crsTransform=projection["transform"]))
        download(dem, region, projection, elevation)

    latest_daily = ee.Date(daily.aggregate_max("system:time_start")).format("YYYY-MM-dd").getInfo()
    latest_monthly = ee.Date(monthly.aggregate_max("system:time_start")).format("YYYY-MM").getInfo()
    start, _, end = args.years.partition("-")
    for wy in range(int(start), int(end or start) + 1):
        path = OUT / f"wy={wy}.tif"
        layers, names = [], []
        for k, month in enumerate((1, 2, 3, 4), start=1):
            day_before = f"{wy - 1}-12-31" if month == 1 else \
                f"{wy}-{month - 1:02d}-{calendar.monthrange(wy, month - 1)[1]:02d}"
            if day_before > latest_daily:
                break
            image = daily.filterDate(day_before, ee.Date(day_before).advance(1, "day")).first()
            layers.append(ee.Image(image).select("snow_depth_water_equivalent").multiply(1000))
            names.append(f"swe_issue{k}")
        for month in WATER_MONTHS:
            year = wy - 1 if month >= 10 else wy
            if f"{year}-{month:02d}" > latest_monthly:
                break
            image = ee.Image(monthly.filterDate(f"{year}-{month:02d}-01",
                                                ee.Date(f"{year}-{month:02d}-01").advance(1, "month")).first())
            layers += [image.select("total_precipitation_sum").multiply(1000),
                       image.select("temperature_2m").subtract(273.15),
                       image.select("snow_depth_water_equivalent").multiply(1000)]
            names += [f"ppt_{month:02d}", f"t2m_{month:02d}", f"swe_{month:02d}"]
        sidecar = path.with_suffix(".json")
        if path.exists() and sidecar.exists() and json.loads(sidecar.read_text())["bands"] == names:
            continue
        if not names:
            continue
        stack = ee.Image.cat([layer.rename(name) for layer, name in zip(layers, names)]).toFloat()
        download(stack, region, projection, path)
        sidecar.write_text(json.dumps({"water_year": wy, "bands": names,
                                       "sources": [DAILY, MONTHLY], "units": {
                                           "swe": "mm", "ppt": "mm per month", "t2m": "degrees Celsius"}}) + "\n")
        print(f"WY {wy}: {len(names)} bands", flush=True)


if __name__ == "__main__":
    main()
