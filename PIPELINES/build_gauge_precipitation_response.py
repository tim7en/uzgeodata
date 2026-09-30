"""Measured river flow against catchment precipitation, gauge by gauge.

python PIPELINES/build_gauge_precipitation_response.py

Why. The basin reports can say how much precipitation fell and how much snow the
model stored, but not whether that reached the river: nothing in them is measured
flow. This sets the CA-discharge gauge records (Marti et al. 2023) against the
TerraClimate v1.1 precipitation that fell on each gauge's own catchment, water year by
water year, so a report can say how strongly flow at a gauge has followed
precipitation - and a reader can see where it has not (reservoirs, glacier melt,
irrigation withdrawals).

How.
- Flow: monthly means from the compilation's monthly series, or from its 10-day series
  where all three periods of a month are present, or daily series with 25+ days. A
  water year (October-September) needs all twelve months. Mean m3/s becomes a runoff
  depth over the gauge's own catchment area.
- Precipitation: each gauge catchment polygon (shipped with CA-discharge) is overlaid on
  the level-12 basins in an equal-area projection; catchment precipitation is the
  overlap-weighted mean of the basins' v1.1 water-year totals. Gauges whose catchment
  the level-12 frame covers less than 90% of are left out.
- Per gauge with 10+ paired water years: correlation of the two series, the median
  precipitation elasticity of flow (Sankarasubramanian et al. 2001), the runoff ratio,
  and how often a year with precipitation 15%+ below its mean had flow below its median.
- Where the gauge record reaches 2004+, the modelled runoff of TerraClimate v1.1 and
  ERA5-Land over the same catchment and years is set against the measured depth: the two
  products differ about twofold, and this is the first measured reference for them.

Writes PUBLISHED/data/research/gauge-precipitation-response.json.
"""
from __future__ import annotations

import gzip
import json
import math
from pathlib import Path
import sqlite3
import sys

import duckdb
import geopandas as gpd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core.runtime import utc_now, write_json

GPKG = ROOT / "GEODATA/ca-discharge-2023/CA-discharge.gpkg"
FRAME = ROOT / "GEODATA/transboundary_basins_v2/hydroatlas-level12-full-basins.geojson"
HISTORY = ROOT / "PUBLISHED/data/atlas/climate-continuation/terraclimate-v1.1-history"
CATCHMENTS = ROOT / "PUBLISHED/data/atlas/catchments/index.json"
OUT = ROOT / "PUBLISHED/data/research/gauge-precipitation-response.json"
EQUAL_AREA = "EPSG:6933"
MIN_COVERAGE, MIN_YEARS, DRY = 0.9, 10, -15.0
SECONDS_PER_YEAR = 365.2425 * 86400
ATTRIBUTION = ("Marti, B., Siegfried, T., Yakovlev, A., Zhumabaev, A., Karger, D., Wakil, A. W., Ragettli, S. (2023). "
               "CA-discharge data set, scripts and raw data. Zenodo, doi:10.5281/zenodo.8147591. CC BY 4.0.")


def monthly_flow():
    """{code: {(year, month): m3/s}} from the best series each gauge has."""
    connection = sqlite3.connect(GPKG)
    rows = connection.execute("SELECT CODE, res, date, value FROM discharge_time_series WHERE value IS NOT NULL").fetchall()
    connection.close()
    parts = {}
    for code, res, date, value in rows:
        year, month = int(date[:4]), int(date[5:7])
        parts.setdefault((str(code), res), {}).setdefault((year, month), []).append(float(value))
    flows = {}
    for (code, res), months in parts.items():
        need = {"month": 1, "decade": 3, "day": 25}[res]
        series = {key: sum(v) / len(v) for key, v in months.items() if len(v) >= need}
        # Keep whichever resolution gives the gauge the most complete months.
        if len(series) > len(flows.get(code, {})):
            flows[code] = series
    return flows


def water_years(series):
    """{water year: mean} where all twelve months are present."""
    out = {}
    for wy in {y + (m >= 10) for y, m in series}:
        months = [(wy - 1, m) for m in (10, 11, 12)] + [(wy, m) for m in range(1, 10)]
        if all(k in series for k in months):
            out[wy] = sum(series[k] for k in months) / 12
    return out


