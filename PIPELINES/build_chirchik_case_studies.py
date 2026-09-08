"""Build reproducible Chirchik case studies from held observations (no network).

Optional station-cell product data are supplied by extract_case_study_forcing.py.
The build never treats basin means as station samples or runoff depth as discharge.
"""
from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import json
import math
import random
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "PUBLISHED/data/hydroclimate"
OUT = ROOT / "PUBLISHED/data/case-studies"
NAMES = {"uz:station/meteo-419704": "Pskem", "uz:station/meteo-422709": "Oygaing",
         "uz:station/meteo-413694": "Tashkent", "uz:station/gauge-16290": "Pskem–Mullala"}
VARIABLES = {"precipitation_total": "mm", "air_temperature_mean": "°C"}
VERSION = "1.0.0"


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temp.replace(path)


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def period(row):
    return date(int(row["year"]), int(row["month"]), 1).strftime("%Y-%m")


def finite(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Non-finite observation: {value}")
    return number


def unique(rows, keys):
    seen = set()
    for row in rows:
        key = tuple(row[k] for k in keys)
        if key in seen:
            raise ValueError(f"Duplicate observation key: {key}")
        seen.add(key)


def scores(observed, predicted):
    """KGE 2009, population SD ratio; bias sign is prediction minus observation.

    Undefined ratios/correlations remain null, including zero-variance predictions.
    """
    if len(observed) != len(predicted):
        raise ValueError("Paired score arrays differ in length")
    n = len(observed)
    if not n:
        return {"n": 0, **dict.fromkeys(["bias", "mae", "rmse", "pbias", "r", "nse", "kge", "alpha", "beta"])}
    o, p = mean(observed), mean(predicted)
    errors = [b - a for a, b in zip(observed, predicted)]
    vo = sum((x - o) ** 2 for x in observed)
    vp = sum((x - p) ** 2 for x in predicted)
    r = sum((a - o) * (b - p) for a, b in zip(observed, predicted)) / math.sqrt(vo * vp) if vo and vp else None
    alpha = math.sqrt(vp / vo) if vo else None
    beta = p / o if o else None
    kge = 1 - math.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2) if all(x is not None for x in [r, alpha, beta]) else None
    return {"n": n, "bias": mean(errors), "mae": mean(abs(x) for x in errors),
            "rmse": math.sqrt(mean(x * x for x in errors)), "pbias": 100 * mean(errors) / o if o else None,
            "r": r, "nse": 1 - sum(x * x for x in errors) / vo if vo else None,
            "kge": kge, "alpha": alpha, "beta": beta}


def discharge_months(daily, suspect, coverage=0.9):
    unique(daily, ["station_id", "year", "month", "day"])
    grouped = defaultdict(list)
    for row in daily:
        y, m, d = (int(row[k]) for k in ["year", "month", "day"])
        date(y, m, d)  # Reject impossible calendar days, including leap-day errors.
        q = finite(row["discharge_cms"])
        if q < 0:
            raise ValueError("Negative discharge requires source review")
        grouped[(row["station_id"], y, m)].append((d, q, row))
    result = []
    for (station, y, m), values in sorted(grouped.items()):
        days = calendar.monthrange(y, m)[1]
        clean = [q for d, q, _ in values if (station, y, m, d) not in suspect]
        raw = [q for _, q, _ in values]
        eligible = len(clean) / days >= coverage
        result.append({"station_id": station, "year": y, "month": m, "period": f"{y}-{m:02d}",
                       "raw_mean": mean(raw), "screened_mean": mean(clean) if clean else None,
                       "days_observed": len(raw), "days_valid": len(clean), "days_expected": days,
                       "coverage": len(clean) / days, "suspect_days": len(raw) - len(clean),
                       "eligible": eligible, "observed_volume_mcm": sum(clean) * 86400 / 1e6 if len(clean) == days else None,
                       "source_files": sorted({r["source_file"] for _, _, r in values})})
    return result


