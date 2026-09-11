"""Compare the products against the NSIDC Central Asia network.

python PIPELINES/compare_nsidc_products.py

The national archive placed four stations above 1500 m, which was too thin a base for
any statement about mountains. This repeats the comparison against Williams and
Konovalov's compilation, which puts around fifty inside the two river systems, and
which carries its own coordinates so nothing rests on the name crosswalk.

The two references do not define precipitation the same way. The national gauges are
uncorrected; these are corrected for gauge type and for wetting, though not for wind.
A gauge correction raises recorded totals, so a product's apparent wet bias should
fall when measured against this reference -- and the size of that fall says how much
of the bias was ever the product's rather than the gauge's.
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
from PIPELINES.compare_station_products import ELEVATION_BANDS, ESTIMATES, band_of, metrics

STATIONS = ROOT / "PUBLISHED/data/hydromet/nsidc-central-asia-stations.csv"
OBSERVATIONS = ROOT / "PUBLISHED/data/hydromet/nsidc-central-asia-monthly.csv"
SERIES = ROOT / "PUBLISHED/data/hydromet/nsidc-product-series.csv"
REPORT = ROOT / "PUBLISHED/data/hydromet/nsidc-product-comparison.json"
WINDOW = (1980, 2003)          # where the products and this archive overlap
MOUNTAIN_BANDS = ((1500, 2500), (2500, 5000))


def build():
    sites = {r["station_id"]: r for r in read(STATIONS) if r["in_domain"] == "True"}
    values = {}
    for row in read(SERIES):
        if row["value"]:
            values[(row["station_id"], row["product"], row["measure"],
                    int(row["year"]), int(row["month"]))] = float(row["value"])

    rows = []
    for row in read(OBSERVATIONS):
        variable, station = row["variable"], row["station_id"]
        year, month = int(row["year"]), int(row["month"])
        site = sites.get(station)
        if variable not in ESTIMATES or site is None or not WINDOW[0] <= year <= WINDOW[1]:
            continue
        elevation = float(site["elevation_m"])
        for product, measures in ESTIMATES[variable].items():
            parts = [values.get((station, product, m, year, month)) for m in measures]
            if any(p is None for p in parts):
                continue
            modelled = sum(parts) / len(parts)
            rows.append({"station_id": station, "variable": variable, "product": product,
                         "observed": float(row["value"]), "estimated": modelled,
                         "difference": modelled - float(row["value"]),
                         "elevation_band": band_of(elevation),
                         "system_id": site["system_id"]})

    report = {"generated_at": utc_now(), "window": list(WINDOW), "pairs": len(rows),
              "stations": len({r["station_id"] for r in rows}), "by_variable": {}}
    for variable in ESTIMATES:
        subset = [r for r in rows if r["variable"] == variable]
        if not subset:
            continue
        entry = {"overall": {}, "by_elevation": {}, "by_system": {}, "mountain_only": {}}
        for product in sorted({r["product"] for r in subset}):
            product_rows = [r for r in subset if r["product"] == product]
            entry["overall"][product] = metrics(product_rows)
            entry["by_elevation"][product] = {
                band: metrics([r for r in product_rows if r["elevation_band"] == band])
                for band in {r["elevation_band"] for r in product_rows}}
            entry["by_elevation"][product] = {k: v for k, v in entry["by_elevation"][product].items() if v}
            entry["by_system"][product] = {
                system: metrics([r for r in product_rows if r["system_id"] == system])
                for system in {r["system_id"] for r in product_rows}}
            entry["by_system"][product] = {k: v for k, v in entry["by_system"][product].items() if v}
            mountains = [r for r in product_rows
                         if r["elevation_band"] in {band_of(low) for low, _ in MOUNTAIN_BANDS}]
            entry["mountain_only"][product] = metrics(mountains)
        report["by_variable"][variable] = entry

    report["reference"] = {
        "precipitation": "Corrected for gauge type and wetting, not for wind. Wind is the "
                         "largest correction for snow, so these totals still understate winter "
                         "precipitation at exposed sites and a wet bias measured here remains "
                         "an upper bound on the product's own error.",
        "coverage": "Stations carry their own coordinates and elevation; no name crosswalk is "
                    "involved and no placement is inferred.",
        "window": "The archive ends in 2003, so this extends the comparison upward in "
                  "elevation and backward in time, not forward.",
    }
    write_json(REPORT, report)
    return report


def main():
    report = build()
    print(json.dumps({"pairs": report["pairs"], "stations": report["stations"],
                      "mountain_only": {v: e["mountain_only"]
                                        for v, e in report["by_variable"].items()}},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
