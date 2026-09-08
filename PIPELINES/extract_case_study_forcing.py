"""Extract historical ERA5-Land and CHIRPS station cells for observed months.

Requires an already authenticated Earth Engine session. Existing output is only
replaced after a complete successful retrieval; no credentials are read or printed.
"""
from __future__ import annotations

import argparse
import calendar
import json
from datetime import datetime, timezone
from pathlib import Path

from build_chirchik_case_studies import DATA, OUT, read_csv, write_csv, write_json, period

PRODUCTS = {
    "era5-land": ("ECMWF/ERA5_LAND/MONTHLY_AGGR", 11132),
    "chirps-v3": ("UCSB-CHC/CHIRPS/V3/PENTAD", 5566),
    "chirts-midrange": ("UCSB-CHG/CHIRTS/DAILY", 5566),
}
FIELDS = ["station_id", "period", "variable", "value", "unit", "product", "spatial_support",
          "longitude", "latitude", "source_asset", "source_images", "scale_m", "retrieved_at"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default="ee-sabitovty")
    parser.add_argument("--output", type=Path, default=OUT / "station-product-monthly.csv")
    args = parser.parse_args()
    import ee
    try:
        ee.Initialize(project=args.project)
    except Exception as error:
        raise SystemExit("Earth Engine credentials are unavailable. Run `earthengine authenticate` locally, then retry cases:forcing.") from error
    ee.data.setDeadline(120000)
    observations = read_csv(DATA / "pskem-station-monthly.csv")
    links = [r for r in read_csv(DATA / "pskem-station-basin-links.csv") if r["station_role"] == "meteorological"]
    points = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([float(r["longitude"]), float(r["latitude"])]),
                                            {"station_id": r["station_id"]}) for r in links])
    coordinates = {r["station_id"]: r for r in links}
    wanted = {(r["station_id"], period(r), r["variable"]) for r in observations
              if r["variable"] in ["air_temperature_mean", "precipitation_total"]}
    years = sorted({int(p[:4]) for _, p, _ in wanted})
    retrieved = datetime.now(timezone.utc).isoformat()
    rows = []
    for product, (asset, scale) in PRODUCTS.items():
        projection_info = ee.ImageCollection(asset).first().select(0).projection().getInfo()
        for year in years:
            if product == "chirts-midrange" and year > 2016:
                continue
            collection = ee.ImageCollection(asset).filterDate(f"{year}-01-01", f"{year + 1}-01-01")

            def reduce_month(m):
                begin = ee.Date.fromYMD(year, m, 1)
                source = collection.filterDate(begin, begin.advance(1, "month"))
                if product == "era5-land":
                    image = source.first()
                    transformed = image.select("temperature_2m").subtract(273.15).rename("air_temperature_mean").addBands(
                        image.select("total_precipitation_sum").multiply(1000).rename("precipitation_total"))
                elif product == "chirps-v3":
                    transformed = source.select("precipitation").sum().rename("precipitation_total")
                else:
                    transformed = source.map(lambda image: image.select("minimum_temperature").add(
                        image.select("maximum_temperature")).divide(2).rename("air_temperature_mean")).mean()
                # Explicit native projection/transform preserves the original cell grid;
                # no resampling to the finer basin geometry or a synthetic station elevation.
                return transformed.reduceRegions(collection=points, reducer=ee.Reducer.first(),
                    crs=projection_info['crs'], crsTransform=projection_info['transform']).map(
                    lambda f: f.set({"period": begin.format("YYYY-MM"), "image_count": source.size(),
                                     "source_images": source.aggregate_array("system:index")})).map(lambda f: f.setGeometry(None))

            cache = DATA.parents[2] / "WORKSPACE/derived/chirchik-cache" / f"stations-{product}-{year}-v2.json"
            if cache.exists():
                features = json.loads(cache.read_text(encoding="utf-8"))
            else:
                features = ee.FeatureCollection(ee.List.sequence(1, 12).map(reduce_month)).flatten().getInfo()["features"]
                write_json(cache, features)
            for f in features:
                props = f["properties"]
                expected = (1 if product == "era5-land" else 6 if product == "chirps-v3" else
                            calendar.monthrange(year, int(props['period'][-2:]))[1])
                if props["image_count"] != expected:
                    raise RuntimeError(f"Incomplete {product} input in {props['period']}; output not replaced")
                station = props["station_id"]
                for variable, unit in [("air_temperature_mean", "°C"), ("precipitation_total", "mm")]:
                    if (station, props["period"], variable) not in wanted or (product == "chirps-v3" and variable != "precipitation_total") or (product == "chirts-midrange" and variable != "air_temperature_mean"):
                        continue
                    rows.append({"station_id": station, "period": props["period"], "variable": variable,
                                 "value": props.get(variable, ""), "unit": unit, "product": product,
                                 "spatial_support": "station_grid_cell", "longitude": coordinates[station]["longitude"],
                                 "latitude": coordinates[station]["latitude"], "source_asset": asset,
                                 "source_images": "|".join(props["source_images"]), "scale_m": scale, "retrieved_at": retrieved})
            print(f"{product} {year}: retrieved station cells", flush=True)
    rows.sort(key=lambda r: (r["product"], r["station_id"], r["period"], r["variable"]))
    expected_rows = len(wanted) + sum(v == "precipitation_total" for _, _, v in wanted) + sum(v == "air_temperature_mean" and p <= "2016-12" for _, p, v in wanted)
    if len(rows) != expected_rows:
        raise RuntimeError(f"Expected {expected_rows} station-product rows, received {len(rows)}; output not replaced")
    temporary = args.output.with_suffix(".csv.tmp")
    write_csv(temporary, rows, FIELDS)
    temporary.replace(args.output)
    write_json(args.output.with_suffix(".manifest.json"), {"retrieved_at": retrieved, "rows": len(rows),
        "products": PRODUCTS, "method": "Native projection and transform; station cell; monthly ERA5 states/sums and six CHIRPS pentads.",
        "chirts_note": "CHIRTS is the monthly average of daily (Tmin+Tmax)/2, a midrange proxy that can differ from station mean-temperature observing conventions. Record ends 2016.",
        "independence": "Station assimilation/contribution not yet audited; no fitted bias correction."})
    print(f"Wrote {len(rows)} values to {args.output}")


if __name__ == "__main__":
    main()
