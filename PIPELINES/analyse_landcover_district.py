"""Land cover composition and change for one administrative district.

Reads the Impact Observatory / Esri 10 m annual land cover directly from the
Cloud-Optimised GeoTIFFs published on the Microsoft Planetary Computer, clips it
to a district polygon from the OCHA boundaries, and reports the area of each
class per year and what changed between the first year and the last.

Being COGs, only the bytes covering the district are fetched — a district is a
few thousand pixels across, against a global mosaic of hundreds of gigabytes.
Nothing is downloaded whole.

On Earth Engine: the same product is served there as
``projects/sat-io/open-datasets/landcover/ESRI_Global-LULC_10m_TS`` and this
analysis was written for it first. Earth Engine needs an interactive browser
sign-in to mint a token, which a non-interactive session cannot do, so it reads
the identical rasters from their open COG mirror instead. The numbers are the
same data; only the transport differs.

    python PIPELINES/analyse_landcover_district.py --pcode UZ33217
    python PIPELINES/analyse_landcover_district.py --pcode UZ18233 --years 2017 2023
"""

from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

try:
    import numpy as np
    import rasterio
    import requests
    from rasterio.features import geometry_mask
    from rasterio.warp import transform_geom
    from rasterio.windows import from_bounds
    from shapely.geometry import mapping, shape
except ImportError as error:  # pragma: no cover - depends on the workstation
    raise SystemExit("rasterio, shapely and requests are required: pip install rasterio shapely requests") from error

ROOT = Path(__file__).resolve().parent.parent
DISTRICTS = ROOT / "PUBLISHED" / "data" / "admin" / "adm2.geojson"
PROVINCES = ROOT / "PUBLISHED" / "data" / "admin" / "adm1.geojson"
OUTPUT_DIR = ROOT / "PUBLISHED" / "data" / "analysis"

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SIGN = "https://planetarycomputer.microsoft.com/api/sas/v1/sign"
COLLECTION = "io-lulc-annual-v02"

# Colours follow the product's own legend closely enough to be recognisable.
PALETTE = {
    "Water": "#1a5bab", "Trees": "#358221", "Flooded vegetation": "#87d19e",
    "Crops": "#ffdb5c", "Built area": "#ed022a", "Bare ground": "#ede9e4",
    "Snow/ice": "#f2faff", "Clouds": "#c8c8c8", "Rangeland": "#c6ad8d",
}


def district(pcode: str) -> dict:
    for feature in json.loads(DISTRICTS.read_text(encoding="utf8"))["features"]:
        if feature["properties"]["pcode"] == pcode:
            return feature
    raise SystemExit(f"No district with P-code {pcode}. See PUBLISHED/data/admin/adm2.geojson.")


def province_name(pcode: str) -> str:
    for feature in json.loads(PROVINCES.read_text(encoding="utf8"))["features"]:
        if feature["properties"]["pcode"] == pcode:
            return feature["properties"]["nameEn"]
    return pcode


def search(geometry) -> list[dict]:
    response = requests.post(STAC, json={
        "collections": [COLLECTION],
        "intersects": mapping(geometry.centroid),
        "limit": 50,
    }, timeout=90)
    response.raise_for_status()
    return sorted(response.json()["features"],
                  key=lambda item: item["properties"]["start_datetime"])


def sign(href: str) -> str:
    response = requests.get(SIGN, params={"href": href}, timeout=90)
    response.raise_for_status()
    return response.json()["href"]


def class_names(item: dict) -> dict[int, str]:
    values = item["assets"]["data"].get("file:values", [])
    return {entry["values"][0]: entry["summary"] for entry in values}


