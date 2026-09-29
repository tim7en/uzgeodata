"""Bounded, reproducible arithmetic audit for the screenshot basin.

Run from repository root: python qa/deep_dive/tab_audit/check_screenshot_basin.py
This checks independent arithmetic from published intermediate tables. The raw
TerraClimate NetCDF is not in this checkout; the drought record has its own check
(qa/deep_dive/drought/check_drought_basin.py).
"""
import hashlib
import json
import math
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).with_name("result.json")
BASIN = "4121292070"
BASE = ROOT / "PUBLISHED/data/atlas/climate-continuation"
HIST = ROOT / f"PUBLISHED/data/atlas/history/{BASIN}.json"
COEFF = BASE / "water-balance-coefficients.parquet"
CONT = BASE / "v1.1-water-balance-continuation.parquet"
TOLERANCE = 0.00011  # displayed monthly values rounded to 4 decimal places


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def rows(path, **filters):
    return pq.read_table(path, filters=[(k, "=", v) for k, v in filters.items()]).to_pylist()


def main():
    history = json.loads(HIST.read_text(encoding="utf-8"))
    files = {HIST, COEFF, CONT}
    aet2025_path = BASE / "terraclimate-v1.1-history/year=2025.parquet"
    files.add(aet2025_path)
    aet = sorted(rows(aet2025_path, basin_id=BASIN, variable="aet"), key=lambda r: r["month"])
    assert len(aet) == 12 and all(r["value"] is not None for r in aet)
    chart = history["series"]["aet_mm_s"]["values"]
    checks = []
    for r in aet:
        i = (2025 - history["years"][0]) * 12 + r["month"] - 1
        checks.append({"month": r["month"], "intermediate": r["value"],
                       "display": chart[i], "difference": chart[i] - r["value"]})
    annual = sum(r["value"] for r in aet)
    # Independently apply the stored basin/month regression to the source predictor.
    c = rows(COEFF, basin_id=BASIN, variable="aet", month=1)[0]
    predictor_path = BASE / "era5-land-extended/year=2026.parquet"
    files.add(predictor_path)
    predictor = rows(predictor_path, basin_id=BASIN, variable=c["predictor"], month=1)[0]
    modeled = max(0.0, c["target_mean"] + c["slope"] * (predictor["value"] - c["predictor_mean"]))
    published = rows(CONT, basin_id=BASIN, variable="aet", year=2026, month=1)[0]
    assert math.isclose(predictor["value"], published["era_value"], abs_tol=1e-9)
    # A basin-specific holdout, with the earlier fitted coefficients frozen.
    coeffs = {r["month"]: r for r in rows(COEFF, basin_id=BASIN, variable="aet")}
    holdout = []
    for year in range(2020, 2026):
        target_path = BASE / f"terraclimate-v1.1-history/year={year}.parquet"
        era_path = BASE / f"era5-land-extended/year={year}.parquet"
        files.update((target_path, era_path))
        targets = {r["month"]: r["value"] for r in rows(target_path, basin_id=BASIN, variable="aet")}
        proxy = {r["month"]: r["value"] for r in rows(era_path, basin_id=BASIN, variable="aet_mm")}
        for month in range(1, 13):
            if month not in targets or month not in proxy or targets[month] is None or proxy[month] is None:
                continue
            fit = coeffs[month]
            predicted = max(0.0, fit["target_mean"] + fit["slope"] * (proxy[month] - fit["predictor_mean"]))
            holdout.append((targets[month], predicted, fit["target_mean"]))
    rmse = lambda column: math.sqrt(sum((r[column] - r[0]) ** 2 for r in holdout) / len(holdout))

    result = {
        "basin_id": BASIN,
        "scope": "published intermediate arithmetic, not raw NetCDF re-extraction or station validation",
        "files_sha256": {str(p.relative_to(ROOT)).replace('\\', '/'): sha(p) for p in sorted(files)},
        "checks": {
            "aet_2025": {"monthly": checks, "annual_total_mm": annual,
                         "displayed_month_sum_mm": sum(c["display"] for c in checks),
                         "maximum_absolute_display_difference_mm": max(abs(c["difference"]) for c in checks),
                         "status": "PASS" if all(abs(c["difference"]) <= TOLERANCE for c in checks) else "FAIL"},
            "aet_2026_01_estimate": {"predictor_mm": predictor["value"], "target_mean_mm": c["target_mean"],
                "predictor_mean_mm": c["predictor_mean"], "slope": c["slope"],
                "recomputed_mm": modeled, "published_mm": published["estimate"],
                "difference_mm": modeled - published["estimate"],
                "holdout_abs_error_p90_mm": published["holdout_abs_error_p90"],
                "status": "PASS" if abs(modeled - published["estimate"]) < 1e-8 else "FAIL"},
            "aet_2020_2025_local_holdout": {"months": len(holdout),
                "estimated_rmse_mm_per_month": rmse(1), "seasonal_baseline_rmse_mm_per_month": rmse(2),
                "status": "CALCULATED_MODEL_SKILL"}
        },
        "limitations": ["Raw TerraClimate v1.1 NetCDF grids are absent; monthly basin values cannot be independently extracted.",
                        "The drought record is checked separately by qa/deep_dive/drought/check_drought_basin.py."],
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"basin_id": BASIN, "checks": {k: {z: v for z, v in c.items() if z in ("status", "annual_total_mm", "recomputed_mm", "published_mm", "ppt_total_mm")} for k, c in result["checks"].items()}}, indent=2))
    if any(c["status"] == "FAIL" for c in result["checks"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
