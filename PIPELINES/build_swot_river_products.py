#!/usr/bin/env python3
"""Turn the raw SWOT river-reach fetch (fetch_swot_rivers.py) into what the
landing map actually serves: a single trimmed GeoJSON of every named reach
for the map layer, and one small per-reach observation JSON -- fetched
lazily on click, the same shape LakeModal already uses for lakes -- for
every reach with enough passing data to chart.

Usage:
    python PIPELINES/build_swot_river_products.py
"""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from statsmodels.nonparametric.smoothers_lowess import lowess

ROOT = Path(__file__).resolve().parents[1]
CS = ROOT / "PUBLISHED/data/case-studies/rivers"
OUT_SWOT_DIR = CS / "swot"
OUT_LAYER = CS / "reaches.geojson"
MIN_GOOD_FOR_CHART = 5
# SWORD centerlines average 324 vertices/reach -- far denser than a
# national-scale web map needs. 0.001 degrees (~100 m) cuts that to ~13
# while keeping each reach's shape recognisable at any zoom this map uses.
SIMPLIFY_TOLERANCE_DEG = 0.001


def loess_fit(dates: pd.Series, values: pd.Series, frac: float) -> list[float | None]:
    valid = values.notna()
    if valid.sum() < 5:
        return [None] * len(values)
    x = dates.astype("int64").to_numpy(dtype=float)
    y = values.to_numpy(dtype=float)
    smoothed = lowess(y[valid.to_numpy()], x[valid.to_numpy()], frac=frac, return_sorted=False)
    out = np.full(len(values), np.nan)
    out[valid.to_numpy()] = smoothed
    return [None if np.isnan(v) else round(float(v), 3) for v in out]


def main() -> None:
    OUT_SWOT_DIR.mkdir(parents=True, exist_ok=True)

    prior = gpd.read_file(CS / "reaches_prior.geojson")
    prior["reach_id"] = prior["reach_id"].astype(str)
    summary = pd.read_csv(CS / "river_summary.csv", dtype={"reach_id": str})
    monthly = pd.read_csv(CS / "river_timeseries_monthly.csv", dtype={"reach_id": str}, parse_dates=["time"])
    monthly_by_reach = {rid: g.sort_values("time") for rid, g in monthly.groupby("reach_id")}
    raw = pd.read_csv(CS / "river_observations_raw.csv", dtype={"reach_id": str}, parse_dates=["time"])
    raw["wse_outlier"] = raw["wse_outlier"].astype(bool)
    raw["partial_f"] = raw["partial_f"].fillna(0).astype(bool)
    raw_by_reach = {rid: g.sort_values("time") for rid, g in raw.groupby("reach_id")}

    summary_by_reach = {r.reach_id: r for r in summary.itertuples()}

    # Trimmed layer: every named reach's geometry, tagged with whether it has
    # a chartable record, so the map can style "monitored" vs "named but no
    # usable pass yet" without shipping the observations themselves here.
    layer = prior[["reach_id", "river_group", "basin", "p_width_m", "p_wse_m", "p_length_m", "geometry"]].copy()
    layer["n_overpasses"] = layer["reach_id"].map(lambda r: getattr(summary_by_reach.get(r), "n_overpasses", 0) or 0).astype(int)
    layer["n_good_or_suspect"] = layer["reach_id"].map(lambda r: getattr(summary_by_reach.get(r), "n_good_or_suspect", 0) or 0).astype(int)
    layer["has_chart"] = layer["n_good_or_suspect"] >= MIN_GOOD_FOR_CHART
    layer["geometry"] = layer.geometry.simplify(SIMPLIFY_TOLERANCE_DEG)
    layer.to_file(OUT_LAYER, driver="GeoJSON")
    print(f"Wrote {len(layer)} reach geometries to {OUT_LAYER} ({int(layer['has_chart'].sum())} chartable)")

    n_written = 0
    for reach_id, row in summary_by_reach.items():
        if (row.n_good_or_suspect or 0) < MIN_GOOD_FOR_CHART:
            continue
        raw_series = raw_by_reach.get(reach_id)
        monthly_series = monthly_by_reach.get(reach_id)
        if raw_series is None or monthly_series is None or monthly_series.empty:
            continue

        clean_wse = raw_series["wse"].where(~raw_series["wse_outlier"])
        wse_loess = loess_fit(raw_series["time"], clean_wse, frac=0.25)
        width_loess = loess_fit(monthly_series["time"], monthly_series["width"], frac=0.35)

        payload = {
            "reach_id": reach_id,
            "river_group": row.river_group,
            "basin": row.basin,
            "river_name_raw": row.river_name_raw,
            "source": "NASA/CNES SWOT mission, SWOT_L2_HR_RiverSP_2.0 via PO.DAAC Hydrocron",
            "prior_width_m": None if pd.isna(row.p_width_m) else float(row.p_width_m),
            "prior_wse_m": None if pd.isna(row.p_wse_m) else float(row.p_wse_m),
            "observations": [
                {
                    "time": t.strftime("%Y-%m-%d"),
                    "wse_m": None if pd.isna(w) else round(float(w), 2),
                    "wse_outlier": bool(o),
                    "width_m": None if pd.isna(wd) else round(float(wd), 1),
                    "partial": bool(p),
                }
                for t, w, o, wd, p in zip(
                    raw_series["time"], raw_series["wse"], raw_series["wse_outlier"],
                    raw_series["width"], raw_series["partial_f"],
                )
            ],
            "wse_loess": [
                {"time": t.strftime("%Y-%m-%d"), "value": v}
                for t, v in zip(raw_series["time"], wse_loess)
            ],
            "width_loess": [
                {"time": t.strftime("%Y-%m-%d"), "value": v}
                for t, v in zip(monthly_series["time"], width_loess)
            ],
            "months": [
                {"time": t.strftime("%Y-%m-%d"), "wse_m": None if pd.isna(w) else round(float(w), 2),
                 "width_m": None if pd.isna(wd) else round(float(wd), 1), "n_overpasses": int(n)}
                for t, w, wd, n in zip(monthly_series["time"], monthly_series["wse"],
                                        monthly_series["width"], monthly_series["n_overpasses"])
            ],
        }
        (OUT_SWOT_DIR / f"{reach_id}.json").write_text(json.dumps(payload), encoding="utf-8")
        n_written += 1

    print(f"Wrote {n_written} per-reach SWOT time series JSON files to {OUT_SWOT_DIR}")


if __name__ == "__main__":
    main()