def measure(item: dict, geometry) -> tuple[dict[int, int], float]:
    """Count pixels of each class inside the polygon.

    The mosaic is in UTM, so the polygon is reprojected to the raster's CRS
    rather than the raster to the polygon's: reprojecting a categorical surface
    would resample class codes and invent classes that are not there.
    """
    href = sign(item["assets"]["data"]["href"])
    projected = shape(transform_geom("EPSG:4326", item["properties"]["proj:epsg"] and
                                     f"EPSG:{item['properties']['proj:epsg']}", mapping(geometry)))
    with rasterio.open(href) as source:
        window = from_bounds(*projected.bounds, transform=source.transform).round_offsets().round_lengths()
        data = source.read(1, window=window)
        transform = source.window_transform(window)
        pixel_area = abs(transform.a * transform.e)
        outside = geometry_mask([mapping(projected)], out_shape=data.shape,
                                transform=transform, invert=False)
        inside = np.ma.masked_array(data, mask=outside)
        values, counts = np.unique(inside.compressed(), return_counts=True)
    return dict(zip(values.tolist(), counts.tolist())), pixel_area


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pcode", default="UZ33217", help="ADM2 P-code (default Urgench, Khorezm).")
    parser.add_argument("--years", nargs="*", type=int, help="Years to read. Default: all available.")
    args = parser.parse_args()

    feature = district(args.pcode)
    geometry = shape(feature["geometry"])
    properties = feature["properties"]
    name = properties["nameEn"]
    province = province_name(properties["parent"])

    items = search(geometry)
    if args.years:
        items = [i for i in items if int(i["properties"]["start_datetime"][:4]) in args.years]
    if not items:
        raise SystemExit("No land cover items cover this district for those years.")

    names = class_names(items[0])
    print(f"{name} district, {province} ({args.pcode})")
    print(f"  Impact Observatory / Esri 10 m annual land cover, {COLLECTION}")
    print(f"  {len(items)} yearly mosaics, tile {items[0]['id'].split('-')[0]}, "
          f"EPSG:{items[0]['properties']['proj:epsg']}\n")

    per_year: OrderedDict[int, dict] = OrderedDict()
    for item in items:
        year = int(item["properties"]["start_datetime"][:4])
        counts, pixel_area = measure(item, geometry)
        total = sum(counts.values())
        per_year[year] = {
            "pixels": total,
            "areaKm2": round(total * pixel_area / 1e6, 3),
            "classes": {names.get(code, str(code)): {
                "pixels": count,
                "km2": round(count * pixel_area / 1e6, 3),
                "percent": round(count / total * 100, 2),
            } for code, count in sorted(counts.items(), key=lambda kv: -kv[1])},
        }
        print(f"  {year} read: {total:,} pixels ({total * pixel_area / 1e6:,.1f} km²)")

    first, last = min(per_year), max(per_year)
    labels = sorted({label for year in per_year.values() for label in year["classes"]})

    print(f"\n{'CLASS':22}", end="")
    for year in per_year:
        print(f"{year:>10}", end="")
    print(f"{'CHANGE':>12}")
    print("-" * (22 + 10 * len(per_year) + 12))
    changes = {}
    for label in sorted(labels, key=lambda l: -per_year[last]["classes"].get(l, {}).get("km2", 0)):
        print(f"{label:22}", end="")
        for year in per_year:
            print(f"{per_year[year]['classes'].get(label, {}).get('km2', 0):>10.1f}", end="")
        delta = (per_year[last]["classes"].get(label, {}).get("km2", 0)
                 - per_year[first]["classes"].get(label, {}).get("km2", 0))
        changes[label] = round(delta, 3)
        print(f"{delta:>+12.1f}")
    print(f"\n  areas in km²; change is {last} minus {first}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    target = OUTPUT_DIR / f"landcover-{args.pcode}.json"
    target.write_text(json.dumps({
        "version": "1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "collection": COLLECTION,
            "title": "Impact Observatory / Esri 10 m Annual Land Use Land Cover (9-class) V2",
            "via": "Microsoft Planetary Computer STAC, Cloud-Optimised GeoTIFF",
            "licence": "CC-BY-4.0",
            "earthEngineEquivalent": "projects/sat-io/open-datasets/landcover/ESRI_Global-LULC_10m_TS",
        },
        "district": {
            "pcode": args.pcode, "name": name, "province": province,
            "type": properties.get("type"), "nameRu": properties.get("nameRu"),
            "nameUz": properties.get("nameUz"),
            "bbox": [round(value, 5) for value in geometry.bounds],
        },
        "palette": PALETTE,
        "years": per_year,
        "changeKm2": changes,
        "note": (
            "Pixel counts are taken in the mosaic's own UTM projection, so a pixel is 10 m by "
            "10 m on the ground and area is a count times 100 m². The district polygon is "
            "reprojected to the raster rather than the raster to the polygon: resampling a "
            "categorical surface would blend class codes into classes that do not exist."
        ),
    }, ensure_ascii=False, indent=2), encoding="utf8")
    print(f"  -> {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
