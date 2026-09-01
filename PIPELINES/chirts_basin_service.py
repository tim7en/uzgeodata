"""Monthly temperature and humidity statistics per basin from CHIRTS-daily.

CHIRTS blends infrared satellite temperature with station observations at 0.05°,
giving daily Tmax and Tmin plus four derived humidity variables. It is the
temperature counterpart to CHIRPS and shares its grid, which makes the two
directly comparable basin by basin.

Two things about it decide how it is stored.

**It is closed.** The Earth Engine record runs 1983-01-01 to 2016-12-31 and stops
— zero images after. CHIRTS cannot answer what the weather is doing now, and
nothing built on it should imply otherwise. Its role is historical: a
station-blended baseline against which the coarser, still-running products can be
judged, and a record of how heat behaved over thirty-four years.

**Daily matters, but daily rows do not.** What a daily record gives that a monthly
one cannot is counts — how many days passed 35 °C, how hot the hottest day got.
Those are computed from the daily images server-side and stored monthly, which
keeps the information and drops 3.2 million rows nobody would read.

One trap is encoded deliberately: `heat_index` is in **degrees Fahrenheit** while
every other band is metric, and it is computed from the daily *mean* temperature
rather than Tmax. Tashkent on a mild day reads a mean of 68.3 °F and a heat index
of 68.29; Kolkata at 78% humidity reads 87.4 °F and 102.88. Treating that column
as Celsius, or as a maximum, would be wrong in two different ways at once.

    python PIPELINES/chirts_basin_service.py --start 2014-01 --end 2016-12
    python PIPELINES/chirts_basin_service.py --start 1983-01 --end 2016-12   # the whole record

Basin level is chosen per product, from the source grid — not once for the whole
ontology. A basin smaller than the pixel it samples cannot hold a value of its
own; it inherits its neighbour's. CFSv2 is 34.8 km, so a level-12 basin covers a
tenth of a pixel and level 7 is as fine as it goes. CHIRPS and CHIRTS are 5.6 km,
where a level-12 basin covers about four pixels, so level 12 is honest for them —
and costs no more, because a reduction is priced by the raster it reads rather
than by the number of polygons laid over it.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parent.parent
BASINS = ROOT / "PUBLISHED" / "data" / "hydrography" / "basins.geojson"
from ontology_paths import dataset_dir
OUTPUT = dataset_dir("CHIRTS_BASIN_MONTHLY", "ATMOSPHERE") / "chirts-basin-monthly.csv"

PROJECT = "ee-sabitovty"
ASSET = "UCSB-CHG/CHIRTS/DAILY"
SCALE = 5566
RECORD = ("1983-01", "2016-12")

# Thresholds for the day counts. 35 °C is where field labour and many crops start
# to suffer; 40 °C is the extreme that matters for mortality and irrigation demand.
HOT_DAY_THRESHOLDS = (35, 40)

UNITS = {
    "tmax_mean": "degC", "tmin_mean": "degC", "tmax_absolute": "degC",
    "tmin_absolute": "degC", "vpd_mean": "kPa", "rh_mean": "percent",
    "heat_index_max": "degF",
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
    parser.add_argument("--start", default="2014-01", help="First month, YYYY-MM.")
    parser.add_argument("--end", default="2016-12", help="Last month, YYYY-MM.")
    args = parser.parse_args()

    if args.end > RECORD[1] or args.start < RECORD[0]:
        print(f"note: CHIRTS runs {RECORD[0]} to {RECORD[1]} and stops there; "
              "months outside that will return nothing.")

    try:
        import ee
        ee.Initialize(project=PROJECT)
        ee.Number(1).getInfo()
    except Exception as error:
        raise SystemExit(f"Earth Engine unavailable: {str(error).strip()[:150]}\n"
                         f"  Run: earthengine authenticate --project {PROJECT}") from error

    document = json.loads(BASINS.read_text(encoding="utf8"))
    collection = ee.FeatureCollection([
        ee.Feature(ee.Geometry(f["geometry"]), {"basin": int(f["properties"]["HYBAS_ID"])})
        for f in document["features"]])
    source = ee.ImageCollection(ASSET)

    done = set()
    if OUTPUT.exists():
        with OUTPUT.open(encoding="utf8", newline="") as handle:
            done = {(r["year"], r["month"]) for r in csv.DictReader(handle)}
    todo = [(y, m) for y, m in months(args.start, args.end) if (str(y), str(m)) not in done]

    print(f"CHIRTS-daily · {len(document['features'])} level-12 basins · {len(todo)} months to measure")
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
                print(f"  {year}-{month:02d}: no images (outside the record)", flush=True)
                continue

            tmax = daily.select("maximum_temperature")
            tmin = daily.select("minimum_temperature")
            # The day counts are the reason for reading a daily product at all:
            # a monthly mean cannot say how many days crossed a threshold.
            stack = (tmax.mean().rename("tmax_mean")
                     .addBands(tmin.mean().rename("tmin_mean"))
                     .addBands(tmax.max().rename("tmax_absolute"))
                     .addBands(tmin.min().rename("tmin_absolute"))
                     .addBands(daily.select("vapor_pressure_deficit").mean().rename("vpd_mean"))
                     .addBands(daily.select("relative_humidity").mean().rename("rh_mean"))
                     .addBands(daily.select("heat_index").max().rename("heat_index_max")))
            for threshold in HOT_DAY_THRESHOLDS:
                stack = stack.addBands(
                    tmax.map(lambda image, t=threshold: image.gte(t)).sum()
                    .rename(f"days_tmax_ge_{threshold}"))

            try:
                result = stack.reduceRegions(
                    collection=collection, reducer=ee.Reducer.mean(), scale=SCALE).getInfo()
            except Exception as error:
                print(f"  ! {year}-{month:02d}: {str(error).strip()[:100]}", flush=True)
                continue

            for feature in result["features"]:
                properties = feature["properties"]
                for name, unit in UNITS.items():
                    value = properties.get(name)
                    if value is None:
                        continue
                    # A day count is a count: averaging it across a basin's pixels
                    # gives a fraction, which is meaningful but must not pretend to
                    # be an integer number of days.
                    quality = "ok" if -90 <= value <= 200 else "implausible"
                    writer.writerow([properties["basin"], year, month, count,
                                     name, round(value, 4), unit, quality])
                    rows += 1
            handle.flush()
            if position % 6 == 0 or position == len(todo):
                rate = (time.time() - started) / position
                print(f"  {year}-{month:02d} · {position}/{len(todo)} · {rate:.0f}s each · "
                      f"{(len(todo) - position) * rate / 60:.0f} min left", flush=True)

    print(f"\n  {rows:,} observations -> {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
