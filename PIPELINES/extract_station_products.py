"""Extract gridded estimates at the station coordinates, month by month.

python PIPELINES/extract_station_products.py [--years 2003-2022]

A basin mean cannot be compared with a thermometer. The regional store holds values
reduced over whole basins, which is the right support for an atlas and the wrong one
for asking how well a product reproduces what a station recorded. So this samples the
products at the station's own grid cell instead, over the same months the station
archive covers.

Two independent products are taken for air temperature and for precipitation --
TerraClimate and ERA5-Land -- because a single product offers nothing to weigh
against itself. Soil temperature comes from ERA5-Land alone; nothing else here
measures it, and that limitation travels with the result.

Each value keeps the band and scale factor it came from. TerraClimate publishes
tenths of a degree and ERA5-Land publishes kelvin; both are converted here, once,
where the conversion can be read beside the source.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core.runtime import utc_now, write_json
from PIPELINES.build_station_crosswalk import read
from PIPELINES.verify_station_crosswalk import VERIFIED

OUT = ROOT / "PUBLISHED/data/hydromet/station-product-series.csv"
SUMMARY = ROOT / "PUBLISHED/data/hydromet/station-product-series.manifest.json"
PROJECT = "ee-sabitovty"
DEFAULT_YEARS = (2003, 2022)

# product -> asset, and band -> (measure, scale, offset, unit)
PRODUCTS = {
    "terraclimate": {
        "asset": "IDAHO_EPSCOR/TERRACLIMATE",
        "bands": {
            "tmmx": ("air_temperature_max", 0.1, 0.0, "degrees Celsius"),
            "tmmn": ("air_temperature_min", 0.1, 0.0, "degrees Celsius"),
            "pr": ("precipitation_total", 1.0, 0.0, "millimetres per month"),
        },
    },
    "era5_land": {
        "asset": "ECMWF/ERA5_LAND/MONTHLY_AGGR",
        "bands": {
            "temperature_2m": ("air_temperature_mean", 1.0, -273.15, "degrees Celsius"),
            "soil_temperature_level_1": ("soil_temperature_mean", 1.0, -273.15, "degrees Celsius"),
            "total_precipitation_sum": ("precipitation_total", 1000.0, 0.0, "millimetres per month"),
        },
    },
}


NSIDC_STATIONS = ROOT / "PUBLISHED/data/hydromet/nsidc-central-asia-stations.csv"


def stations(source="national"):
    """Located stations from either archive.

    The national sites reach their coordinates through the name crosswalk and carry
    its verdict; the NSIDC sites carry their own coordinates and need no crosswalk,
    so nothing about their placement is inferred.
    """
    out = []
    if source == "national":
        for row in read(VERIFIED):
            if row["match_status"] == "matched_by_name" and row["longitude"]:
                out.append({"station_id": row["observation_station_id"],
                            "name": row["observation_name"],
                            "longitude": float(row["longitude"]), "latitude": float(row["latitude"]),
                            "elevation_m": row["elevation_m"],
                            "verification": row.get("verification", "not_checked")})
    else:
        for row in read(NSIDC_STATIONS):
            if row["in_domain"] == "True":
                out.append({"station_id": row["station_id"], "name": row["name"],
                            "longitude": float(row["longitude"]), "latitude": float(row["latitude"]),
                            "elevation_m": row["elevation_m"],
                            "verification": "coordinate_supplied_by_source"})
    return out


def collection(sites):
    import ee
    return ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([s["longitude"], s["latitude"]]), {"station_id": s["station_id"]})
        for s in sites])


def year_rows(product, points, year):
    """One call per product-year: twelve months of every band, sampled at each point."""
    import ee
    spec = PRODUCTS[product]
    source = ee.ImageCollection(spec["asset"])
    stack = []
    for band in spec["bands"]:
        projection = source.first().select(band).projection()
        for month in range(1, 13):
            start = ee.Date.fromYMD(year, month, 1)
            stack.append(source.select(band).filterDate(start, start.advance(1, "month"))
                         .mean().rename(f"{band}__{month:02d}").setDefaultProjection(projection))
        scale = source.first().select(band).projection().nominalScale()
    table = ee.Image.cat(stack).reduceRegions(
        collection=points, reducer=ee.Reducer.first(), scale=scale).getInfo()

    rows = []
    for feature in table["features"]:
        properties = feature["properties"]
        for band, (measure, factor, offset, unit) in spec["bands"].items():
            for month in range(1, 13):
                raw = properties.get(f"{band}__{month:02d}")
                rows.append({
                    "station_id": properties["station_id"], "product": product, "band": band,
                    "measure": measure, "year": year, "month": month,
                    "value": None if raw is None else raw * factor + offset,
                    "unit": unit, "asset": spec["asset"]})
    return rows


def extract(years=DEFAULT_YEARS, project=PROJECT, source="national", out=None):
    import ee
    ee.Initialize(project=project)
    sites = stations(source)
    points = collection(sites)
    span = list(range(years[0], years[1] + 1))
    started, at = time.perf_counter(), utc_now()

    rows = []
    for product in PRODUCTS:
        for year in span:
            rows.extend(year_rows(product, points, year))
        print(f"{product}: {len(sites)} stations x {len(span)} years "
              f"({time.perf_counter() - started:.0f}s)", flush=True)

    target = Path(out) if out else OUT
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    filled = sum(1 for r in rows if r["value"] is not None)
    summary = {
        "generated_at": at, "source": source, "table": str(target), "years": [span[0], span[-1]], "stations": len(sites),
        "rows": len(rows), "values": filled, "missing": len(rows) - filled,
        "products": {p: {"asset": s["asset"], "bands": list(s["bands"])} for p, s in PRODUCTS.items()},
        "wall_seconds": time.perf_counter() - started,
        "support": "station_grid_cell",
        "meaning": "Product values sampled at the station's own grid cell, not a basin mean. "
                   "The cell is far larger than the instrument, so a difference between the "
                   "two is a difference of support as much as of accuracy.",
    }
    write_json(Path(str(target).replace(".csv", ".manifest.json")), summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", default=f"{DEFAULT_YEARS[0]}-{DEFAULT_YEARS[1]}")
    parser.add_argument("--source", choices=("national", "nsidc"), default="national")
    parser.add_argument("--out", default=None)
    arguments = parser.parse_args()
    first, _, last = arguments.years.partition("-")
    print(json.dumps(extract((int(first), int(last or first)), source=arguments.source,
                             out=arguments.out), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
