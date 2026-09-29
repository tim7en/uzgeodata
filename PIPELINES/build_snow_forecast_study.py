"""Seasonal flow forecasting from snow, and snow and flow trends, for one gauge.

Adapts the design of Barnhart et al. (USGS and Uzhydromet HMRI, Kashkadarya) to a
basin without a SnowModel reanalysis. Their predictors come from SnowModel forced
with downscaled ERA5-Land (data release doi:10.5066/P1IHVOVG); here they come from
ERA5-Land itself on its 0.1 degree grid (extract_snow_forecast_forcing.py). Whether
that coarser snow still carries the forecast signal is what this study tests.

Target: vegetation-season (April-September) mean discharge, the irrigation season,
and single target months April-September. Forecasts are issued on the 1st of
January (forecast month 1) through April (4), using only information from before
the issue date:

  meanSWE, maxSWE   basin mean and cell maximum SWE on the day before issue
  ebSWE<band>       mean SWE of the cells in each 200 m elevation band
  Prec              basin precipitation summed from 1 October to the day before issue
  Tair<month>       basin mean air temperature of each month from October on

Models are ordinary least squares with at most three predictors, chosen by
adjusted R2 from every subset. Three skill measures are reported:

  in-sample   adjusted R2 of the chosen model on all years, with a 1,000-sample
              bootstrap of years (comparable to the USGS figures);
  LOYO CV     leave-one-year-out, with the predictor search repeated inside every
              fold so the held-out year never influences the choice;
  split       fitted on water years to 1995 and tested on 1996 onward.

Trends use Mann-Kendall (tie-corrected) with Sen's slope.

    python PIPELINES/build_snow_forecast_study.py --gauge 16290
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from itertools import combinations
import json
import math
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pyogrio
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
GAUGES = ROOT / "GEODATA/ca-discharge-2023/CA-discharge.gpkg"
FORCING = ROOT / "RESEARCH/snow-forecast"
# Uzhydromet monthly workbooks that extend a CA-discharge record past 2016.
SUPPLEMENT = {"16290": ROOT / "PUBLISHED/data/hydroclimate/pskem-discharge-monthly.csv"}
BAND_WIDTH = 200
ISSUE_MONTHS = (1, 2, 3, 4)
TARGET_MONTHS = (4, 5, 6, 7, 8, 9)
MAX_PREDICTORS = 3
SPLIT_YEAR = 1995
RNG = np.random.default_rng(20260929)


# ---------------------------------------------------------------- discharge
def discharge(code):
    series = pyogrio.read_dataframe(GAUGES, layer="discharge_time_series", where=f"CODE='{code}'")
    series["date"] = pd.to_datetime(series.date)
    series["month"] = series.date.dt.to_period("M")
    monthly = series.groupby("month").value.agg(["mean", "count"])
    monthly = monthly[monthly["count"] == 3]["mean"].rename("q")  # all three decades present
    monthly.index = monthly.index.to_timestamp()
    source = pd.Series("ca-discharge", index=monthly.index)
    extra = SUPPLEMENT.get(code)
    if extra and extra.exists():
        u = pd.read_csv(extra)
        u.index = pd.to_datetime(dict(year=u.year, month=u.month, day=1))
        u = u.discharge_mean_cms
        overlap = pd.concat([monthly, u], axis=1, join="inner")
        agreement = {"months": len(overlap), "r": float(overlap.corr().iloc[0, 1]),
                     "mean_ratio": float((overlap.iloc[:, 1] / overlap.iloc[:, 0]).mean())}
        added = u[~u.index.isin(monthly.index)]
        monthly = pd.concat([monthly, added]).sort_index()
        source = pd.concat([source, pd.Series("uzhydromet", index=added.index)]).sort_index()
    else:
        agreement = None
    frame = pd.DataFrame({"q": monthly, "source": source})
    frame["year"], frame["month"] = frame.index.year, frame.index.month
    frame["water_year"] = frame.year + (frame.month >= 10)
    return frame, agreement, series


def seasons(monthly, decadal):
    """Vegetation-season mean, single target months, and centre-of-volume timing per water year."""
    season = monthly[monthly.month.between(4, 9)].groupby("year").q.agg(["mean", "count"])
    targets = pd.DataFrame({"veg": season["mean"].where(season["count"] == 6)})
    for m in TARGET_MONTHS:
        targets[f"m{m}"] = monthly[monthly.month == m].set_index("year").q
    # Centre of volume: day of the water year by which half the water-year flow has
    # passed, from the 10-day record (resolution about ten days).
    d = decadal.copy()
    d["wy"] = d.date.dt.year + (d.date.dt.month >= 10)
    start = pd.to_datetime(d.wy.astype(str) + "-10-01") - pd.DateOffset(years=1)
    d["dowy"] = (d.date - start).dt.days + 1
    timing = {}
    for wy, g in d.groupby("wy"):
        if len(g) < 36:
            continue
        g = g.sort_values("dowy")
        cumulative = g.value.cumsum() / g.value.sum()
        timing[wy] = int(g.dowy.iloc[int(np.argmax(cumulative.to_numpy() >= .5))])
    targets["centre_of_volume_dowy"] = pd.Series(timing)
    return targets.sort_index()


# ---------------------------------------------------------------- predictors
def forcing(code):
    cells = json.loads((FORCING / code / "cells.json").read_text())
    table = pd.DataFrame(cells["cells"])
    table["band"] = (table.elevation_m // BAND_WIDTH * BAND_WIDTH).astype(int)
    con = duckdb.connect()
    con.register("cells", table[["cell", "weight", "band"]])
    daily = con.execute(f"""
      SELECT CAST(date AS DATE) AS date, variable,
             sum(value * weight) AS basin, max(value) AS cell_max
      FROM read_parquet('{FORCING / code / 'year=*.parquet'}') JOIN cells USING (cell)
      GROUP BY 1, 2 ORDER BY 1
    """).df()
    bands = con.execute(f"""
      SELECT CAST(date AS DATE) AS date, band, sum(value * weight) / sum(weight) AS swe
      FROM read_parquet('{FORCING / code / 'year=*.parquet'}') JOIN cells USING (cell)
      WHERE variable = 'swe_mm' GROUP BY 1, 2
    """).df()
    wide = daily.pivot(index="date", columns="variable", values="basin")
    wide["swe_max_cell"] = daily[daily.variable == "swe_mm"].set_index("date").cell_max
    wide.index = pd.to_datetime(wide.index)
    band_wide = bands.pivot(index="date", columns="band", values="swe")
    band_wide.index = pd.to_datetime(band_wide.index)
    band_wide.columns = [f"ebSWE{b}" for b in band_wide.columns]
    band_area = table.groupby("band").weight.sum()
    return wide, band_wide, cells, {f"ebSWE{b}": float(w) for b, w in band_area.items()}


def predictors_for(wide, band_wide, wy, issue_month):
    issue = pd.Timestamp(wy, issue_month, 1)
    day_before = issue - pd.Timedelta(days=1)
    start = pd.Timestamp(wy - 1, 10, 1)
    if day_before not in wide.index or start not in wide.index:
        return None
    row = {"meanSWE": wide.at[day_before, "swe_mm"], "maxSWE": wide.at[day_before, "swe_max_cell"],
           "Prec": wide.loc[start:day_before, "ppt_mm"].sum()}
    for k, month in enumerate([10, 11, 12, 1, 2, 3], start=1):
        month_start = pd.Timestamp(wy - 1 if month >= 10 else wy, month, 1)
        if month_start >= issue:
            break
        month_end = month_start + pd.offsets.MonthEnd(0)
        row[f"Tair{k}"] = wide.loc[month_start:month_end, "t2m_c"].mean()
    for column in band_wide.columns:
        row[column] = band_wide.at[day_before, column]
    return row


# ---------------------------------------------------------------- regression
def fit(X, y):
    A = np.column_stack([np.ones(len(y)), X])
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    residual = y - A @ beta
    sse, sst = residual @ residual, ((y - y.mean()) ** 2).sum()
    n, p = len(y), X.shape[1]
    r2 = 1 - sse / sst
    adj = 1 - (1 - r2) * (n - 1) / (n - p - 1)
    f = (r2 / p) / ((1 - r2) / (n - p - 1)) if r2 < 1 else np.inf
    return beta, adj, float(stats.f.sf(f, p, n - p - 1))


def select(X, y, names):
    """Best subset (size 1..MAX_PREDICTORS) by adjusted R2; drops near-constant columns."""
    usable = [i for i in range(X.shape[1]) if np.nanstd(X[:, i]) > 1e-6]
    best = (-np.inf, None)
    for size in range(1, MAX_PREDICTORS + 1):
        for combo in combinations(usable, size):
            _, adj, _ = fit(X[:, combo], y)
            if adj > best[0]:
                best = (adj, combo)
    return best[1]


def evaluate(frame, target, names):
    data = frame.dropna(subset=[target, *names])
    years = data.index.to_numpy()
    X, y = data[names].to_numpy(float), data[target].to_numpy(float)
    chosen = select(X, y, names)
    beta, adj, p = fit(X[:, chosen], y)
    # Bootstrap the chosen model over resampled years.
    boot_adj, boot_p = [], []
    for _ in range(1000):
        idx = RNG.integers(0, len(y), len(y))
        if np.unique(idx).size < len(chosen) + 3:
            continue
        _, a, pv = fit(X[idx][:, chosen], y[idx])
        boot_adj.append(a)
        boot_p.append(pv)
    # Leave-one-year-out with selection inside each fold.
    cv = np.empty(len(y))
    fold_choices = {}
    for i in range(len(y)):
        keep = np.arange(len(y)) != i
        combo = select(X[keep], y[keep], names)
        b, _, _ = fit(X[keep][:, combo], y[keep])
        cv[i] = b[0] + X[i, combo] @ b[1:]
        for c in combo:
            fold_choices[names[c]] = fold_choices.get(names[c], 0) + 1
    # Climatology forecast for the same folds: the mean of the other years.
    clim = np.array([y[np.arange(len(y)) != i].mean() for i in range(len(y))])
    sst = ((y - y.mean()) ** 2).sum()
    cv_r2 = 1 - ((y - cv) ** 2).sum() / sst
    # Chronological split.
    train, test = years <= SPLIT_YEAR, years > SPLIT_YEAR
    split = None
    if train.sum() > 15 and test.sum() > 8:
        combo = select(X[train], y[train], names)
        b, _, _ = fit(X[train][:, combo], y[train])
        pred = b[0] + X[test][:, combo] @ b[1:]
        split = {"train": [int(years[train].min()), int(years[train].max())],
                 "test": [int(years[test].min()), int(years[test].max())],
                 "predictors": [names[c] for c in combo],
                 "nse": float(1 - ((y[test] - pred) ** 2).sum() / ((y[test] - y[test].mean()) ** 2).sum()),
                 "rmse": float(np.sqrt(((y[test] - pred) ** 2).mean())),
                 "bias": float((pred - y[test]).mean()),
                 "climatology_rmse": float(np.sqrt(((y[test] - y[train].mean()) ** 2).mean()))}
    return {
        "years": [int(years.min()), int(years.max())], "n": int(len(y)),
        "predictors": [names[c] for c in chosen],
        "coefficients": [float(v) for v in beta],
        "in_sample": {"adj_r2": float(adj), "p_value": p,
                      "bootstrap_adj_r2": [float(np.percentile(boot_adj, q)) for q in (5, 50, 95)],
                      "bootstrap_p_median": float(np.median(boot_p))},
        "loyo": {"r2": float(cv_r2), "rmse": float(np.sqrt(((y - cv) ** 2).mean())),
                 "climatology_rmse": float(np.sqrt(((y - clim) ** 2).mean())),
                 "skill_vs_climatology": float(1 - ((y - cv) ** 2).sum() / ((y - clim) ** 2).sum()),
                 "predictor_frequency": {k: v / len(y) for k, v in sorted(fold_choices.items(), key=lambda kv: -kv[1])}},
        "split": split,
        "series": [[int(yr), float(o), float(f)] for yr, o, f in zip(years, y, cv)],
    }


# ---------------------------------------------------------------- operational hindcast
HINDCAST_START = 1971
CORRECTION_YEARS = 10
OPERATIONAL_PREDICTORS = ("meanSWE", "Prec")


def operational(frame, target, predictor):
    """Forecast each year from earlier years only, as a forecaster on the issue date could.

    The regression is refitted on every year before the one forecast (expanding
    window), then shifted by the mean error of the previous ten years. The shift
    tracks slow drift in how much flow a unit of snow yields; without it the
    fitted level lags behind. Skill is measured against the mean of the previous
    30 years, the forecast a water manager would otherwise use.
    """
    data = frame[[predictor, target]].dropna()
    rows = []
    for year in data.index:
        if year < HINDCAST_START:
            continue
        past = data.loc[:year - 1]
        if len(past) < 15:
            continue
        X = np.column_stack([np.ones(len(past)), past[predictor]])
        beta = np.linalg.lstsq(X, past[target].to_numpy(), rcond=None)[0]
        residual = past[target].to_numpy() - X @ beta
        raw = beta[0] + beta[1] * data.at[year, predictor]
        rows.append((int(year), float(data.at[year, target]), float(raw),
                     float(raw + residual[-CORRECTION_YEARS:].mean()),
                     float(past[target].iloc[-30:].mean())))
    table = pd.DataFrame(rows, columns=["year", "observed", "raw", "corrected", "climatology"]).set_index("year")

    def score(part):
        base = ((part.observed - part.climatology) ** 2).sum()
        return {"years": [int(part.index.min()), int(part.index.max())], "n": int(len(part)),
                **{f"skill_{k}": float(1 - ((part.observed - part[k]) ** 2).sum() / base) for k in ("raw", "corrected")},
                **{f"rmse_{k}": float(np.sqrt(((part.observed - part[k]) ** 2).mean()))
                   for k in ("raw", "corrected", "climatology")},
                **{f"bias_{k}": float((part[k] - part.observed).mean()) for k in ("raw", "corrected")}}
    return {"predictor": predictor,
            "all": score(table), "recent": score(table.loc[1996:]) if (table.index >= 1996).sum() >= 8 else None,
            "series": [[y, *[round(v, 2) for v in r]] for y, r in zip(table.index, table.to_numpy())]}


# ---------------------------------------------------------------- trends
def mann_kendall(values):
    x = np.asarray(values, float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 10:
        return None
    s = sum(np.sign(x[j] - x[i]) for i in range(n - 1) for j in range(i + 1, n))
    _, counts = np.unique(x, return_counts=True)
    var = (n * (n - 1) * (2 * n + 5) - sum(t * (t - 1) * (2 * t + 5) for t in counts)) / 18
    z = (s - np.sign(s)) / math.sqrt(var) if s else 0.0
    slopes = [(x[j] - x[i]) / (j - i) for i in range(n - 1) for j in range(i + 1, n)]
    return {"n": n, "p_value": float(2 * stats.norm.sf(abs(z))), "sen_slope_per_decade": float(np.median(slopes) * 10)}


def trend(series, first=None):
    s = series.dropna()
    if first:
        s = s[s.index >= first]
    result = mann_kendall(s.to_numpy())
    if result:
        result["years"] = [int(s.index.min()), int(s.index.max())]
    return result


def snow_trends(wide, band_wide, last_wy):
    """Peak SWE and its timing (day of water year) per water year, basin and bands; DJF climate."""
    swe = pd.concat([wide.swe_mm.rename("basin"), band_wide], axis=1)
    swe["wy"] = swe.index.year + (swe.index.month >= 10)
    out = {}
    peaks, timing = {}, {}
    for wy, g in swe.groupby("wy"):
        if len(g) < 360 or wy > last_wy:
            continue
        start = pd.Timestamp(wy - 1, 10, 1)
        for column in g.columns.drop("wy"):
            peaks.setdefault(column, {})[wy] = float(g[column].max())
            timing.setdefault(column, {})[wy] = int((g[column].idxmax() - start).days + 1)
    for column in peaks:
        out[column] = {"peak_swe": trend(pd.Series(peaks[column])),
                       "peak_timing": trend(pd.Series(timing[column]))}
    djf = wide[wide.index.month.isin([12, 1, 2])].copy()
    djf["wy"] = djf.index.year + (djf.index.month >= 10)
    groups = djf.groupby("wy")
    out["djf_temperature"] = trend(groups.t2m_c.mean()[groups.size() >= 89])
    out["djf_precipitation"] = trend(groups.ppt_mm.sum()[groups.size() >= 89])
    return out, {k: {str(y): v for y, v in d.items()} for k, d in peaks.items() if k == "basin"}, \
        {str(y): v for y, v in timing["basin"].items()}


# ---------------------------------------------------------------- main
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gauge", required=True)
    args = parser.parse_args()
    code = args.gauge
    gauge = pyogrio.read_dataframe(GAUGES, layer="gauges", where=f"CODE='{code}'").iloc[0]
    monthly, agreement, decadal = discharge(code)
    targets = seasons(monthly, decadal)
    wide, band_wide, cells, band_area = forcing(code)
    first_wy = wide.index.min().year + 1
    rows = {}
    for wy in range(first_wy, int(wide.index.max().year) + 1):
        for f in ISSUE_MONTHS:
            p = predictors_for(wide, band_wide, wy, f)
            if p:
                rows[(wy, f)] = p
    table = pd.DataFrame.from_dict(rows, orient="index")
    table.index = pd.MultiIndex.from_tuples(table.index, names=["water_year", "issue_month"])

    results = {"vegetation_season": {}, "monthly": {}}
    for f in ISSUE_MONTHS:
        frame = table.xs(f, level="issue_month").join(targets, how="inner")
        names = [c for c in table.columns if c in frame and frame[c].notna().all()]
        results["vegetation_season"][str(f)] = evaluate(frame, "veg", names)
        v = results["vegetation_season"][str(f)]
        print(f"veg season, issue month {f}: {v['predictors']} in-sample adjR2 {v['in_sample']['adj_r2']:.2f} "
              f"| LOYO R2 {v['loyo']['r2']:.2f} skill {v['loyo']['skill_vs_climatology']:.2f} "
              f"| split NSE {v['split']['nse'] if v['split'] else float('nan'):.2f}", flush=True)
        for m in TARGET_MONTHS:
            results["monthly"].setdefault(str(m), {})[str(f)] = evaluate(frame, f"m{m}", names)
        results.setdefault("operational", {})[str(f)] = {
            p: operational(frame, "veg", p) for p in OPERATIONAL_PREDICTORS if p in frame}
        o = results["operational"][str(f)]["meanSWE"]
        print(f"   operational meanSWE: skill {o['all']['skill_corrected']:.2f} (1971-), "
              f"{o['recent']['skill_corrected'] if o['recent'] else float('nan'):.2f} (1996-)", flush=True)
    q_trend = {"vegetation_season_full": trend(targets.veg),
               "vegetation_season_1991": trend(targets.veg, 1991),
               "vegetation_season_1951": trend(targets.veg, 1951),
               "centre_of_volume_full": trend(targets.centre_of_volume_dowy),
               "centre_of_volume_1991": trend(targets.centre_of_volume_dowy, 1991)}
    snow, peak_series, timing_series = snow_trends(wide, band_wide, int(targets.index.max()))
    out = FORCING / code
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gauge": {"code": code, "name": gauge.NAME_ENG, "river": gauge.RIVER, "basin": gauge.BASIN,
                  "lon": float(gauge.LON), "lat": float(gauge.LAT), "area_km2": cells["basin_area_km2"]},
        "discharge": {"source": "CA-discharge 2023 (10-day, monthly mean of three decades)"
                      + (" + Uzhydromet monthly workbook after 2016" if agreement else ""),
                      "overlap_agreement": agreement,
                      "vegetation_season_years": [int(targets.veg.dropna().index.min()), int(targets.veg.dropna().index.max())],
                      "vegetation_season_mean_m3s": float(targets.veg.mean())},
        "forcing": {"source": "ERA5-Land DAILY_AGGR, 0.1 degree, fractional basin overlap",
                    "cells": len(cells["cells"]), "band_width_m": BAND_WIDTH, "band_area_share": band_area},
        "method": {"issue_months": list(ISSUE_MONTHS), "max_predictors": MAX_PREDICTORS,
                   "selection": "best subset by adjusted R2", "bootstrap": 1000,
                   "cross_validation": "leave-one-year-out with selection inside each fold",
                   "split_year": SPLIT_YEAR,
                   "operational": f"expanding-window refit from {HINDCAST_START}, level shifted by the mean error of the previous {CORRECTION_YEARS} years, scored against the previous 30-year mean",
                   "reference": "Design after Barnhart et al. (USGS/HMRI), Kashkadarya; predictors here from ERA5-Land, not SnowModel."},
        "forecasts": results,
        "trends": {"discharge": q_trend, "snow_and_climate": snow},
        "series": {"vegetation_season_m3s": {str(k): (None if not np.isfinite(v) else float(v)) for k, v in targets.veg.items()},
                   "centre_of_volume_dowy": {str(k): int(v) for k, v in targets.centre_of_volume_dowy.dropna().items()},
                   "peak_swe_basin_mm": peak_series.get("basin", {}),
                   "peak_swe_timing_basin_dowy": timing_series},
    }
    (out / "study.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    table.reset_index().join(targets, on="water_year").to_csv(out / "predictors-and-targets.csv", index=False)
    print(json.dumps({k: v for k, v in q_trend.items()}, indent=1))
    print({k: (v["peak_swe"], v["peak_timing"]) for k, v in snow.items() if k == "basin"})
    print("DJF T", snow["djf_temperature"], "DJF P", snow["djf_precipitation"])


if __name__ == "__main__":
    main()
