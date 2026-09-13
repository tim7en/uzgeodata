"""Check Layer 4 against a river, because a model harness nobody tested is a claim.

Everything above this point can be checked internally: a sum is right or wrong against
its inputs. A model cannot be checked that way at all. So this takes the one target in
the project that was measured independently of everything the platform produces -- the
Pskem gauge at Mullala, 2001 to 2017, read from a hydromet archive -- and asks whether
monthly climate over the catchment predicts it on years the fit never saw.

Two things make it a fair test rather than a demonstration:

The predictors are the catchment, not the outlet. The gauge integrates everything
draining through it, which the routing table says is twenty level-12 basins, and they
are area-weighted. Running this on the outlet polygon alone would be predicting a river
from a few square kilometres beside it and would still produce a number.

The evaluation years are withheld before the fit exists. The split is fixed here and
the harness refuses a score on the training period at all, so there is no path by which
the reported skill was tuned on what it is scored against.

Discharge is converted to millimetres of depth over the catchment so it stands in the
same units as the fluxes predicting it, and a coefficient can be read.
"""
from __future__ import annotations
import argparse
import calendar
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import models, query
from ATLAS_MODULES.core.runtime import utc_now, write_json

STORE = ROOT / "PUBLISHED/data/atlas/observations"
HYDRO = ROOT / "PUBLISHED/data/hydroclimate"
OUT = ROOT / "PUBLISHED/data/atlas/models/pskem-discharge.json"

GAUGE = "uz:station/gauge-16290"
OUTLET = "4121289400"

# Fixed before the fit, and stated here rather than passed in, so no one can search
# over splits until the skill looks good. Ten years to fit, the rest held out.
TRAIN = ("2003-01", "2012-12")
EVALUATE = ("2013-01", "2017-12")

# Chosen from what drives a snowmelt river, before any skill was computed:
# precipitation is the supply, maximum temperature is the energy that releases it, and
# snow cover is how much is still held on the ground. None of the three is a discharge
# measurement, which is the point of the exercise.
#
# The first set used ERA5 mean temperature instead of the TerraClimate maximum. It was
# changed for coverage and not for skill: ERA5 temperature begins in 2010, which left
# 36 of the 120 training months standing once the harness dropped every month it could
# not fill. The split below did not move, and the score that came back after the change
# is the score recorded, whatever it says.
CONCEPTS = ["precipitation", "maximum temperature", "snow cover"]


def catchment(outlet=OUTLET, routing=HYDRO / "basin-routing-level12.csv"):
    """Every level-12 basin draining through the outlet, by walking the routing graph."""
    upstream = {}
    with routing.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["level"] != "12":
                continue
            upstream.setdefault(row["next_down"], []).append(row["hybas_id"])
    found, stack = set(), [str(outlet)]
    while stack:
        basin = stack.pop()
        if basin in found:
            continue
        found.add(basin)
        stack.extend(upstream.get(basin, []))
    return sorted(found)


def areas(basins, geometry=HYDRO / "basins-level12.geojson"):
    """Each basin's own area in square kilometres, from the published geometry.

    SUB_AREA and not UP_AREA: these are the weights for averaging a field across the
    catchment, so each basin should count for the land it covers. UP_AREA would count
    every headwater once for itself and again inside everything below it.
    """
    wanted = set(basins)
    collection = json.loads(geometry.read_text(encoding="utf-8"))
    found = {}
    for feature in collection["features"]:
        properties = feature["properties"]
        key = str(properties["HYBAS_ID"])
        if key in wanted:
            found[key] = float(properties["SUB_AREA"])
    missing = wanted - set(found)
    if missing:
        raise models.NotEnoughEvidence(f"no area published for {sorted(missing)}")
    return found


def gauge_depth(area_km2, path=HYDRO / "pskem-discharge-monthly.csv", station=GAUGE):
    """Monthly discharge as millimetres of depth over the catchment.

    A mean in cubic metres per second becomes a depth by spreading the month's volume
    across the draining area, which puts the target in the same units as the rainfall
    predicting it. Months whose observed days do not match the calendar are dropped:
    the source carries at least one, a 29-day February in a non-leap year, and a mean
    over a miscounted month is a quantity of unknown definition.
    """
    kept, rejected = {}, []
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["station_id"] != station:
                continue
            year, month = int(row["year"]), int(row["month"])
            days = calendar.monthrange(year, month)[1]
            if int(row["days_observed"]) != days or int(row["days_in_month"]) != days:
                rejected.append({"year": year, "month": month,
                                 "days_observed": int(row["days_observed"]),
                                 "calendar_days": days})
                continue
            seconds = days * 86400
            volume = float(row["discharge_mean_cms"]) * seconds       # cubic metres
            kept[(year, month)] = volume / (area_km2 * 1e6) * 1000.0  # millimetres
    return kept, rejected


def run(store=STORE, out=OUT):
    basins = catchment()
    weight = areas(basins)
    total = sum(weight.values())
    target, rejected = gauge_depth(total)

    connection = query.connect(store)
    try:
        report = models.fit(store, basins, target, CONCEPTS, TRAIN, EVALUATE,
                            connection=connection, weights=weight,
                            label=f"{GAUGE} monthly discharge as depth over the catchment")
    finally:
        connection.close()

    report.update({
        "generated_at": utc_now(),
        "predictor_note": "Snow cover is published with a caution: its gaps grow towards the "
                          "present at constant source coverage. It is used here as a predictor, "
                          "where that bias costs the model accuracy, and not as evidence of a "
                          "trend, which is what the caution forbids.",
        "catchment": {"outlet": OUTLET, "basins": len(basins),
                      "area_km2": round(total, 1),
                      "derived_from": "basin-routing-level12.csv, walked upstream"},
        "target_unit": "millimetres of depth over the catchment per month",
        "gauge": {"station_id": GAUGE, "label": "р. Пскем (с. Муллала)",
                  "months_available": len(target),
                  "months_rejected_for_day_count": rejected},
        "independence": "The gauge is a hydromet record, measured by instruments this "
                        "project has no part in. Nothing in the predictors was fitted to "
                        "it and nothing in it was used to build the observation store.",
    })
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        write_json(out, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--dry-run", action="store_true",
                        help="report without writing the published result")
    arguments = parser.parse_args()
    report = run(out=None if arguments.dry_run else Path(arguments.out))
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