def catchment_weights():
    """{code: ({basin_id: overlap km2}, gauge area km2, coverage)} in an equal-area projection."""
    gauges = gpd.read_file(GPKG, layer="basins")[["CODE", "area_km2", "geometry"]].to_crs(EQUAL_AREA)
    frame = gpd.read_file(FRAME, columns=["HYBAS_ID"]).to_crs(EQUAL_AREA)
    frame["basin_id"] = frame.HYBAS_ID.astype("int64").astype(str)
    pieces = gpd.overlay(gauges, frame[["basin_id", "geometry"]], how="intersection", keep_geom_type=True)
    pieces["km2"] = pieces.area / 1e6
    out = {}
    for code, group in pieces.groupby("CODE"):
        polygon = gauges.loc[gauges.CODE == code]
        area = float(polygon.area.sum() / 1e6)
        out[str(code)] = (dict(zip(group.basin_id, group.km2)), float(polygon.area_km2.iloc[0]), group.km2.sum() / area if area else 0)
    return out


def basin_water_years(basins, variable):
    """{basin: {water year: total}} from the v1.1 history, complete water years only."""
    ids = ", ".join(f"'{b}'" for b in basins)
    frame = duckdb.connect().execute(f"""
      WITH m AS (SELECT CAST(basin_id AS VARCHAR) basin_id, value,
                        CASE WHEN month >= 10 THEN year + 1 ELSE year END AS wy
                 FROM read_parquet('{(HISTORY / 'year=*.parquet').as_posix()}')
                 WHERE variable = '{variable}' AND CAST(basin_id AS VARCHAR) IN ({ids}))
      SELECT basin_id, wy, sum(value), count(*) FROM m GROUP BY 1, 2""").fetchall()
    out = {}
    for basin, wy, total, n in frame:
        if n == 12:
            out.setdefault(basin, {})[int(wy)] = float(total)
    return out


