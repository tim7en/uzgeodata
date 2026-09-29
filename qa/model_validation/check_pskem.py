"""Recalculate the published Pskem monthly holdout from underlying series."""
from __future__ import annotations

import calendar
import csv
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import duckdb
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
ATLAS = ROOT / "PUBLISHED/data/atlas"
HYDRO = ROOT / "PUBLISHED/data/hydroclimate"
MODEL = ATLAS / "models/pskem-discharge.json"
OUT = Path(__file__).with_name("results.json")
ATTRS = ("pre_mm_s", "tmx_dc_s", "snw_pc_s")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scores(obs, pred):
    err = [p - o for o, p in zip(obs, pred)]
    return {"n": len(err), "bias": sum(err) / len(err),
            "mae": sum(map(abs, err)) / len(err),
            "rmse": math.sqrt(sum(e * e for e in err) / len(err))}


def main():
    claim = json.loads(MODEL.read_text(encoding="utf-8"))
    basins = claim["basins"]
    geo = json.loads((HYDRO / "basins-level12.geojson").read_text(encoding="utf-8"))
    area = {str(f["properties"]["HYBAS_ID"]): float(f["properties"]["SUB_AREA"])
            for f in geo["features"] if str(f["properties"]["HYBAS_ID"]) in basins}
    assert len(area) == len(basins)
    total_area = sum(area.values())

    monthly = {}
    rejected = []
    with (HYDRO / "pskem-discharge-monthly.csv").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["station_id"] != "uz:station/gauge-16290":
                continue
            year, month = int(row["year"]), int(row["month"])
            days = calendar.monthrange(year, month)[1]
            key = f"{year:04d}-{month:02d}"
            if int(row["days_observed"]) != days or int(row["days_in_month"]) != days:
                rejected.append(key)
                continue
            monthly[key] = float(row["discharge_mean_cms"]) * days * 86400 / (total_area * 1000)

    # Use the published observation query's run/revision selection; independently
    # aggregate basin values and recompute predictions, baseline and error metrics.
    from ATLAS_MODULES.core import query
    store = ATLAS / "observations"
    conn = query.connect(store)
    rows = []
    try:
        for suffix in ATTRS:
            rows.extend(query.observations(store, basins=basins,
                        variables=[f"uzgeodata.dated.v1.{suffix}"],
                        start="2003-01", end="2017-12", connection=conn))
    finally:
        conn.close()
    cells = defaultdict(dict)
    for basin, attr, month, val, *_ in rows:
        cells[month.strftime("%Y-%m")][(str(basin), attr.split(".")[-1])] = val

    matrix = {}
    missing = {}
    for key in sorted(cells):
        vector = []
        absent = {}
        for attr in ATTRS:
            gaps = [basin for basin in basins if cells[key].get((basin, attr)) is None]
            if gaps:
                absent[attr] = len(gaps)
            else:
                vector.append(sum(area[b] * cells[key][(b, attr)] for b in basins) / total_area)
        if absent:
            missing[key] = absent
        else:
            matrix[key] = vector

    train = [k for k in sorted(matrix) if "2003-01" <= k <= "2012-12" and k in monthly]
    test = [k for k in sorted(matrix) if "2013-01" <= k <= "2017-12" and k in monthly]
    X = np.array([[1, *matrix[k]] for k in train])
    y = np.array([monthly[k] for k in train])
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    coeff = np.array([claim["coefficients"][name] for name in
                      ("intercept", "precipitation", "maximum temperature", "snow cover")])
    obs = [monthly[k] for k in test]
    pred = [float(np.dot([1, *matrix[k]], coeff)) for k in test]
    ref_by_month = {m: sum(monthly[k] for k in train if int(k[5:]) == m) /
                    sum(int(k[5:]) == m for k in train) for m in range(1, 13)}
    baseline = [ref_by_month[int(k[5:])] for k in test]
    model_score = scores(obs, pred)
    baseline_score = scores(obs, baseline)
    model_sse = sum((o-p)**2 for o, p in zip(obs, pred))
    baseline_sse = sum((o-p)**2 for o, p in zip(obs, baseline))
    mean = sum(obs) / len(obs)
    model_score["nash_sutcliffe"] = 1 - model_sse / sum((o-mean)**2 for o in obs)
    model_score["skill_against_training_month_climatology"] = 1 - model_sse / baseline_sse
    residual_quantiles = {str(q): float(np.quantile([p-o for o,p in zip(obs,pred)], q))
                          for q in (0, .1, .25, .5, .75, .9, 1)}
    groups = {"cold_Nov_Apr": [i for i,k in enumerate(test) if int(k[5:]) in (11,12,1,2,3,4)],
              "warm_May_Oct": [i for i,k in enumerate(test) if int(k[5:]) in (5,6,7,8,9,10)]}
    # Regime thresholds come from training observations alone.
    low, high = np.quantile(y, [1/3, 2/3])
    groups["dry_lower_training_tercile"] = [i for i,o in enumerate(obs) if o < low]
    groups["wet_upper_training_tercile"] = [i for i,o in enumerate(obs) if o > high]
    stratified = {name: {"model": scores([obs[i] for i in ids], [pred[i] for i in ids]),
                         "baseline": scores([obs[i] for i in ids], [baseline[i] for i in ids])}
                  for name, ids in groups.items() if ids}
    deltas = {name: model_score[name] - claim["skill"][name] for name in
              ("bias", "mae", "rmse", "nash_sutcliffe")}
    assert len(train) == claim["train"]["months"] and len(test) == claim["evaluate"]["months"]
    assert max(abs(beta - coeff)) < 1e-8
    assert max(map(abs, deltas.values())) < 1e-8
    assert abs(model_score["skill_against_training_month_climatology"] -
               claim["skill"]["skill_against_climatology"]) < 1e-8
    result = {
        "classification": "retrospective monthly statistical reconstruction using same-month observed climate; no lead-time forecast skill established",
        "target_unit": "mm/month catchment depth", "area_km2": total_area,
        "split": {"train": ["2003-01", "2012-12"], "evaluate": ["2013-01", "2017-12"],
                  "train_months": len(train), "heldout_months": len(test), "heldout_keys": test},
        "missingness": {"gauge_valid_months_total": len(monthly), "rejected_calendar_months": rejected,
                        "incomplete_predictor_months": missing,
                        "nominal_train_months": 120, "nominal_evaluation_months": 60},
        "coefficients_refit": beta.tolist(), "published_coefficients": coeff.tolist(),
        "published_metric_deltas": deltas, "model": model_score, "baseline": baseline_score,
        "residual_quantiles_mm": residual_quantiles,
        "strata": stratified, "training_target_tercile_thresholds_mm": [float(low), float(high)],
        "uncertainty": {"published_interval": None, "coverage_test": "unavailable: no predictive interval published"},
        "provenance": {"model_sha256": sha(MODEL),
                       "gauge_monthly_sha256": sha(HYDRO / "pskem-discharge-monthly.csv"),
                       "geometry_sha256": sha(HYDRO / "basins-level12.geojson"),
                       "observation_manifest_sha256": sha(store / "manifest.json")},
        "limitations": ["Predictor row choice uses repository query view; aggregation, fit and metrics are recalculated separately.",
                        "Historical same-month predictor values may not have been available at forecast issue time.",
                        "Five evaluation years from one gauge and one catchment; no geographic transfer test.",
                        "No uncertainty interval or probabilistic coverage claim in the model artifact."]}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"n": len(test), "model": model_score, "baseline": baseline_score,
                      "rejected": rejected, "max_coefficient_delta": float(max(abs(beta-coeff)))}, indent=2))


if __name__ == "__main__":
    main()
