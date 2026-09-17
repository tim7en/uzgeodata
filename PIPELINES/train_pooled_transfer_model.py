#!/usr/bin/env python3
"""Pooled, gauge-unseen transfer model: predict discharge from climate + basin
attributes alone, for basins that have never reported a single discharge value.

Why this replaces the per-gauge "gauge-independent" experiment: that script
still fit one Random Forest PER GAUGE. A model that only ever sees one basin's
rows cannot use basin_area_km2, elevation, etc. as predictors at all (they are
constant within a gauge, so a tree has zero variance to split on) and there is
no shared model to hand to an ungauged basin — there was nothing to apply.

This script instead:
1. Pools all gauges into one training set and predicts SPECIFIC discharge
   (mm/day, i.e. discharge normalised by basin_area_km2) from climate,
   basin static attributes and seasonal terms. Specific discharge is the
   standard hydrological regionalisation target: it is comparable across a
   98 km2 and a 121,000 km2 basin, which raw m3/s is not.
2. Validates with GroupKFold by gauge_code: every held-out fold contains
   GAUGES the model never trained on at all (not just held-out months at a
   gauge it already knows). This is the actual "ungauged basin" test.
3. Reconstructs discharge_m3s = specific_discharge_mm_day * area / 86.4 and
   scores that reconstruction, because the site's claim is about discharge,
   not about specific discharge.
4. Fits a per-gauge calibration ratio on top of the pooled, out-of-fold
   prediction (using each gauge's own early record; scored on its own later
   record) so a gauge that does exist can sharpen the transferable estimate
   without breaking the fact that the base model is still usable elsewhere.
5. Runs a basin-relative mass-balance sanity check: within each named
   sub-basin, larger upstream area should not predict systematically less
   discharge than a smaller-area gauge in the same basin.

Usage:
    python PIPELINES/train_pooled_transfer_model.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.model_selection import GroupKFold
from sklearn.metrics import r2_score, mean_squared_error
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
CS = ROOT / "PUBLISHED/data/case-studies"
DATA = CS / "enhanced_discharge_features_aral.csv"
OUT_SUMMARY = CS / "pooled_transfer_summary.json"
OUT_PREDICTIONS = CS / "pooled_transfer_predictions.csv"
OUT_IMPORTANCE = CS / "pooled_transfer_importance.csv"
OUT_FIGURE = CS / "pooled_transfer_atlas.png"

N_FOLDS = 5
SECONDS_PER_DAY = 86400
MM_PER_M = 1000
KM2_TO_M2 = 1e6
AREA_TO_SPECIFIC = SECONDS_PER_DAY * MM_PER_M / KM2_TO_M2  # 86.4: m3/s, km2 -> mm/day


def load() -> pd.DataFrame:
    df = pd.read_csv(DATA, dtype={"gauge_code": str})
    df = df[df["discharge_m3s"] > 0].copy()
    df["q_spec_mm_day"] = df["discharge_m3s"] * AREA_TO_SPECIFIC / df["basin_area_km2"]
    df["log_q_spec"] = np.log1p(df["q_spec_mm_day"])
    return df


FEATURES = [
    # Terrain / static basin form.
    "basin_area_km2", "basin_elevation_m", "basin_elevation_min_m", "basin_elevation_max_m",
    "basin_slope_pct", "basin_aspect", "basin_tri", "basin_roughness",
    # Real land cover (Copernicus CGLS-LC100, corrected — see
    # comprehensive_feature_engineering.map_esa_landcover). landcover_snow_ice_pct
    # is the actual glacier/permanent-snow signal; basin_glacier_pct was a
    # hardcoded 0.0 placeholder and is deliberately not used here.
    "landcover_forest_pct", "landcover_shrubland_pct", "landcover_grassland_pct",
    "landcover_cropland_pct", "landcover_bare_pct", "landcover_snow_ice_pct",
    "landcover_water_pct",
    # Climate forcing — this is where seasonality actually lives (temperature
    # is negative in winter, precipitation peaks in spring, on their own
    # values) rather than a synthetic month_sin/month_cos calendar signal.
    "basin_precip_mm", "basin_precip_lag1_mm", "basin_precip_3m_mm", "basin_anom_precip",
    "basin_tavg_c", "basin_tmax_c", "basin_tmin_c",
]


def prepared(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    features = [f for f in FEATURES if f in df.columns and df[f].notna().mean() >= 0.9]
    dropped = [f for f in FEATURES if f not in features]
    if dropped:
        print(f"Dropping sparse/missing features: {dropped}")
    valid = df.dropna(subset=features + ["log_q_spec"]).reset_index(drop=True)
    print(f"Pooled dataset: {len(valid)} records, {valid.gauge_code.nunique()} gauges, {len(features)} features")
    return valid, features


def fit_predict_oof(df: pd.DataFrame, features: list[str]) -> np.ndarray:
    """Out-of-fold pooled predictions: each row is predicted by a model that
    never saw its gauge during training (GroupKFold by gauge_code)."""
    groups = df["gauge_code"].values
    X = df[features].values
    y = df["log_q_spec"].values
    oof = np.full(len(df), np.nan)

    gkf = GroupKFold(n_splits=N_FOLDS)
    for fold, (train_idx, test_idx) in enumerate(gkf.split(X, y, groups), 1):
        scaler = StandardScaler()
        X_train = scaler.fit_transform(X[train_idx])
        X_test = scaler.transform(X[test_idx])
        rf = RandomForestRegressor(n_estimators=300, max_depth=14, min_samples_leaf=3,
                                    random_state=42, n_jobs=-1)
        gb = GradientBoostingRegressor(n_estimators=200, learning_rate=0.05, max_depth=4,
                                        random_state=42)
        rf.fit(X_train, y[train_idx])
        gb.fit(X_train, y[train_idx])
        oof[test_idx] = 0.5 * rf.predict(X_test) + 0.5 * gb.predict(X_test)
        print(f"  fold {fold}/{N_FOLDS}: {len(test_idx)} held-out rows, "
              f"{df['gauge_code'].iloc[test_idx].nunique()} unseen gauges")

    return oof


def full_fit_importance(df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    scaler = StandardScaler()
    X = scaler.fit_transform(df[features].values)
    rf = RandomForestRegressor(n_estimators=300, max_depth=14, min_samples_leaf=3,
                                random_state=42, n_jobs=-1)
    rf.fit(X, df["log_q_spec"].values)
    return pd.DataFrame({"feature": features, "importance": rf.feature_importances_}) \
        .sort_values("importance", ascending=False)


def calibrate_per_gauge(df: pd.DataFrame) -> pd.DataFrame:
    """For each gauge, fit a ratio calibration on its own first 80% of
    chronologically ordered records (using the pooled out-of-fold prediction,
    which is already unbiased because that gauge's fold never trained on it),
    then score both the raw pooled estimate and the calibrated one on the
    remaining, later 20% — a forward-chronology test, not reused training rows."""
    rows = []
    for code, g in df.groupby("gauge_code"):
        g = g.sort_values("date").reset_index(drop=True)
        n_train = int(0.8 * len(g))
        if n_train < 10 or len(g) - n_train < 5:
            continue
        train, test = g.iloc[:n_train], g.iloc[n_train:]
        ratio = float(np.median(train["discharge_m3s"]) / max(np.median(train["discharge_pooled_pred_m3s"]), 1e-6))
        calibrated_pred = test["discharge_pooled_pred_m3s"] * ratio
        rows.append({
            "gauge_code": code,
            "n_calibration": n_train,
            "n_test": len(test),
            "calibration_ratio": ratio,
            "r2_pooled_uncalibrated": r2_score(test["discharge_m3s"], test["discharge_pooled_pred_m3s"]) if len(test) > 1 else np.nan,
            "r2_pooled_calibrated": r2_score(test["discharge_m3s"], calibrated_pred) if len(test) > 1 else np.nan,
            "rmse_pooled_uncalibrated": float(np.sqrt(mean_squared_error(test["discharge_m3s"], test["discharge_pooled_pred_m3s"]))),
            "rmse_pooled_calibrated": float(np.sqrt(mean_squared_error(test["discharge_m3s"], calibrated_pred))),
        })
    return pd.DataFrame(rows)


def mass_balance_check(df: pd.DataFrame, topology_path: Path) -> dict:
    """Real upstream/downstream check using traced catchment geometry
    (build_gauge_topology.py), not a same-named-basin-plus-area heuristic:
    that heuristic missed cross-basin confluences (Naryn into Syr Darya) and
    had no way to tell a genuinely nested catchment from two unrelated basins
    of similar size.

    For each downstream gauge with an identified dominant upstream gauge
    (its single largest confirmed-nested measured tributary), discharge
    should not drop right at that confluence — even though it commonly drops
    much further downstream in this basin from irrigation withdrawal, which
    is real hydrology, not a model error, and is not what this checks.
    """
    if not topology_path.exists():
        return {"comparisons": 0, "violations": 0, "violation_rate_pct": None,
                "note": f"{topology_path.name} not found — run build_gauge_topology.py first"}

    dominant = pd.read_csv(topology_path, dtype={"downstream_code": str, "dominant_upstream_code": str})
    median_q = df.groupby("gauge_code")[["discharge_m3s", "discharge_pooled_pred_m3s"]].median()

    comparisons, violations_obs, violations_pred = 0, 0, 0
    for row in dominant.itertuples():
        if row.downstream_code not in median_q.index or row.dominant_upstream_code not in median_q.index:
            continue
        comparisons += 1
        down, up = median_q.loc[row.downstream_code], median_q.loc[row.dominant_upstream_code]
        if down["discharge_m3s"] < up["discharge_m3s"]:
            violations_obs += 1
        if down["discharge_pooled_pred_m3s"] < up["discharge_pooled_pred_m3s"]:
            violations_pred += 1

    return {
        "comparisons": comparisons,
        "violations_observed": violations_obs,
        "violations_predicted": violations_pred,
        "violation_rate_observed_pct": round(100 * violations_obs / comparisons, 1) if comparisons else None,
        "violation_rate_predicted_pct": round(100 * violations_pred / comparisons, 1) if comparisons else None,
    }


def plot_atlas(valid: pd.DataFrame, importance: pd.DataFrame, overall_r2: float) -> None:
    """Two panels, deliberately: a log-log scatter (the only honest way to show
    98-121,000 km2 basins on one axis) and a horizontal importance bar chart.
    No per-gauge legend, no per-gauge ticks — this model has 76 gauges and
    is meant to generalise to basins that have none."""
    figure, axes = plt.subplots(1, 2, figsize=(13, 5.5), dpi=160)
    figure.patch.set_facecolor("white")

    axis = axes[0]
    obs = valid["discharge_m3s"].clip(lower=0.01)
    pred = valid["discharge_pooled_pred_m3s"].clip(lower=0.01)
    axis.scatter(obs, pred, s=10, alpha=.35, color="#5d8f99")
    lo, hi = min(obs.min(), pred.min()), max(obs.max(), pred.max())
    axis.plot([lo, hi], [lo, hi], "--", color="#333333", linewidth=1)
    axis.set_xscale("log")
    axis.set_yscale("log")
    axis.set(xlabel="Observed discharge (m3/s, log scale)", ylabel="Predicted discharge (m3/s, log scale)",
             title=f"Gauge-unseen prediction, {valid.gauge_code.nunique()} gauges (R²={overall_r2:.2f})")

    axis = axes[1]
    top = importance.head(8).iloc[::-1]
    axis.barh(top["feature"], top["importance"], color="#5d8f99")
    axis.set(xlabel="Importance (specific discharge model)", title="What predicts discharge without a gauge")
    axis.tick_params(labelsize=10)

    for axis in axes.flat:
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="x" if axis is axes[1] else "both", alpha=.2)
    figure.suptitle("Pooled transfer model: climate + basin attributes only, no gauge history anywhere",
                     fontsize=13, x=.04, ha="left")
    figure.tight_layout()
    figure.savefig(OUT_FIGURE, facecolor="white")
    plt.close(figure)


def main() -> None:
    df = load()
    valid, features = prepared(df)

    oof_log = fit_predict_oof(valid, features)
    valid["log_q_spec_pred"] = oof_log
    valid["q_spec_pred_mm_day"] = np.expm1(oof_log)
    valid["discharge_pooled_pred_m3s"] = valid["q_spec_pred_mm_day"] * valid["basin_area_km2"] / AREA_TO_SPECIFIC

    overall_r2 = r2_score(valid["discharge_m3s"], valid["discharge_pooled_pred_m3s"])
    overall_rmse = float(np.sqrt(mean_squared_error(valid["discharge_m3s"], valid["discharge_pooled_pred_m3s"])))
    print(f"\nPooled, gauge-unseen reconstruction: R2={overall_r2:.3f}, RMSE={overall_rmse:.2f} m3/s")

    per_gauge_r2 = valid.groupby("gauge_code").apply(
        lambda g: r2_score(g["discharge_m3s"], g["discharge_pooled_pred_m3s"]) if len(g) > 1 else np.nan,
        include_groups=False,
    )
    print(f"Per-gauge pooled R2: median {per_gauge_r2.median():.3f}, "
          f"positive {int((per_gauge_r2 > 0).sum())}/{len(per_gauge_r2)}")

    importance = full_fit_importance(valid, features)
    importance.to_csv(OUT_IMPORTANCE, index=False)
    print("\nTop specific-discharge predictors:")
    for row in importance.head(8).itertuples():
        print(f"  {row.feature:28s} {row.importance:.4f}")

    calibration = calibrate_per_gauge(valid)
    calibration.to_csv(CS / "pooled_transfer_calibration.csv", index=False)
    cal_positive = int((calibration.r2_pooled_calibrated > 0).sum())
    uncal_positive = int((calibration.r2_pooled_uncalibrated > 0).sum())
    print(f"\nPer-gauge calibration (chronological holdout after local ratio fit): "
          f"{cal_positive}/{len(calibration)} positive calibrated vs "
          f"{uncal_positive}/{len(calibration)} positive uncalibrated; "
          f"median calibrated R2 {calibration.r2_pooled_calibrated.median():.3f} "
          f"vs uncalibrated {calibration.r2_pooled_uncalibrated.median():.3f}")

    mb = mass_balance_check(valid, CS / "gauge_topology_dominant_upstream.csv")
    print(f"\nMass-balance plausibility check (real traced topology): "
          f"{mb['comparisons']} confluence pairs; "
          f"predicted inverted {mb.get('violations_predicted')} ({mb.get('violation_rate_predicted_pct')}%), "
          f"observed inverted {mb.get('violations_observed')} ({mb.get('violation_rate_observed_pct')}%)")

    plot_atlas(valid, importance, overall_r2)

    valid[[
        "gauge_code", "date", "year", "month", "basin_area_km2",
        "discharge_m3s", "q_spec_mm_day", "q_spec_pred_mm_day", "discharge_pooled_pred_m3s",
    ]].to_csv(OUT_PREDICTIONS, index=False)
    summary = {
        "method": "Pooled RF+GB on specific discharge (mm/day, area-normalised), "
                  "GroupKFold by gauge_code (gauges in a held-out fold are entirely unseen "
                  "by that fold's model) so every reported number is a genuine "
                  "spatial-transfer / ungauged-basin test.",
        "n_gauges": int(valid.gauge_code.nunique()),
        "n_records": len(valid),
        "features": features,
        "overall_r2": float(overall_r2),
        "overall_rmse_m3s": overall_rmse,
        "per_gauge_r2_median": float(per_gauge_r2.median()),
        "per_gauge_positive": int((per_gauge_r2 > 0).sum()),
        "per_gauge_total": int(len(per_gauge_r2)),
        "calibration": {
            "positive_calibrated": cal_positive,
            "positive_uncalibrated": uncal_positive,
            "n_gauges_calibrated": len(calibration),
            "median_r2_calibrated": float(calibration.r2_pooled_calibrated.median()),
            "median_r2_uncalibrated": float(calibration.r2_pooled_uncalibrated.median()),
        },
        "mass_balance_check": mb,
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSaved {OUT_SUMMARY.name}, {OUT_PREDICTIONS.name}, {OUT_IMPORTANCE.name}")


if __name__ == "__main__":
    main()
