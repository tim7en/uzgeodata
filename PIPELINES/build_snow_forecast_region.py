"""Run the snow-based seasonal flow forecast at every gauged Aral-drainage catchment.

Uses the regional ERA5-Land predictor grids (extract_snow_forecast_region.py) and
the scoring of build_snow_forecast_study.py, so a gauge scored here is comparable
with the single-basin studies. Also writes basin-level predictors for all 7,445
level-12 basins, locally and accumulated upstream, as input for forecasting
ungauged basins later.

Everything is written to RESEARCH/snow-forecast/region/, which is never part of
the website release.

Glacier cells: ERA5-Land holds a fixed 10 m of SWE on glacier-covered cells. A
cell whose mean September SWE exceeds 500 mm in most years is excluded from every
SWE predictor, and its share of the catchment is reported instead.

Regulation: a gauge with a dam from dams-transboundary inside its catchment is
flagged from the dam's completion year; its skill is also scored on the years
before that, when enough of them exist.

    python PIPELINES/build_snow_forecast_region.py
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

import warnings

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import rasterio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIPELINES import build_snow_forecast_study as study  # noqa: E402
from PIPELINES import extract_regional_climate_grids as grids  # noqa: E402
from PIPELINES.model_regional_climate_continuation import accumulate_one  # noqa: E402

GRIDS = ROOT / "WORKSPACE/derived/snow-forecast-region"
GAUGES = ROOT / "GEODATA/ca-discharge-2023/CA-discharge.gpkg"
LOOKUP = ROOT / "PUBLISHED/data/case-studies/gauge_basin_lookup.csv"
DAMS = ROOT / "PUBLISHED/data/hydroclimate/dams-transboundary.geojson"
LEVEL12 = ROOT / "GEODATA/transboundary_basins_v2/hydroatlas-level12-full-basins.geojson"
OUT = ROOT / "RESEARCH/snow-forecast/region"
CHECKPOINTS = GRIDS / "gauge-results"
BAND_WIDTH = 500
GLACIER_SWE_MM = 500
MIN_YEARS = 25
FIRST_WY = 1951
ISSUE_MONTH_NAMES = {1: "1 Jan", 2: "1 Feb", 3: "1 Mar", 4: "1 Apr"}


# ------------------------------------------------------------------ grids
def load_grids():
    with rasterio.open(GRIDS / "elevation.tif") as dataset:
        transform, width, height = dataset.transform, dataset.width, dataset.height
        elevation = dataset.read(1).astype(float).ravel()
    years = {}
    for path in sorted(GRIDS.glob("wy=*.tif")):
        wy = int(path.stem.split("=")[1])
        bands = json.loads(path.with_suffix(".json").read_text())["bands"]
        with rasterio.open(path) as dataset:
            data = dataset.read().astype(float)
        data[~np.isfinite(data) | (np.abs(data) > 1e6)] = np.nan
        years[wy] = {name: data[i].ravel() for i, name in enumerate(bands)}
    september = np.array([v["swe_09"] for v in years.values() if "swe_09" in v])
    glacier = np.nanmean(september > GLACIER_SWE_MM, axis=0) > .5
    return transform, width, height, elevation, years, glacier


def weights_for(frame, key, transform, width, height, name):
    """Fractional-overlap weights, cached separately from the level-12 cache."""
    grids.CACHE = ROOT / "WORKSPACE/derived/snow-forecast-region/weights" / name
    frame = frame.rename(columns={key: "basin_id"})[["basin_id", "geometry"]].reset_index(drop=True)
    index, cells, weight = grids.grid_weights(frame, transform, width, height)
    groups = {}
    for i, c, w in zip(index, cells, weight):
        groups.setdefault(frame.basin_id.iloc[i], []).append((c, w))
    return {k: (np.array([c for c, _ in v]), np.array([w for _, w in v])) for k, v in groups.items()}


# ------------------------------------------------------------------ discharge
def monthly_discharge(code, resolution):
    series = pyogrio.read_dataframe(GAUGES, layer="discharge_time_series", where=f"CODE='{code}'")
    if series.empty:
        return None
    series["date"] = pd.to_datetime(series.date)
    series["month"] = series.date.dt.to_period("M")
    need = {"decade": 3, "month": 1, "day": 25}.get(resolution, 1)
    grouped = series.groupby("month").value.agg(["mean", "count"])
    monthly = grouped[grouped["count"] >= need]["mean"]
    monthly.index = monthly.index.to_timestamp()
    extra = study.SUPPLEMENT.get(str(code))
    if extra and extra.exists():
        u = pd.read_csv(extra)
        u.index = pd.to_datetime(dict(year=u.year, month=u.month, day=1))
        monthly = pd.concat([monthly, u.discharge_mean_cms[~u.index.isin(monthly.index)]]).sort_index()
    frame = monthly.to_frame("q")
    frame["year"], frame["month"] = frame.index.year, frame.index.month
    season = frame[frame.month.between(4, 9)].groupby("year").q.agg(["mean", "count"])
    return season["mean"].where(season["count"] == 6).dropna()


# ------------------------------------------------------------------ predictors
def gauge_predictors(cells, weights, elevation, glacier, years):
    snow = ~glacier[cells]
    band = (elevation[cells] // BAND_WIDTH * BAND_WIDTH).astype(int)
    rows = {}
    for wy, grid in years.items():
        for k in (1, 2, 3, 4):
            name = f"swe_issue{k}"
            if name not in grid:
                continue
            swe = grid[name][cells]
            ok = snow & np.isfinite(swe)
            if ok.sum() == 0:
                continue
            row = {"meanSWE": np.average(swe[ok], weights=weights[ok]), "maxSWE": np.nanmax(swe[ok])}
            months = [10, 11, 12, 1, 2, 3][:k + 2]
            ppt = [grid.get(f"ppt_{m:02d}") for m in months]
            if any(p is None for p in ppt):
                continue
            total = sum(p[cells] for p in ppt)
            finite = np.isfinite(total)
            row["Prec"] = np.average(total[finite], weights=weights[finite]) if finite.any() else np.nan
            for i, m in enumerate(months, start=1):
                t = grid[f"t2m_{m:02d}"][cells]
                f = np.isfinite(t)
                row[f"Tair{i}"] = np.average(t[f], weights=weights[f]) if f.any() else np.nan
            for b in np.unique(band[ok]):
                inside = ok & (band == b)
                row[f"ebSWE{b}"] = np.average(swe[inside], weights=weights[inside])
            rows[(wy, k)] = row
    table = pd.DataFrame.from_dict(rows, orient="index")
    table.index = pd.MultiIndex.from_tuples(table.index, names=["water_year", "issue_month"])
    return table


def regulated_since(geometry, dams):
    inside = dams[dams.within(geometry)]
    years = pd.to_numeric(inside.year_completed, errors="coerce").dropna()
    return (int(years.min()) if len(years) else None), inside.dam_name.tolist()


def outlet_basin(point, area_km2, level12):
    """Level-12 basin at the gauge whose upstream area best matches the catchment area."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # a 0.05 degree search radius is intended
        near = level12[level12.distance(point) < .05]
    if near.empty:
        return None, None
    ratio = (near.UP_AREA / area_km2).apply(lambda r: abs(math.log(r)) if r > 0 else 9)
    best = near.loc[ratio.idxmin()]
    return str(int(best.HYBAS_ID)), float(best.UP_AREA / area_km2)


