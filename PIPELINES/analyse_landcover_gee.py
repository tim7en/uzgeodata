"""Land cover for one district, computed on Earth Engine.

The same analysis as analyse_landcover_district.py, but the counting happens on
Earth Engine's servers rather than here: the district becomes an ee.Geometry, the
land cover collection is filtered to it, and a frequency histogram is reduced
per year. Only the histogram comes back, so the raster never moves.

Doing it there rather than locally is the point — once this runs, any other
Earth Engine collection is reachable the same way, and the reduction scales to
the whole country without downloading anything.

Authentication cannot be automated. Earth Engine mints its token through a
browser sign-in, so run this once in your own terminal:

    earthengine authenticate --project ee-sabitovty

That writes a refresh token to ~/.config/earthengine/credentials and this script
works from then on. A token from an OAuth client still in "testing" status
expires after seven days, which is why an old credentials file fails with
invalid_grant rather than simply working.

    python PIPELINES/analyse_landcover_gee.py --pcode UZ33217
    python PIPELINES/analyse_landcover_gee.py --pcode UZ18233 --asset ESA/WorldCover/v200
"""

from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DISTRICTS = ROOT / "PUBLISHED" / "data" / "admin" / "adm2.geojson"
PROVINCES = ROOT / "PUBLISHED" / "data" / "admin" / "adm1.geojson"
OUTPUT_DIR = ROOT / "PUBLISHED" / "data" / "analysis"

PROJECT = "ee-sabitovty"
# The Impact Observatory / Esri 10 m series, as published in the Earth Engine
# community catalogue. The band is a class code, not a measurement.
DEFAULT_ASSET = "projects/sat-io/open-datasets/landcover/ESRI_Global-LULC_10m_TS"

CLASSES = {
    1: "Water", 2: "Trees", 4: "Flooded vegetation", 5: "Crops",
    7: "Built area", 8: "Bare ground", 9: "Snow/ice", 10: "Clouds", 11: "Rangeland",
}


def feature_for(path: Path, pcode: str, key: str = "pcode") -> dict | None:
    for feature in json.loads(path.read_text(encoding="utf8"))["features"]:
        if feature["properties"][key] == pcode:
            return feature
    return None


