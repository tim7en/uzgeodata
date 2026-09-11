"""Compare what stations recorded with what the gridded products estimated.

python PIPELINES/compare_station_products.py

Pairs every station month with the product estimate at that station's own grid cell,
and reports the difference by station, by elevation band and by land cover, so that
where a product fails is visible rather than averaged away.

Three comparisons are not equally sound, and the difference matters more than the
numbers:

* Precipitation is like for like. A monthly total in millimetres, both sides.
* Air temperature is not. TerraClimate publishes daily maxima and minima, and their
  midpoint is not the mean of a day's readings; the station mean comes from fixed
  synoptic hours. ERA5-Land's 2 m temperature is a true mean, so it is the fairer of
  the two, and the comparison of TerraClimate carries a known method difference on
  top of whatever error it has.
* Soil temperature is the weakest. ERA5-Land level 1 spans the top seven centimetres
  of soil; the depth the station recorded is not stated in the delivery. A difference
  here may be entirely a difference of depth.

A product and a thermometer also disagree because they measure different things: a
cell kilometres across against an instrument in a yard. That is a difference of
support, not an error, and it does not shrink with a better product.
"""
from __future__ import annotations
import collections
import csv
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core.runtime import utc_now, write_json
from PIPELINES.build_station_crosswalk import read
from PIPELINES.extract_station_products import OUT as SERIES
from PIPELINES.verify_station_crosswalk import VERIFIED

OBSERVATIONS = ROOT / "PUBLISHED/data/hydromet/station-monthly.csv"
CONTEXT = ROOT / "PUBLISHED/data/case-studies/regional-station-context.csv"
PAIRS = ROOT / "PUBLISHED/data/hydromet/station-product-pairs.csv"
REPORT = ROOT / "PUBLISHED/data/hydromet/station-product-comparison.json"

# station variable -> how each product estimates it
ESTIMATES = {
    "air_temperature_mean": {
        "era5_land": ("air_temperature_mean",),
        "terraclimate": ("air_temperature_max", "air_temperature_min"),   # midpoint, not a mean
    },
    "precipitation_total": {
        "era5_land": ("precipitation_total",),
        "terraclimate": ("precipitation_total",),
    },
    "soil_temperature_mean": {
        "era5_land": ("soil_temperature_mean",),
    },
}
ELEVATION_BANDS = ((0, 500), (500, 1000), (1000, 1500), (1500, 4000))
MINIMUM_PAIRS = 24


def product_values(path=SERIES):
    """(station, product, measure, year, month) -> value."""
    values = {}
    with Path(path).open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["value"]:
                values[(row["station_id"], row["product"], row["measure"],
                        int(row["year"]), int(row["month"]))] = float(row["value"])
    return values


def estimate(values, station, product, year, month, measures):
    parts = [values.get((station, product, m, year, month)) for m in measures]
    if any(p is None for p in parts):
        return None
    return sum(parts) / len(parts)


def band_of(elevation):
    for low, high in ELEVATION_BANDS:
        if low <= elevation < high:
            return f"{low}-{high} m"
    return "unknown"


def pair(observations, values, sites):
    """Every station month that a product also estimated."""
    rows = []
    for row in observations:
        variable = row["variable"]
        if variable not in ESTIMATES or row["quality"] != "ok" or not row["year"].isdigit():
            continue
        station, year, month = row["station_id"], int(row["year"]), int(row["month"])
        site = sites.get(station)
        if site is None:
            continue
        for product, measures in ESTIMATES[variable].items():
            modelled = estimate(values, station, product, year, month, measures)
            if modelled is None:
                continue
            rows.append({
                "station_id": station, "station_name": site["name"], "variable": variable,
                "product": product, "year": year, "month": month,
                "observed": float(row["value"]), "estimated": modelled,
                "difference": modelled - float(row["value"]),
                "elevation_m": site["elevation_m"], "elevation_band": band_of(site["elevation_m"]),
                "landcover": site["landcover"], "verification": site["verification"]})
    return rows