def score(frame, names):
    result = study.evaluate(frame, "veg", names)
    result["operational"] = {p: study.operational(frame, "veg", p) for p in ("meanSWE", "Prec")}
    return result


# ------------------------------------------------------------------ basins
def basin_predictors(years, glacier, transform, width, height):
    geo = gpd.read_file(LEVEL12)
    basins = pd.DataFrame({"basin_id": geo.HYBAS_ID.astype("int64").astype(str),
                           "next_down": geo.NEXT_DOWN.astype("int64").astype(str),
                           "area_km2": geo.SUB_AREA})
    grids.CACHE = ROOT / "WORKSPACE/derived/regional-climate-grids"
    index, cells, weight = grids.grid_weights(geo.assign(basin_id=basins.basin_id), transform, width, height)
    below = dict(zip(basins.basin_id, basins.next_down.where(basins.next_down != "0")))
    below = {b: (d if d in below else None) for b, d in below.items()}
    area = dict(zip(basins.basin_id, basins.area_km2))
    indegree = {b: 0 for b in below}
    for d in below.values():
        if d:
            indegree[d] += 1
    order, queue = [], [b for b, n in indegree.items() if n == 0]
    while queue:
        b = queue.pop()
        order.append(b)
        d = below[b]
        if d:
            indegree[d] -= 1
            if indegree[d] == 0:
                queue.append(d)
    snow_weight = weight * ~glacier[cells]
    glacier_share = np.bincount(index, weights=weight * glacier[cells], minlength=len(basins))
    rows = []
    for wy, grid in sorted(years.items()):
        if "swe_issue4" not in grid or "ppt_03" not in grid:
            continue
        swe = grid["swe_issue4"][cells]
        ok = np.isfinite(swe) & (snow_weight > 0)
        num = np.bincount(index[ok], weights=(swe * snow_weight)[ok], minlength=len(basins))
        den = np.bincount(index[ok], weights=snow_weight[ok], minlength=len(basins))
        local_swe = np.where(den > 0, num / np.where(den > 0, den, 1), np.nan)
        ppt = sum(grid[f"ppt_{m:02d}"] for m in (10, 11, 12, 1, 2, 3))[cells]
        okp = np.isfinite(ppt)
        local_ppt = np.bincount(index[okp], weights=(ppt * weight)[okp], minlength=len(basins)) / \
            np.maximum(np.bincount(index[okp], weights=weight[okp], minlength=len(basins)), 1e-12)
        up_swe = accumulate_one(dict(zip(basins.basin_id, np.where(np.isfinite(local_swe), local_swe, None))), order, below, area)
        up_ppt = accumulate_one(dict(zip(basins.basin_id, local_ppt)), order, below, area)
        for i, b in enumerate(basins.basin_id):
            rows.append({"basin_id": b, "water_year": wy,
                         "apr1_swe_mm": None if not np.isfinite(local_swe[i]) else float(local_swe[i]),
                         "oct_mar_ppt_mm": float(local_ppt[i]),
                         "up_apr1_swe_mm": up_swe[b]["mean"], "up_apr1_swe_km3": None if up_swe[b]["integral_mcm"] is None else up_swe[b]["integral_mcm"] / 1000,
                         "up_swe_coverage": up_swe[b]["coverage"],
                         "up_oct_mar_ppt_mm": up_ppt[b]["mean"]})
    table = pd.DataFrame(rows)
    shares = pd.DataFrame({"basin_id": basins.basin_id, "glacier_cell_share": glacier_share})
    return table, shares