def initialise():
    """Bring up Earth Engine, or explain exactly what is missing.

    ee.Authenticate() is deliberately not called: it opens a browser and blocks,
    which is useless in a script and worse in an automated run. Failing with the
    command to type is more honest than hanging.
    """
    try:
        import ee
    except ImportError as error:
        raise SystemExit("earthengine-api is not installed: pip install earthengine-api") from error

    try:
        ee.Initialize(project=PROJECT)
        ee.Number(1).getInfo()          # forces a real call, so a stale token fails here
        return ee
    except Exception as error:
        raise SystemExit(
            f"Earth Engine is not authenticated for project {PROJECT}.\n"
            f"  reason: {str(error).strip()[:200]}\n\n"
            "  Run this once, in your own terminal, and sign in with the browser it opens:\n"
            f"      earthengine authenticate --project {PROJECT}\n\n"
            "  Then re-run this script. If the sign-in succeeds but access is still refused,\n"
            "  the Earth Engine API is probably not enabled on the Cloud project:\n"
            f"      https://console.cloud.google.com/apis/library/earthengine.googleapis.com?project={PROJECT}"
        ) from error


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pcode", default="UZ33217", help="ADM2 P-code (default Urgench, Khorezm).")
    parser.add_argument("--asset", default=DEFAULT_ASSET, help="Earth Engine ImageCollection id.")
    parser.add_argument("--scale", type=int, default=10, help="Reduction scale in metres.")
    parser.add_argument("--years", nargs="*", type=int, help="Restrict to these years.")
    args = parser.parse_args()

    feature = feature_for(DISTRICTS, args.pcode)
    if feature is None:
        raise SystemExit(f"No district with P-code {args.pcode}.")
    properties = feature["properties"]
    province = (feature_for(PROVINCES, properties["parent"]) or {}).get("properties", {}).get("nameEn", "")

    ee = initialise()
    print(f"Earth Engine ready · project {PROJECT}")

    region = ee.Geometry(feature["geometry"])
    try:
        collection = ee.ImageCollection(args.asset)
        size = collection.size().getInfo()
    except Exception as error:
        raise SystemExit(
            f"Could not open {args.asset}: {str(error).strip()[:200]}\n"
            "  If it is a community-catalogue asset the id may have moved. Alternatives that\n"
            "  carry comparable land cover:\n"
            "      ESA/WorldCover/v200                      (10 m, 2021)\n"
            "      GOOGLE/DYNAMICWORLD/V1                   (10 m, near-real-time)\n"
            "      COPERNICUS/Landcover/100m/Proba-V-C3/Global"
        ) from error

    print(f"  {args.asset}: {size} images")
    images = collection.filterBounds(region)

    # One reduction per year. frequencyHistogram counts pixels per class code
    # server-side; only the counts come back.
    years = args.years or sorted({
        int(stamp[:4]) for stamp in images.aggregate_array("system:time_start")
        .map(lambda t: ee.Date(t).format("YYYY")).getInfo()
    } if size else set())
    if not years:
        years = list(range(2017, 2024))

    per_year: OrderedDict[int, dict] = OrderedDict()
    for year in years:
        annual = images.filterDate(f"{year}-01-01", f"{year + 1}-01-01")
        if annual.size().getInfo() == 0:
            print(f"  {year}: no image")
            continue
        mosaic = annual.mosaic().clip(region)
        histogram = mosaic.reduceRegion(
            reducer=ee.Reducer.frequencyHistogram(),
            geometry=region,
            scale=args.scale,
            maxPixels=1e10,
            bestEffort=False,
        ).getInfo()
        band = next(iter(histogram.values())) or {}
        counts = {int(float(code)): int(count) for code, count in band.items()}
        total = sum(counts.values())
        pixel_area = args.scale ** 2
        per_year[year] = {
            "pixels": total,
            "areaKm2": round(total * pixel_area / 1e6, 3),
            "classes": {CLASSES.get(code, str(code)): {
                "pixels": count,
                "km2": round(count * pixel_area / 1e6, 3),
                "percent": round(count / total * 100, 2) if total else 0,
            } for code, count in sorted(counts.items(), key=lambda kv: -kv[1])},
        }
        print(f"  {year}: {total:,} pixels ({total * pixel_area / 1e6:,.1f} km²)")

    if not per_year:
        raise SystemExit("No year produced a histogram; check the asset and the region.")

    first, last = min(per_year), max(per_year)
    labels = sorted({label for year in per_year.values() for label in year["classes"]},
                    key=lambda l: -per_year[last]["classes"].get(l, {}).get("km2", 0))

    print(f"\n{'CLASS':22}", end="")
    for year in per_year:
        print(f"{year:>10}", end="")
    print(f"{'CHANGE':>12}")
    print("-" * (22 + 10 * len(per_year) + 12))
    changes = {}
    for label in labels:
        print(f"{label:22}", end="")
        for year in per_year:
            print(f"{per_year[year]['classes'].get(label, {}).get('km2', 0):>10.1f}", end="")
        delta = (per_year[last]["classes"].get(label, {}).get("km2", 0)
                 - per_year[first]["classes"].get(label, {}).get("km2", 0))
        changes[label] = round(delta, 3)
        print(f"{delta:>+12.1f}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    target = OUTPUT_DIR / f"landcover-gee-{args.pcode}.json"
    target.write_text(json.dumps({
        "version": "1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engine": {"platform": "Google Earth Engine", "project": PROJECT,
                   "asset": args.asset, "scale": args.scale,
                   "reducer": "frequencyHistogram, computed server-side"},
        "district": {"pcode": args.pcode, "name": properties["nameEn"], "province": province},
        "years": per_year,
        "changeKm2": changes,
    }, ensure_ascii=False, indent=2), encoding="utf8")
    print(f"\n  -> {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