def calendar_audit(daily):
    """Quarantine impossible dates, retaining the source record for review."""
    accepted, rejected = [], []
    for row in daily:
        try:
            date(int(row["year"]), int(row["month"]), int(row["day"]))
        except ValueError:
            rejected.append({**row, "reason": "invalid_calendar_date"})
        else:
            accepted.append(row)
    return accepted, rejected


def benchmark(monthly, train_end=2010, test_end=2017, field="screened_mean"):
    train = defaultdict(list)
    for row in monthly:
        if row["eligible"] and 2001 <= row["year"] <= train_end:
            train[row["month"]].append(row[field])
    climatology = {m: mean(v) for m, v in train.items()}
    test = [{**r, "predicted": climatology[r["month"]]} for r in monthly
            if r["eligible"] and train_end < r["year"] <= test_end and r["month"] in climatology]
    return {"training": f"2001–{train_end}", "evaluation": f"{train_end + 1}–{test_end}",
            "climatology": [{"month": m, "value": v, "training_months": len(train[m])} for m, v in sorted(climatology.items())],
            "scores": scores([r[field] for r in test], [r["predicted"] for r in test]), "pairs": test}


def block_intervals(pairs, repeats=500):
    groups = defaultdict(list)
    for row in pairs:
        groups[row["year"]].append(row)
    years = sorted(groups)
    if len(years) < 5:
        return None
    rng = random.Random(1729)
    samples = defaultdict(list)
    for _ in range(repeats):
        sample = [r for y in rng.choices(years, k=len(years)) for r in groups[y]]
        result = scores([r["screened_mean"] for r in sample], [r["predicted"] for r in sample])
        for key in ["rmse", "mae", "bias", "nse", "kge"]:
            if result[key] is not None:
                samples[key].append(result[key])
    return {"method": "95% percentile intervals; resample held-out calendar years with replacement; fixed fitted benchmark",
            "repeats": repeats, "seed": 1729, "independent_years": len(years),
            "intervals": {k: [sorted(v)[int(0.025 * (len(v) - 1))], sorted(v)[int(0.975 * (len(v) - 1))]] for k, v in samples.items()}}


def station_inventory(rows, links):
    grouped = defaultdict(list)
    for row in rows:
        if row["variable"] in VARIABLES:
            finite(row["value"])
            if row["variable"] == "precipitation_total" and float(row["value"]) < 0:
                raise ValueError("Negative precipitation requires source review")
            grouped[(row["station_id"], row["variable"])].append(row)
    inventory, series, annual, seasonal = [], [], [], []
    for (station, variable), values in sorted(grouped.items()):
        by_period = {period(r): finite(r["value"]) for r in values}
        start, end = min(by_period), max(by_period)
        months = [f"{y}-{m:02}" for y in range(int(start[:4]), int(end[:4]) + 1) for m in range(1, 13)
                  if start <= f"{y}-{m:02}" <= end]
        link = next(r for r in links if r["station_id"] == station)
        inventory.append({"station_id": station, "station": NAMES[station], "variable": variable,
                          "unit": VARIABLES[variable], "start": start, "end": end, "months": len(values),
                          "missing": [m for m in months if m not in by_period], "expected_months": len(months),
                          "basin_id": link["hybas_id"], "latitude": float(link["latitude"]), "longitude": float(link["longitude"]),
                          "source_files": sorted({r["source_file"] for r in values})})
        series.extend({"station_id": station, "station": NAMES[station], "variable": variable, "unit": VARIABLES[variable],
                       "period": m, "value": by_period.get(m)} for m in months)
        for y in range(int(start[:4]), int(end[:4]) + 1):
            v = [by_period.get(f"{y}-{m:02}") for m in range(1, 13)]
            complete = all(x is not None for x in v)
            value = (sum(v) if variable == "precipitation_total" else
                     sum(x * calendar.monthrange(y, m)[1] for m, x in enumerate(v, 1)) / (366 if calendar.isleap(y) else 365)) if complete else None
            annual.append({"station": NAMES[station], "station_id": station, "variable": variable, "year": y,
                           "months": sum(x is not None for x in v), "value": value, "unit": VARIABLES[variable]})
        for m in range(1, 13):
            v = [x for p, x in by_period.items() if int(p[-2:]) == m]
            seasonal.append({"station_id": station, "variable": variable, "month": m, "mean": mean(v), "n": len(v)})
    return inventory, series, annual, seasonal