def clean(value):
    """JSON has no NaN: missing scores become null."""
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.integer):
        return int(value)
    return value


def associate_basins(results):
    """Tie every level-12 basin to the nearest scored gauge downstream of it.

    Walking down NEXT_DOWN from a basin, the first basin that is a gauge outlet
    names the smallest gauged catchment containing it; its April 1 skill is the
    tested forecast that covers the basin. Basins with no gauge below them, or
    only a gauge whose outlet match is poor, are left unassigned.
    """
    geo = gpd.read_file(LEVEL12)
    below = dict(zip(geo.HYBAS_ID.astype("int64").astype(str), geo.NEXT_DOWN.astype("int64").astype(str)))
    outlets = {e["outlet_hybas_id"]: e for e in results
               if e.get("outlet_hybas_id") and e.get("outlet_area_ratio") and .67 <= e["outlet_area_ratio"] <= 1.5}
    rows = []
    for basin in below:
        step, hops, found = basin, 0, None
        while step and step != "0" and hops < 5000:
            if step in outlets:
                found = outlets[step]
                break
            step, hops = below.get(step), hops + 1
        april = found["issue"]["4"] if found else None
        rows.append({"basin_id": basin, "gauge_code": found["code"] if found else None,
                     "gauge_name": found["name"] if found else None,
                     "april_operational_skill": april["operational"]["meanSWE"]["all"]["skill_corrected"] if april else None,
                     "april_loyo_r2": april["loyo"]["r2"] if april else None,
                     "regulated_since": found["regulated_since"] if found else None})
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT / "basin-gauge-association.csv", index=False)
    print(f"Basins covered by a scored gauge: {frame.gauge_code.notna().sum():,} of {len(frame):,}", flush=True)


