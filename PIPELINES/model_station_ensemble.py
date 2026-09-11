"""Test whether the products can be combined and corrected into something better.

python PIPELINES/model_station_ensemble.py

The comparison showed two things worth acting on: the products disagree, and their
error is not constant — ERA5-Land runs colder and much wetter as elevation rises,
while TerraClimate stays flatter. Both are openings. A combination can beat either
input, and an error that varies with a known quantity can be corrected against it.

Five candidates are tested against the stations:

* each product alone, as the baseline anything else has to beat;
* their plain mean, which needs no fitting at all;
* an inverse-error weighted mean, whose weights are fitted;
* an elevation-corrected mean, which removes the part of the bias that tracks height.

Every fitted candidate is scored by leaving one station out at a time: the model is
fitted without that station and then asked about it. Scoring a fitted correction on
the stations that fitted it measures memory, not skill, and would make the last two
candidates look better than they are.

What this cannot establish: the stations are unevenly spread, with thirty-six sites
below 500 m and four above 1500 m, so a mountain result rests on four sites and the
correction is only as good as their representativeness. And a correction fitted to
station points does not automatically transfer to a basin mean, which is a different
spatial support.
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
from PIPELINES.compare_station_products import PAIRS

REPORT = ROOT / "PUBLISHED/data/hydromet/station-ensemble.json"
MINIMUM_STATIONS = 8


def load(path=PAIRS):
    """Station months where both products offered an estimate, keyed for pairing."""
    rows = collections.defaultdict(dict)
    with Path(path).open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            key = (row["variable"], row["station_id"], int(row["year"]), int(row["month"]))
            rows[key][row["product"]] = float(row["estimated"])
            rows[key]["observed"] = float(row["observed"])
            rows[key]["elevation"] = float(row["elevation_m"])
    return rows


def cases(rows, variable, products):
    out = []
    for (name, station, year, month), entry in rows.items():
        if name != variable or not all(p in entry for p in products):
            continue
        out.append({"station": station, "observed": entry["observed"],
                    "elevation": entry["elevation"],
                    **{p: entry[p] for p in products}})
    return out


def score(pairs):
    """Bias, mean absolute error and root mean square error for one candidate."""
    errors = [p["predicted"] - p["observed"] for p in pairs]
    return {"pairs": len(errors), "bias": statistics.mean(errors),
            "mean_absolute_error": statistics.mean(abs(e) for e in errors),
            "root_mean_square_error": math.sqrt(statistics.mean(e * e for e in errors))}


def fit_weights(training, products):
    """Weights inversely proportional to each product's mean square error."""
    inverse = {}
    for product in products:
        error = statistics.mean((c[product] - c["observed"]) ** 2 for c in training)
        inverse[product] = 1.0 / error if error > 0 else 0.0
    total = sum(inverse.values())
    return {p: (w / total if total else 1.0 / len(products)) for p, w in inverse.items()}


def fit_elevation(training, products):
    """Straight line through the mean error against elevation."""
    points = [(c["elevation"], statistics.mean(c[p] for p in products) - c["observed"])
              for c in training]
    mean_x = statistics.mean(x for x, _ in points)
    mean_y = statistics.mean(y for _, y in points)
    spread = sum((x - mean_x) ** 2 for x, _ in points)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / spread if spread else 0.0
    return mean_y - slope * mean_x, slope


def evaluate(all_cases, products):
    """Fixed candidates scored directly; fitted candidates by leaving a station out."""
    stations = sorted({c["station"] for c in all_cases})
    if len(stations) < MINIMUM_STATIONS:
        return None

    results = {}
    for product in products:
        results[product] = score([{"predicted": c[product], "observed": c["observed"]}
                                  for c in all_cases])
    results["plain_mean"] = score([
        {"predicted": statistics.mean(c[p] for p in products), "observed": c["observed"]}
        for c in all_cases])

    weighted, corrected = [], []
    for held in stations:
        training = [c for c in all_cases if c["station"] != held]
        testing = [c for c in all_cases if c["station"] == held]
        if len(training) < 100 or not testing:
            continue
        weights = fit_weights(training, products)
        intercept, slope = fit_elevation(training, products)
        for case in testing:
            blend = sum(weights[p] * case[p] for p in products)
            weighted.append({"predicted": blend, "observed": case["observed"]})
            plain = statistics.mean(case[p] for p in products)
            corrected.append({"predicted": plain - (intercept + slope * case["elevation"]),
                              "observed": case["observed"]})
    if weighted:
        results["weighted_mean_cross_validated"] = score(weighted)
    if corrected:
        results["elevation_corrected_mean_cross_validated"] = score(corrected)

    reference = min((k for k in results), key=lambda k: results[k]["root_mean_square_error"])
    for name, entry in results.items():
        entry["fitted"] = name.endswith("cross_validated")
    return {"candidates": results, "best_by_rmse": reference,
            "stations": len(stations), "products": list(products)}


def build():
    rows = load()
    report = {"generated_at": utc_now(), "variables": {}}
    for variable, products in (("air_temperature_mean", ("era5_land", "terraclimate")),
                               ("precipitation_total", ("era5_land", "terraclimate"))):
        found = evaluate(cases(rows, variable, products), products)
        if found:
            report["variables"][variable] = found

    report["method"] = {
        "validation": "Leave-one-station-out. A fitted candidate is scored only on stations "
                      "excluded from its own fitting, so the figures are out-of-sample.",
        "unfitted": "Each product alone and the plain mean are fitted to nothing and are "
                    "scored directly on every pair.",
    }
    report["limits"] = {
        "coverage": "Thirty-six stations sit below 500 m and four above 1500 m. A mountain "
                    "correction rests on those four and is only as good as they are typical.",
        "support": "Fitted at station points. A basin mean is a different spatial support and "
                   "a point correction does not transfer to it without separate work.",
        "identity": "Stations were placed by a name crosswalk that one check did not "
                    "contradict; it is not a verified identity.",
        "soil_temperature": "Excluded: only one product estimates it, so there is nothing to "
                            "combine and no ensemble to test.",
    }
    write_json(REPORT, report)
    return report


def main():
    print(json.dumps(build(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
