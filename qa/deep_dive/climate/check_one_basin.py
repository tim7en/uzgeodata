"""Independent one-basin/one-month check of the local ERA5-Land grid.

Run from the repository root: python qa/deep_dive/climate/check_one_basin.py
Only standard geometry/raster libraries are used for the reduction; no production
aggregation code or cached production weights are imported.
"""
import hashlib
import json
import math
from pathlib import Path

import pyarrow.parquet as pq
import rasterio
from pyproj import Geod
from shapely.geometry import box, shape

ROOT = Path(__file__).resolve().parents[3]
GRID = ROOT / "WORKSPACE/derived/regional-climate-grids/era-2003.tif"
FRAME = ROOT / "GEODATA/transboundary_basins_v2/hydroatlas-level12-full-basins.geojson"
PUBLISHED = ROOT / "PUBLISHED/data/atlas/climate-continuation/era5-land/year=2003.parquet"
META = PUBLISHED.with_suffix(".json")
BASIN = "4121272730"
MONTH = 1
TOLERANCE = 0.01  # In each variable's own unit; detects materially wrong cell selection/scaling.


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    document = json.loads(FRAME.read_text(encoding="utf-8"))
    feature = next(f for f in document["features"] if str(f["properties"]["HYBAS_ID"]) == BASIN)
    geom = shape(feature["geometry"])
    meta = json.loads(META.read_text(encoding="utf-8"))
    assert meta["source"] == "ECMWF/ERA5_LAND/MONTHLY_AGGR"
    assert MONTH in meta["months"]
    assert geom.is_valid and not geom.is_empty

    with rasterio.open(GRID) as grid:
        assert grid.crs.to_epsg() == 4326
        assert grid.count == 24 and grid.width == 204 and grid.height == 133
        assert math.isclose(grid.transform.a, .1) and math.isclose(grid.transform.e, -.1)
        west, south, east, north = geom.bounds
        col0 = max(0, math.floor((west - grid.transform.c) / grid.transform.a))
        col1 = min(grid.width, math.ceil((east - grid.transform.c) / grid.transform.a))
        row0 = max(0, math.floor((grid.transform.f - north) / -grid.transform.e))
        row1 = min(grid.height, math.ceil((grid.transform.f - south) / -grid.transform.e))
        bands = {"temperature_c": grid.read(1), "precipitation_mm": grid.read(2)}
        pieces = []
        geod = Geod(ellps="WGS84")
        for row in range(row0, row1):
            for col in range(col0, col1):
                x0, y0 = grid.xy(row, col, offset="ul")
                cell = box(x0, y0 + grid.transform.e, x0 + grid.transform.a, y0)
                intersection = geom.intersection(cell)
                if intersection.is_empty or intersection.area <= 0:
                    continue
                cos_weight = intersection.area * math.cos(math.radians(y0 + grid.transform.e / 2))
                geodesic_area, _ = geod.geometry_area_perimeter(intersection)
                pieces.append({"row": row, "col": col, "cos_weight": cos_weight,
                               "geodesic_weight": abs(geodesic_area)})
        assert pieces, "No basin-grid intersections"
        results = {}
        for variable, pixels in bands.items():
            valid = [p for p in pieces if math.isfinite(float(pixels[p["row"], p["col"]]))
                     and float(pixels[p["row"], p["col"]]) > -9000]
            assert valid, f"No valid pixels: {variable}"
            output = {}
            for method, key in (("cos_latitude", "cos_weight"), ("geodesic", "geodesic_weight")):
                total = sum(p[key] for p in valid)
                output[method] = sum(float(pixels[p["row"], p["col"]]) * p[key] for p in valid) / total
            output["covered_fraction"] = sum(p["cos_weight"] for p in valid) / sum(p["cos_weight"] for p in pieces)
            results[variable] = output

    table = pq.read_table(PUBLISHED, filters=[("basin_id", "=", BASIN), ("year", "=", 2003),
                                              ("month", "=", MONTH)])
    rows = {row["variable"]: row for row in table.to_pylist()}
    for variable, output in results.items():
        assert variable in rows
        output["published"] = rows[variable]["value"]
        output["published_coverage"] = rows[variable]["coverage"]
        output["difference_cos"] = output["cos_latitude"] - output["published"]
        output["difference_geodesic"] = output["geodesic"] - output["published"]
        output["within_tolerance"] = abs(output["difference_cos"]) <= TOLERANCE

    report = {"basin_id": BASIN, "year": 2003, "month": MONTH,
              "frame_crs": document.get("crs", "GeoJSON default WGS84"),
              "raster_crs": "EPSG:4326", "raster_bands": 24,
              "raster_band_mapping": {"1": "January temperature_2m converted K to C in Earth Engine",
                                      "2": "January total_precipitation_sum converted m to mm in Earth Engine"},
              "overlap_cells": len(pieces), "tolerance": TOLERANCE,
              "files_sha256": {str(p.relative_to(ROOT)): sha256(p) for p in (GRID, FRAME, PUBLISHED, META)},
              "results": results,
              "status": "PASS" if all(v["within_tolerance"] for v in results.values()) else "FAIL"}
    target = Path(__file__).with_name("result.json")
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