def upstream_candidate(routing, outlet):
    rows = {r["hybas_id"]: r for r in routing}
    if outlet not in rows:
        raise ValueError("Gauge outlet basin absent from routing")
    reverse = defaultdict(list)
    for row in routing:
        reverse[row["next_down"]].append(row["hybas_id"])
    seen, stack = set(), [outlet]
    while stack:
        basin = stack.pop()
        if basin in seen:
            raise ValueError("Cycle or repeated basin in upstream routing")
        seen.add(basin)
        stack.extend(reverse[basin])
    return seen


def product_validation(path, observations):
    if not path.exists():
        return {"status": "awaiting_historical_station_cell_extraction", "comparisons": [], "pairs": []}
    products = read_csv(path)
    unique(products, ["station_id", "period", "variable", "product"])
    obs = {(r["station_id"], period(r), r["variable"]): finite(r["value"]) for r in observations if r["variable"] in VARIABLES}
    grouped, pairs = defaultdict(list), []
    for row in products:
        if row["spatial_support"] != "station_grid_cell":
            raise ValueError("Validation requires station grid-cell samples")
        variable = row["variable"]
        if row["unit"] != VARIABLES.get(variable):
            raise ValueError("Product units must be normalised before comparison")
        key = (row["station_id"], row["period"], variable)
        if key not in obs or row["value"] == "":
            continue
        pair = {**row, "observed": obs[key], "predicted": finite(row["value"])}
        pairs.append(pair)
        grouped[(row["station_id"], variable, row["product"])].append(pair)
    comparisons = []
    for (station, variable, product), group in sorted(grouped.items()):
        subsets = {"all": group}
        for label, months in {"DJF": [12, 1, 2], "MAM": [3, 4, 5], "JJA": [6, 7, 8], "SON": [9, 10, 11]}.items():
            subsets[label] = [r for r in group if int(r["period"][-2:]) in months]
        for season, subset in subsets.items():
            metric = scores([r["observed"] for r in subset], [r["predicted"] for r in subset])
            if variable == "air_temperature_mean":
                metric.update(pbias=None, beta=None, kge=None)  # Celsius ratios depend on arbitrary zero.
            comparisons.append({"station_id": station, "station": NAMES[station], "variable": variable,
                                "product": product, "season": season, "unit": VARIABLES[variable], "scores": metric})
    return {"status": "raw_product_comparisons" if pairs else "no_matching_observations", "comparisons": comparisons, "pairs": pairs,
            "independence": "Station contribution to gridded products not yet verified. Raw comparisons involve no fitted correction."}


