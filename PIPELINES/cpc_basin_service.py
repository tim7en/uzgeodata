"""Monthly temperature statistics per basin from CPC Global Unified Temperature.

A gauge-based analysis on a half-degree grid, built from 6,000 to 7,000 GTS
station reports and running 1979 to within days of the present. That combination
is rare: CHIRTS is station-blended but stops at 2016, and CFSv2 runs to the
present but is model output. CPC is the only station-based temperature record
here that is both long and still current, which makes it the natural yardstick
for the other two.

It is read at basin level 6. A half-degree cell at this latitude is 55.3 by
41.7 km — about 2,305 km², nearly twice a CFSv2 pixel — so a level-7 basin covers
1.2 cells and cannot hold a value of its own, while a level-6 basin covers 4.3.
That makes three grains in the ontology, each derived from its product's grid
rather than chosen once: level 6 here, level 7 for CFSv2, level 12 for the 5.6 km
CHIRPS and CHIRTS.

The bands carry their own quality signal, which is unusual and worth using:
`nmax` and `nmin` give the number of stations that informed each cell. A cell
with no stations is interpolated from somewhere else, and a monthly mean built
from such cells deserves to be read differently from one built over a dense
network. That count is stored alongside the temperatures rather than discarded.

Because level 6 is only 92 basins, the whole record is affordable — which is why
this defaults to the full span rather than a recent slice.

    python PIPELINES/cpc_basin_service.py                       # 1979 to now
    python PIPELINES/cpc_basin_service.py --start 2020-01 --end 2026-08
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASINS = ROOT / "PUBLISHED" / "data" / "review" / "basinatlas" / "basinatlas_uz_lev06.geojson"
OUTPUT = (ROOT / "PUBLISHED" / "data" / "ontology" / "1_ATMOSPHERE"
          / "1.6_CPC_BASIN_MONTHLY" / "cpc-basin-monthly.csv")

PROJECT = "ee-sabitovty"
ASSET = "NOAA/CPC/Temperature"
SCALE = 55660
RECORD_START = "1979-01"

HOT_DAY_THRESHOLDS = (35, 40)
FROST_THRESHOLD = 0

UNITS = {
    "tmax_mean": "degC", "tmin_mean": "degC", "tmax_absolute": "degC",
    "tmin_absolute": "degC", "stations_max_mean": "count", "stations_min_mean": "count",
    "days_frost": "days",
    **{f"days_tmax_ge_{t}": "days" for t in HOT_DAY_THRESHOLDS},
}


def months(start: str, end: str):
    sy, sm = (int(p) for p in start.split("-"))
    ey, em = (int(p) for p in end.split("-"))
    year, month = sy, sm
    while (year, month) <= (ey, em):
        yield year, month
        month = month + 1 if month < 12 else 1
        if month == 1:
            year += 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", default=RECORD_START, help="First month, YYYY-MM.")
    parser.add_argument("--end", default=None, help="Last month, YYYY-MM. Default: the record's end.")
    args = parser.parse_args()

    try:
        import ee
        ee.Initialize(project=PROJECT)
        ee.Number(1).getInfo()
    except Exception as error:
        raise SystemExit(f"Earth Engine unavailable: {str(error).strip()[:150]}\n"
                         f"  Run: earthengine authenticate --project {PROJECT}") from error

    source = ee.ImageCollection(ASSET)
    if args.end is None:
        # Ask the collection where it stops rather than assuming; it advances daily.
        latest = source.aggregate_max("system:time_start").getInfo()
        import datetime as dt
        end_date = dt.datetime.utcfromtimestamp(latest / 1000)
        # The final month is usually partial, so stop at the last complete one.
        args.end = f"{end_date.year}-{end_date.month - 1:02d}" if end_date.month > 1 \
            else f"{end_date.year - 1}-12"
        print(f"record ends {end_date:%Y-%m-%d}; taking complete months to {args.end}")

    document = json.loads(BASINS.read_text(encoding="utf8"))
    collection = ee.FeatureCollection([
        ee.Feature(ee.Geometry(f["geometry"]), {"basin": int(f["properties"]["HYBAS_ID"])})
        for f in document["features"]])

    done = set()
    if OUTPUT.exists():
        with OUTPUT.open(encoding="utf-8-sig", newline="") as handle:
            done = {(r["year"], r["month"]) for r in csv.DictReader(handle)}
    todo = [(y, m) for y, m in months(args.start, args.end) if (str(y), str(m)) not in done]

    print(f"CPC · {len(document['features'])} level-6 basins · {len(todo)} months to measure")
    if not todo:
        print("  nothing to do")
        return

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fresh = not OUTPUT.exists()
    started, rows = time.time(), 0
    with OUTPUT.open("a", encoding="utf8", newline="") as handle:
        writer = csv.writer(handle)
        if fresh:
            writer.writerow(["basin_id", "year", "month", "days_in_record",
                             "variable", "value", "unit", "quality"])
        for position, (year, month) in enumerate(todo, start=1):
            start = ee.Date.fromYMD(year, month, 1)
            daily = source.filterDate(start, start.advance(1, "month"))
            count = daily.size().getInfo()
            if count == 0:
                print(f"  {year}-{month:02d}: no images", flush=True)
                continue

            tmax = daily.select("tmax")
            tmin = daily.select("tmin")

            def flags(image):
                """Every threshold test for one day, as bands of a single image.

                Mapping the collection once and summing the result costs one pass
                over the month's images. Doing it per threshold — three maps, three
                sums — cost three, which is most of why a month took ninety seconds.
                """
                hot = [image.select("tmax").gte(t).rename(f"days_tmax_ge_{t}")
                       for t in HOT_DAY_THRESHOLDS]
                frost = image.select("tmin").lt(FROST_THRESHOLD).rename("days_frost")
                combined = frost
                for band in hot:
                    combined = combined.addBands(band)
                return combined

            counts = daily.map(flags).sum()
            stack = (tmax.mean().rename("tmax_mean")
                     .addBands(tmin.mean().rename("tmin_mean"))
                     .addBands(tmax.max().rename("tmax_absolute"))
                     .addBands(tmin.min().rename("tmin_absolute"))
                     .addBands(daily.select("nmax").mean().rename("stations_max_mean"))
                     .addBands(daily.select("nmin").mean().rename("stations_min_mean"))
                     .addBands(counts))

            try:
                result = stack.reduceRegions(
                    collection=collection, reducer=ee.Reducer.mean(), scale=SCALE).getInfo()
            except Exception as error:
                print(f"  ! {year}-{month:02d}: {str(error).strip()[:100]}", flush=True)
                continue

            for feature in result["features"]:
                properties = feature["properties"]
                # A month whose cells saw no station at all is interpolation, not
                # observation, and is marked so a reader can exclude it.
                stations = properties.get("stations_max_mean")
                sparse = stations is not None and stations < 0.05
                for name, unit in UNITS.items():
                    value = properties.get(name)
                    if value is None:
                        continue
                    if not -90 <= value <= 200:
                        quality = "implausible"
                    elif sparse and name.startswith(("tmax", "tmin", "days")):
                        quality = "ok-interpolated"
                    else:
                        quality = "ok"
                    writer.writerow([properties["basin"], year, month, count,
                                     name, round(value, 4), unit, quality])
                    rows += 1
            handle.flush()
            if position % 24 == 0 or position == len(todo):
                rate = (time.time() - started) / position
                print(f"  {year}-{month:02d} · {position}/{len(todo)} · {rate:.1f}s each · "
                      f"{(len(todo) - position) * rate / 60:.0f} min left", flush=True)

    print(f"\n  {rows:,} observations -> {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