def metrics(rows):
    """Bias, spread and agreement for one set of pairs."""
    if len(rows) < MINIMUM_PAIRS:
        return None
    differences = [r["difference"] for r in rows]
    observed = [r["observed"] for r in rows]
    estimated = [r["estimated"] for r in rows]
    bias = statistics.mean(differences)
    result = {
        "pairs": len(rows), "stations": len({r["station_id"] for r in rows}),
        "bias": bias,
        "mean_absolute_error": statistics.mean(abs(d) for d in differences),
        "root_mean_square_error": math.sqrt(statistics.mean(d * d for d in differences)),
        "observed_mean": statistics.mean(observed), "estimated_mean": statistics.mean(estimated),
    }
    if len(rows) > 2 and statistics.pstdev(observed) > 0 and statistics.pstdev(estimated) > 0:
        mo, me = statistics.mean(observed), statistics.mean(estimated)
        cov = sum((o - mo) * (e - me) for o, e in zip(observed, estimated)) / len(rows)
        result["correlation"] = cov / (statistics.pstdev(observed) * statistics.pstdev(estimated))
    return result


def grouped(rows, key):
    out = {}
    buckets = collections.defaultdict(list)
    for row in rows:
        buckets[key(row)].append(row)
    for name, group in sorted(buckets.items(), key=lambda kv: str(kv[0])):
        found = metrics(group)
        if found:
            out[str(name)] = found
    return out


def build():
    sites = {}
    context = {row["station_id"]: row for row in read(CONTEXT)}
    for row in read(VERIFIED):
        if row["match_status"] == "matched_by_name" and row["elevation_m"]:
            detail = context.get(row["network_entity_id"], {})
            sites[row["observation_station_id"]] = {
                "name": row["observation_name"], "elevation_m": float(row["elevation_m"]),
                "landcover": detail.get("landcover_end", "") or "unknown",
                "verification": row.get("verification", "not_checked")}

    rows = pair(read(OBSERVATIONS), product_values(), sites)
    PAIRS.parent.mkdir(parents=True, exist_ok=True)
    with PAIRS.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    report = {"generated_at": utc_now(), "pairs": len(rows),
              "stations": len({r["station_id"] for r in rows}),
              "years": [min(r["year"] for r in rows), max(r["year"] for r in rows)],
              "by_variable": {}}
    for variable in ESTIMATES:
        subset = [r for r in rows if r["variable"] == variable]
        if not subset:
            continue
        entry = {"overall": grouped(subset, lambda r: r["product"]),
                 "by_elevation": {}, "by_landcover": {}}
        for product in {r["product"] for r in subset}:
            product_rows = [r for r in subset if r["product"] == product]
            entry["by_elevation"][product] = grouped(product_rows, lambda r: r["elevation_band"])
            entry["by_landcover"][product] = grouped(product_rows, lambda r: r["landcover"])
        report["by_variable"][variable] = entry

    report["caveats"] = {
        "support": "A grid cell kilometres across is compared with an instrument in a yard. "
                   "Part of every difference here is that mismatch and will not shrink with a "
                   "better product.",
        "air_temperature": "TerraClimate is the midpoint of daily maximum and minimum, which is "
                           "not the mean of a day's readings; ERA5-Land is a true mean. The "
                           "TerraClimate comparison therefore carries a method difference as well.",
        "soil_temperature": "ERA5-Land level 1 is the top seven centimetres. The depth the "
                            "station recorded is not stated in the delivery, so a difference "
                            "here may be entirely a difference of depth.",
        "identity": "Stations were located by a name crosswalk that one independent check did "
                    "not contradict. Three stations departed from that check and are kept in "
                    "the pairs with their verification status attached.",
    }
    write_json(REPORT, report)
    return report


def main():
    report = build()
    print(json.dumps({"pairs": report["pairs"], "stations": report["stations"],
                      "years": report["years"],
                      "overall": {v: e["overall"] for v, e in report["by_variable"].items()}},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