def build(data=DATA, output=OUT, forcing=None):
    output.mkdir(parents=True, exist_ok=True)
    portfolio_path = ROOT / "CASE_STUDIES/chirchik-portfolio.json"
    portfolio = json.loads(portfolio_path.read_text(encoding="utf-8"))
    inputs = [data / n for n in ["pskem-station-monthly.csv", "pskem-discharge-daily.csv", "pskem-station-basin-links.csv",
                                "pskem-observations.manifest.json", "basin-routing-level12.csv", "basins-level12.geojson"]]
    station, daily, links = [read_csv(p) for p in inputs[:3]]
    unique(station, ["station_id", "year", "month", "variable"])
    manifest = json.loads(inputs[3].read_text(encoding="utf-8"))
    gauge = "uz:station/gauge-16290"
    suspect = {(gauge, r["year"], r["month"], r["day"]) for r in manifest["suspectDailyValues"]}
    valid_daily, rejected_daily = calendar_audit(daily)
    monthly = discharge_months(valid_daily, suspect)
    base = benchmark(monthly)
    base["uncertainty"] = block_intervals(base["pairs"])
    base["raw_sensitivity_scores"] = benchmark(monthly, field="raw_mean")["scores"]
    base["sensitivity_note"] = "Raw and screened benchmark scores use the same eligible months and valid calendar dates; only manifest-flagged daily values are excluded in the screened means."
    predicted = {r["period"]: r["predicted"] for r in base.pop("pairs")}
    for row in monthly:
        row["benchmark"] = predicted.get(row["period"])
    inventory, series, annual, seasonal = station_inventory(station, links)
    flow_annual = []
    for y in sorted({r["year"] for r in monthly}):
        rows = [r for r in monthly if r["year"] == y]
        full = len(rows) == 12 and all(r["observed_volume_mcm"] is not None for r in rows)
        flow_annual.append({"year": y, "valid_days": sum(r["days_valid"] for r in rows), "complete": full,
                            "volume_mcm": sum(r["observed_volume_mcm"] for r in rows) if full else None})
    flow_seasonal = []
    for m in range(1, 13):
        values = [r["screened_mean"] for r in monthly if r["month"] == m and r["eligible"]]
        flow_seasonal.append({"month": m, "mean": mean(values), "n": len(values)})
    gauge_link = next(r for r in links if r["station_id"] == gauge)
    ids = upstream_candidate(read_csv(inputs[4]), gauge_link["hybas_id"])
    features = [f for f in json.loads(inputs[5].read_text(encoding="utf-8"))["features"] if str(f["properties"]["HYBAS_ID"]) in ids]
    if len(features) != len(ids):
        raise ValueError("Traced basin geometry is missing")
    catchment = {"status": "candidate_requires_gauge_to_reach_review", "outlet_basin_id": gauge_link["hybas_id"],
                 "gauge_latitude": float(gauge_link["latitude"]), "gauge_longitude": float(gauge_link["longitude"]),
                 "basin_count": len(ids), "area_km2": sum(float(f["properties"]["SUB_AREA"]) for f in features),
                 "basin_ids": sorted(ids), "station_ids_inside_candidate": [r["station_id"] for r in links if r["hybas_id"] in ids],
                 "method": "Reverse NEXT_DOWN trace, including the entire gauge-containing level-12 unit; SUB_AREA summed once per unit.",
                 "limitation": "Whole outlet unit included. Gauge coordinate and reach snapping need review; this is not the full Chirchik basin or an exact gauge delineation."}
    for f in features:
        props = f["properties"]
        f["properties"] = {k: props[k] for k in ["HYBAS_ID", "NEXT_DOWN", "SUB_AREA"]}
    write_json(output / "pskem-candidate-catchment.geojson", {"type": "FeatureCollection", "features": features})
    forcing = forcing or output / "station-product-monthly.csv"
    validation = product_validation(forcing, station)
    for study, variable in [(portfolio["studies"][0], "precipitation_total"), (portfolio["studies"][1], "air_temperature_mean")]:
        if any(r["variable"] == variable and r["scores"]["n"] for r in validation["comparisons"]):
            study["status"] = "Raw product comparisons computed; correction experiments pending"
    if forcing.exists():
        inputs.append(forcing)
    inputs.extend([portfolio_path, Path(__file__).resolve()])
    provenance = [{"path": p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else p.name,
                   "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size} for p in inputs]
    overlap = []
    pskem = {(r["variable"], r["period"]): r["value"] for r in series if r["station"] == "Pskem"}
    for row in monthly:
        p, t = (pskem.get((v, row["period"])) for v in VARIABLES)
        if row["eligible"] and p is not None and t is not None:
            overlap.append({"period": row["period"], "precipitation_mm": p, "temperature_c": t, "discharge_cms": row["screened_mean"]})
    summary = {"station_count": 3, "daily_discharge_rows": len(daily), "suspect_daily_rows": len(suspect),
               "invalid_calendar_rows": len(rejected_daily),
               "discharge_start": monthly[0]["period"], "discharge_end": monthly[-1]["period"],
               "eligible_discharge_months": sum(r["eligible"] for r in monthly), "total_discharge_months": len(monthly),
               "incomplete_discharge_months": sum(r["days_observed"] < r["days_expected"] for r in monthly),
               "joint_months": len(overlap), "joint_start": overlap[0]["period"] if overlap else None,
               "joint_end": overlap[-1]["period"] if overlap else None,
               "peak_climatology_month": max(flow_seasonal, key=lambda r: r["mean"])["month"],
               "existing_pilot_excludes_stations": all(r["in_headwater_formation"] == "0" for r in links)}
    result = {"version": VERSION, "generated_at": datetime.now(timezone.utc).isoformat(), **portfolio,
              "summary": summary, "inventory": inventory, "station_series": series, "station_annual": annual,
              "station_climatology": seasonal, "discharge_monthly": monthly, "discharge_annual": flow_annual,
              "discharge_climatology": flow_seasonal, "benchmark": base, "catchment": catchment,
              "joint_series": overlap, "validation": validation, "provenance": provenance,
              "quality_policy": {"monthly_min_daily_coverage": 0.9, "volume_requires_complete_days": True,
                                 "rejected_daily_rows": rejected_daily,
                                 "suspect_daily_values": manifest["suspectDailyValues"], "missing_values": "Never filled or treated as zero by this analysis",
                                 "source_note": "Station importer reconciles precipitation dashes against annual totals; source rows remain unchanged."}}
    write_json(output / "chirchik.json", result)
    write_json(output / "chirchik.manifest.json", {k: result[k] for k in ["version", "generated_at", "provenance", "quality_policy"]})
    write_csv(output / "discharge-audit.csv", monthly, list(monthly[0]))
    write_csv(output / "discharge-rejected-dates.csv", rejected_daily, [*daily[0], "reason"])
    write_csv(output / "station-annual.csv", annual, list(annual[0]))
    write_csv(output / "joint-climate-discharge.csv", overlap, ["period", "precipitation_mm", "temperature_c", "discharge_cms"])
    write_report(output / "chirchik-report.md", result)
    print(json.dumps({"output": str(output), "summary": summary, "benchmark": base["scores"], "product_validation": validation["status"]}, indent=2))
    return result


def write_report(path, data):
    s, b = data["summary"], data["benchmark"]
    lines = [f"# {data['title']}", "", data["scope"], "", "## Results from the held data", "",
             f"Built with analysis version {VERSION}. Input hashes are in chirchik.manifest.json.", "",
             "| Station | Variable | Period | Months | Missing |", "| --- | --- | --- | ---: | --- |"]
    for r in data["inventory"]:
        lines.append(f"| {r['station']} | {r['variable']} | {r['start']}–{r['end']} | {r['months']} | {', '.join(r['missing']) or 'None'} |")
    lines += ["", f"Discharge: {s['daily_discharge_rows']:,} daily values, {s['discharge_start']}–{s['discharge_end']}; "
              f"{s['suspect_daily_rows']} source-flagged values and {s['invalid_calendar_rows']} invalid calendar record(s) quarantined. {s['eligible_discharge_months']} of {s['total_discharge_months']} months meet 90% screened daily coverage. "
              f"{s['incomplete_discharge_months']} raw months have missing days. Observed volume is reported only for complete screened months.", "",
              f"There are {s['joint_months']} eligible paired precipitation/temperature/discharge months ({s['joint_start']}–{s['joint_end']}). "
              "Temporal alignment is not a test of causality. Annual and seasonal volumes must not be obtained by summing monthly means.", "",
              f"The observed discharge climatology peaks in {calendar.month_name[s['peak_climatology_month']]}. "
              "This is a descriptive full-record statistic; the forecast benchmark below uses only its training period.", "",
              "### Held-out seasonal discharge benchmark", "",
              f"Monthly climatology trained on {b['training']}; evaluated on {b['evaluation']}. "
              "No meteorological or satellite predictors are fitted in this first benchmark.", "",
              "| Score | Value |", "| --- | ---: |"]
    for key in ["n", "mae", "rmse", "bias", "pbias", "nse", "kge", "r", "alpha", "beta"]:
        value = b["scores"][key]
        lines.append(f"| {key} | {value:.4f} |" if value is not None else f"| {key} | Undefined |")
    lines += ["", "MAE/RMSE/bias are in m³/s; percent bias uses prediction minus observation. NSE and KGE have different benchmark interpretations; "
              "KGE zero is not a universal failure threshold. [Knoben et al. (2019)](https://hess.copernicus.org/articles/23/4323/2019/).", "",
              "Whole-year bootstrap intervals and raw-versus-screened sensitivity scores are supplied in chirchik.json. "
              "Intervals condition on the fitted baseline and resample only seven held-out years; they do not capture rating-curve uncertainty.", "",
              "Invalid-date source rows are preserved in discharge-rejected-dates.csv. The delivered daily table contains a 2015-02-29 entry, although 2015 was not a leap year. "
              "The case-study analysis excludes this impossible date before recomputing both raw and screened monthly means; it does not modify the source delivery.", "",
              "### Spatial and validation status", "",
              f"The candidate Pskem trace has {data['catchment']['basin_count']} level-12 units and {data['catchment']['area_km2']:.1f} km² of summed SUB_AREA. "
              + data["catchment"]["limitation"], "",
              "All four station links are outside the existing broad headwater pilot. The Pskem candidate must be reviewed before basin-forcing extraction. "
              "Neither its area nor the brief's approximate full-basin area should be reported as a surveyed gauge area.", "",
              f"Station-product validation status: `{data['validation']['status']}`. "
              "No score is fabricated for an absent or non-overlapping product. Historical cell extraction is separate from the existing basin-mean series.", ""]
    if data["validation"]["comparisons"]:
        lines += ["| Station | Product | Variable | Season | Pairs | RMSE | Bias |", "| --- | --- | --- | --- | ---: | ---: | ---: |"]
        for r in data["validation"]["comparisons"]:
            m = r["scores"]
            if m["n"]:
                lines.append(f"| {r['station']} | {r['product']} | {r['variable']} | {r['season']} | {m['n']} | {m['rmse']:.3f} | {m['bias']:.3f} |")
        lines.append("")
    for i, study in enumerate(data["studies"], 1):
        lines += [f"## {i}. {study['title']}", "", f"**Status:** {study['status']}", "", study["question"], "",
                  f"**Hypothesis:** {study['hypothesis']}", "", f"**Observations:** {study['observations']}", "", "### Protocol", ""]
        lines.extend(f"{j}. {step}" for j, step in enumerate(study["method"], 1))
        for label, key in [("Evaluation", "metrics"), ("Deliverables", "deliverables"), ("Evidence needed before stronger claims", "gates")]:
            lines += ["", f"### {label}", "", *[f"- {v}" for v in study[key]]]
        lines += ["", f"**Decision supported:** {study['decision']}", "", "Sources: " + ", ".join(
            f"[{r['title']}]({r['url']})" for r in data["sources"] if r["id"] in study["sources"]), ""]
    lines += ["## Reproduction and next execution steps", "", "```bash", "npm run cases:build", "npm run test:cases",
              "# For historical gridded precipitation and temperature, after local EE authentication:",
              "npm run cases:forcing", "npm run cases:build", "npm run build", "```", "",
              "1. Review source discharge flags and gauge/reach placement; confirm station elevations and product independence.",
              "2. Run historical station-cell extraction; compare raw products before fitting corrections.",
              "3. Delineate the approved gauge catchment, backfill snow and catchment forcing, then test seasonal forecasts on disjoint years.",
              "4. Expand to Chatkal/Ugam and reservoir storage when their control sections and independent validation data are available.", "",
              "Every output is associated with source hashes, processing version, time support and existing station/basin identifiers. "
              "Study statuses describe the analyses actually run; the remaining protocols are research work, not claimed completed validation."]
    lines += ["", "## Exportable observation figure", "", "![Pskem observations and held-out seasonal-flow benchmark](pskem-observation-evidence.png)", "",
              "[Download vector PDF](pskem-observation-evidence.pdf). Rebuild with `npm run cases:figures` after updating analysis results."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--forcing", type=Path)
    args = parser.parse_args()
    build(args.data, args.output, args.forcing)