# ------------------------------------------------------------------ main
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    transform, width, height, elevation, years, glacier = load_grids()
    print(f"{len(years)} water years, {glacier.sum()} glacier cells screened", flush=True)
    registry = pyogrio.read_dataframe(GAUGES, layer="gauges")
    lookup = pd.read_csv(LOOKUP)
    aral = set(lookup[lookup.aral_drainage].gauge_code.astype(str))
    registry = registry[registry.CODE.astype(str).isin(aral) & (registry.has_ts == 1)]
    catchments = pyogrio.read_dataframe(GAUGES, layer="basins")
    catchments = catchments[catchments.CODE.astype(str).isin(set(registry.CODE.astype(str)))]
    catchments["CODE"] = catchments.CODE.astype(str)
    cell_sets = weights_for(catchments, "CODE", transform, width, height, "gauges")
    dams = gpd.read_file(DAMS)
    level12 = gpd.read_file(LEVEL12)[["HYBAS_ID", "UP_AREA", "geometry"]]
    results, links = [], []
    for gauge in registry.itertuples():
        code = str(gauge.CODE)
        if code not in cell_sets:
            continue
        catchment = catchments[catchments.CODE == code].iloc[0]
        veg = monthly_discharge(code, gauge.res)
        if veg is None:
            continue
        veg = veg[veg.index >= FIRST_WY]
        if len(veg) < MIN_YEARS:
            continue
        cached = CHECKPOINTS / f"{code}.json"
        if cached.exists():
            entry = json.loads(cached.read_text())
            results.append(entry)
            links.append({"gauge_code": code, "outlet_hybas_id": entry["outlet_hybas_id"],
                          "outlet_area_ratio": entry["outlet_area_ratio"],
                          "catchment_area_km2": entry["area_km2"], "regulated_since": entry["regulated_since"]})
            continue
        cells, weights = cell_sets[code]
        table = gauge_predictors(cells, weights, elevation, glacier, years)
        since, dam_names = regulated_since(catchment.geometry, dams)
        hybas, area_ratio = outlet_basin(gpd.points_from_xy([gauge.LON], [gauge.LAT])[0],
                                         catchment.area_km2, level12)
        entry = {"code": code, "name": gauge.NAME_ENG, "river": gauge.RIVER, "basin": gauge.BASIN,
                 "lon": float(gauge.LON), "lat": float(gauge.LAT), "area_km2": float(catchment.area_km2),
                 "cells": int(len(cells)), "glacier_cell_share": float(weights[glacier[cells]].sum()),
                 "veg_years": [int(veg.index.min()), int(veg.index.max())], "n_years": int(len(veg)),
                 "veg_mean_m3s": float(veg.mean()), "regulated_since": since, "dams": dam_names,
                 "outlet_hybas_id": hybas, "outlet_area_ratio": area_ratio, "issue": {}}
        for k in (1, 2, 3, 4):
            frame = table.xs(k, level="issue_month").join(veg.rename("veg"), how="inner")
            names = [c for c in frame.columns if c != "veg" and frame[c].notna().all() and frame[c].std() > 1e-6]
            if len(frame) < MIN_YEARS or "meanSWE" not in names:
                continue
            scored = score(frame, names)
            if since and (frame.index < since).sum() >= MIN_YEARS:
                natural = frame[frame.index < since]
                scored["pre_regulation"] = {"years": [int(natural.index.min()), int(natural.index.max())],
                                            "loyo_r2": study.evaluate(natural, "veg", names)["loyo"]["r2"]}
            entry["issue"][str(k)] = scored
        if "4" not in entry["issue"]:
            continue
        a = entry["issue"]["4"]
        print(f"{code} {gauge.NAME_ENG[:28]:28} {entry['area_km2']:8.0f} km2 n={entry['n_years']:2d} "
              f"reg={since or '-':>4} | Apr in {a['in_sample']['adj_r2']:.2f} loyo {a['loyo']['r2']:.2f} "
              f"op {a['operational']['meanSWE']['all']['skill_corrected']:.2f}", flush=True)
        entry = clean(entry)
        cached.write_text(json.dumps(entry, allow_nan=False) + "\n")
        results.append(entry)
        links.append({"gauge_code": code, "outlet_hybas_id": hybas, "outlet_area_ratio": area_ratio,
                      "catchment_area_km2": entry["area_km2"], "regulated_since": since})
    report = {"generated_at": datetime.now(timezone.utc).isoformat(),
              "visibility": "internal research; never part of the website release",
              "predictors": "ERA5-Land native grid, glacier cells screened, 500 m elevation bands",
              "target": "April-September mean discharge (m3/s)",
              "scoring": "as build_snow_forecast_study.py: in-sample adj R2 + bootstrap, LOYO with selection inside folds, "
                         "operational expanding-window hindcast with ten-year level correction vs previous 30-year mean",
              "gauges": results}
    (OUT / "gauges.json").write_text(json.dumps(clean(report), indent=1, allow_nan=False) + "\n")
    pd.DataFrame(links).to_csv(OUT / "gauge-basin-links.csv", index=False)
    summary = [{"code": e["code"], "name": e["name"], "basin": e["basin"], "area_km2": round(e["area_km2"]),
                "glacier_cell_share": round(e["glacier_cell_share"], 3), "n_years": e["n_years"],
                "regulated_since": e["regulated_since"], "outlet_hybas_id": e["outlet_hybas_id"],
                **{f"{m}_{k}": (None if v is None else round(v, 3)) for k, i in e["issue"].items() for m, v in (
                    ("insample", i["in_sample"]["adj_r2"]), ("loyo", i["loyo"]["r2"]),
                    ("operational", i["operational"]["meanSWE"]["all"]["skill_corrected"]),
                    ("operational_recent", (i["operational"]["meanSWE"]["recent"] or {}).get("skill_corrected")))}}
               for e in results]
    pd.DataFrame(summary).to_csv(OUT / "gauge-skill.csv", index=False)
    print(f"Scored {len(results)} gauges", flush=True)

    associate_basins(results)
    table, shares = basin_predictors(years, glacier, transform, width, height)
    table.to_parquet(OUT / "basin-predictors.parquet", compression="zstd", index=False)
    shares.to_csv(OUT / "basin-glacier-cell-share.csv", index=False)
    print(f"Basin predictors: {len(table):,} rows", flush=True)


if __name__ == "__main__":
    main()