def era5_water_years(basins):
    """{basin: {water year: ERA5-Land runoff total}} from the served catchment matrix."""
    index = json.loads(CATCHMENTS.read_text(encoding="utf-8"))
    ids = [str(x) for x in index["ids"]]
    n, months = len(ids), index["months"]
    raw = np.frombuffer(gzip.decompress((ROOT / "PUBLISHED" / index["series"]["run_mm_s"]["url"].lstrip("/")).read_bytes()), np.uint8)
    planes = raw.reshape(4, n * months).astype(np.uint32)
    coded = (planes[0] | planes[1] << 8 | planes[2] << 16 | planes[3] << 24).view(np.int32)
    values = (np.cumsum(coded.reshape(n, months).astype(np.int64), axis=1) + 2**31) % 2**32 - 2**31
    matrix = np.where(values == index["null_sentinel"], np.nan, values / index["scale"])
    start = index["years"][0]
    position = {b: i for i, b in enumerate(ids)}
    out = {}
    for basin in basins:
        if basin not in position:
            continue
        row = matrix[position[basin]]
        for wy in range(start + 1, start + months // 12):
            slots = range((wy - 1 - start) * 12 + 9, (wy - start) * 12 + 9)
            vals = [row[s] for s in slots]
            if all(np.isfinite(vals)):
                out.setdefault(basin, {})[wy] = float(sum(vals))
    return out


def weighted(weights, per_basin):
    """Overlap-weighted catchment series over the years every overlapping basin has."""
    years = None
    for basin in weights:
        have = set(per_basin.get(basin, {}))
        years = have if years is None else years & have
    total = sum(weights.values())
    return {wy: sum(w * per_basin[b][wy] for b, w in weights.items()) / total for wy in sorted(years or [])}


def statistics(flow, rain):
    years = sorted(set(flow) & set(rain))
    q = np.array([flow[y] for y in years]); p = np.array([rain[y] for y in years])
    qm, pm = q.mean(), p.mean()
    r = float(np.corrcoef(q, p)[0, 1]) if q.std() > 0 and p.std() > 0 else None
    ranks = lambda a: np.argsort(np.argsort(a))
    rho = float(np.corrcoef(ranks(q), ranks(p))[0, 1]) if len(years) > 2 else None
    with np.errstate(divide="ignore", invalid="ignore"):
        ratios = ((q - qm) / (p - pm)) * (pm / qm)
    ratios = ratios[np.isfinite(ratios) & (np.abs(p - pm) > 0.01 * pm)]
    p_anom = (p / pm - 1) * 100
    dry = p_anom <= DRY
    return {"years": [years[0], years[-1]], "n": len(years), "mean_runoff_mm": float(qm), "mean_precipitation_mm": float(pm),
            "runoff_ratio": float(qm / pm) if pm else None, "r": r, "spearman": rho,
            "elasticity": float(np.median(ratios)) if ratios.size else None,
            "dry_years": int(dry.sum()),
            "dry_years_with_low_flow": int((dry & (q < np.median(q))).sum())}


def build():
    flows = monthly_flow()
    weights = catchment_weights()
    connection = sqlite3.connect(GPKG)
    meta = {str(c): dict(zip(("name", "name_ru", "river", "country", "basin", "lon", "lat"), rest))
            for c, *rest in connection.execute("SELECT CODE, NAME_ENG, NAME_RU, RIVER, COUNTRY, BASIN, LON, LAT FROM gauges")}
    connection.close()
    basins = sorted({b for w, _, _ in weights.values() for b in w})
    ppt = basin_water_years(basins, "ppt")
    tc_q = basin_water_years(basins, "q")
    era = era5_water_years(basins)

    gauges, skipped = [], {"no_complete_water_year": 0, "catchment_outside_frame": 0, "too_few_paired_years": 0}
    for code, series in flows.items():
        flow_wy = water_years(series)
        if not flow_wy:
            skipped["no_complete_water_year"] += 1
            continue
        if code not in weights or weights[code][2] < MIN_COVERAGE:
            skipped["catchment_outside_frame"] += 1
            continue
        w, area, coverage = weights[code]
        depth = {wy: q * SECONDS_PER_YEAR / (area * 1e6) * 1000 for wy, q in flow_wy.items()}
        rain = weighted(w, ppt)
        if len(set(depth) & set(rain)) < MIN_YEARS:
            skipped["too_few_paired_years"] += 1
            continue
        entry = {"code": code, **{k: v for k, v in meta.get(code, {}).items() if v is not None},
                 "area_km2": area, "frame_coverage": round(coverage, 3),
                 "stats": statistics(depth, rain),
                 "series": [[wy, round(depth[wy], 1), round(rain[wy], 1)] for wy in sorted(set(depth) & set(rain))]}
        modelled = {}
        for name, per_basin in (("terraclimate_v1_1", tc_q), ("era5_land", era)):
            model = weighted(w, per_basin)
            common = sorted(set(model) & set(depth))
            if len(common) >= 5:
                measured = float(np.mean([depth[y] for y in common]))
                modelled[name] = {"years": [common[0], common[-1]], "n": len(common), "measured_mm": measured,
                                  "modelled_mm": float(np.mean([model[y] for y in common])),
                                  "ratio": float(np.mean([model[y] for y in common]) / measured) if measured else None}
        if modelled:
            entry["modelled_runoff"] = modelled
        gauges.append(entry)
    gauges.sort(key=lambda g: -g["stats"]["n"])

    def median(key, sub=None):
        vals = [(g[sub][key] if sub else g["stats"][key]) for g in gauges if (g.get(sub) if sub else True)]
        vals = [v for v in vals if v is not None]
        return float(np.median(vals)) if vals else None
    compared = [g for g in gauges if "modelled_runoff" in g]
    ratio = lambda name: [g["modelled_runoff"][name]["ratio"] for g in compared if name in g["modelled_runoff"] and g["modelled_runoff"][name]["ratio"]]
    summary = {
        "gauges": len(gauges), "skipped": skipped,
        "median_r": median("r"), "median_elasticity": median("elasticity"), "median_runoff_ratio": median("runoff_ratio"),
        "gauges_r_above_0_6": sum(1 for g in gauges if (g["stats"]["r"] or 0) >= 0.6),
        "gauges_r_below_0_3": sum(1 for g in gauges if (g["stats"]["r"] or 0) < 0.3),
        "modelled_runoff": {name: {"gauges": len(ratio(name)), "median_ratio_to_measured": float(np.median(ratio(name))) if ratio(name) else None,
                                   "within_factor_1_5": sum(1 for v in ratio(name) if 1 / 1.5 <= v <= 1.5)}
                            for name in ("terraclimate_v1_1", "era5_land")},
    }
    result = {
        "generated_at": utc_now(), "attribution": ATTRIBUTION,
        "method": {"flow": "CA-discharge monthly, 10-day (all three) or daily (25+ days) means; water years October-September, all twelve months",
                   "precipitation": "TerraClimate v1.1 water-year totals of the level-12 basins overlapping the gauge's delineated catchment, overlap-weighted in EPSG:6933",
                   "elasticity": "median of ((Q - Qmean)/(P - Pmean)) x (Pmean/Qmean) over years (Sankarasubramanian, Vogel and Limbrunner 2001)",
                   "dry_year": f"catchment precipitation {int(-DRY)}% or more below its mean over the paired years",
                   "minimum_years": MIN_YEARS, "minimum_frame_coverage": MIN_COVERAGE},
        "reading": "Measured flow integrates what precipitation alone does not: glacier melt, reservoir operation and "
                   "withdrawals upstream of the gauge. A weak correlation is information about the catchment, not an error "
                   "in either record. Most records end by 2021, so they describe how a catchment has responded, not this year.",
        "summary": summary, "gauges": gauges,
    }
    write_json(OUT, result)
    return summary


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
