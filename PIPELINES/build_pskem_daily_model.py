"""A daily snowmelt-and-soil model for the Pskem, calibrated and validated out of sample.

The seasonal experiment tried to predict a whole season from one March snapshot
across ten annual points, six of them for training. That is too little to learn
from and too little to judge on. The daily record is not: 6,210 complete days of
discharge from 2001 to 2017 against daily temperature, precipitation and potential
evaporation.

The structure is a conventional temperature-index model of the HBV family, chosen
because it is the standard for snow-dominated catchments with no ground snow
network, and because every parameter means something a hydrologist can argue with:

    snowfall     P * sfcf                       when T <= tt
    melt         cfmax * (T - tt)               limited by the pack
    recharge     (soil / fc) ** beta            of rain plus melt
    evaporation  PET scaled by soil wetness
    discharge    a fast store and a slow store, each emptying at its own rate

`sfcf` is a snowfall correction: gauge and gridded precipitation both undercatch
snow in mountains, and refusing to carry the term does not make the bias go away.
The water balance is reported so the correction cannot hide a broken mass budget.

Calibration uses the first ten years and validation the last seven. The validation
period is drier than the calibration period, which is stated rather than avoided:
it is the harder direction and the one the seasonal model failed in.

    python PIPELINES/build_pskem_daily_model.py
    python PIPELINES/build_pskem_daily_model.py --samples 40000
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import date, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
FORCING = ROOT / "PUBLISHED/data/case-studies/sabitov-daily-forcing.csv"
DISCHARGE = ROOT / "PUBLISHED/data/hydroclimate/pskem-discharge-daily.csv"
CATCHMENT = ROOT / "PUBLISHED/data/case-studies/pskem-candidate-catchment.geojson"
AUDIT = ROOT / "PUBLISHED/data/case-studies/discharge-audit.csv"
HYPSOMETRY = ROOT / "PUBLISHED/data/case-studies/elevation-profiles.csv"
OUT_DIR = ROOT / "PUBLISHED/data/case-studies"
SERIES = OUT_DIR / "pskem-daily-model.csv"
SUMMARY = OUT_DIR / "pskem-daily-model.json"
MANIFEST = OUT_DIR / "pskem-daily-model.manifest.json"
CALIBRATION = (2001, 2010)
VALIDATION = (2011, 2017)
# Physically admissible ranges, not fitted preferences.
BOUNDS = {
    "tt": (-1.5, 2.5),        # rain/snow threshold, degrees C
    "cfmax": (1.0, 7.0),      # degree-day factor, mm per degree per day
    "sfcf": (0.8, 1.8),       # snowfall correction for undercatch
    "fc": (50.0, 600.0),      # soil moisture capacity, mm
    "beta": (1.0, 5.0),       # runoff nonlinearity
    "perc": (0.1, 4.0),       # percolation to the slow store, mm/day
    "k_fast": (0.05, 0.6),    # fast recession, per day
    "k_slow": (0.001, 0.15),  # slow recession, per day
    # Bracketed on the environmental lapse rate (about -6.5) rather than left free.
    # Unconstrained, calibration drove it past the dry adiabatic limit to absorb
    # errors elsewhere, which buys no skill and stops being physics.
    "lapse": (-8.0, -5.0),    # temperature lapse, degrees C per 1000 m
}
ORDER = list(BOUNDS)


def write_json(path: Path, payload: object) -> None:
    # Undefined scores (e.g. unobserved warm-up days) are JSON null, never NaN.
    from build_study_landing import safe_json
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(safe_json(payload), handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    os.replace(temporary, path)


def dropouts(flow: dict[str, float], ratio: float = 0.5) -> list[dict]:
    """Days that fall far below their own neighbourhood.

    The published audit only catches near-zero readings, so it flags three days
    in 2017 and misses others: 2016-07-01 and 02 both read exactly 16.5 m3/s
    against a surrounding week near 156, in peak melt. A repeated value far below
    its neighbours is a recording dropout, not a river. The test is symmetric and
    local, so a genuine recession is not caught by it — a river falling steadily
    stays close to its own week.
    """
    ordered = sorted(flow)
    found = []
    for index in range(3, len(ordered) - 3):
        window = [flow[ordered[offset]] for offset in range(index - 3, index + 4) if offset != index]
        window.sort()
        reference = window[len(window) // 2]
        value = flow[ordered[index]]
        if reference > 0 and value < reference * ratio:
            found.append({"date": ordered[index], "value": round(value, 3),
                          "neighbourMedian": round(reference, 3),
                          "ratio": round(value / reference, 3)})
    return found


def load_bands():
    """Elevation bands with their area share, from the published hypsometry.

    A basin-mean temperature cannot melt a catchment that spans 875 to 4375 m:
    the low bands should be releasing water in April while the average is still
    below the snow threshold. Each band therefore gets its own temperature, and
    the model sums their contributions by area.
    """
    if not HYPSOMETRY.exists():
        return None
    rows = []
    with HYPSOMETRY.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append({
                "mid": (float(row["minimum_m"]) + float(row["maximum_m"])) / 2,
                "area": float(row["area_km2"]),
                "temperature": float(row["temperature_c"]),
            })
    total = sum(row["area"] for row in rows)
    elevation = np.array([row["mid"] for row in rows])
    fraction = np.array([row["area"] for row in rows]) / total
    mean_elevation = float((elevation * fraction).sum())
    # The gradient the published band temperatures themselves imply, kept for the
    # record beside the calibrated one.
    centred = elevation - elevation.mean()
    observed = np.array([row["temperature"] for row in rows])
    measured = float((centred * (observed - observed.mean())).sum() / (centred ** 2).sum() * 1000)
    return {"elevation": elevation, "fraction": fraction, "meanElevation": mean_elevation,
            "measuredLapsePer1000m": round(measured, 3), "count": len(rows)}


def suspect_days(flow: dict[str, float]) -> tuple[set[str], list[dict]]:
    """Identify the days the published screening removes, by reproducing its result.

    The audit records how many days a month lost and the mean that remained, but
    not which day. Searching for the day whose removal reproduces the screened
    mean identifies it and verifies the reading at the same time: if no day
    reproduces it, the assumption is wrong and the month is reported rather than
    guessed at.
    """
    if not AUDIT.exists():
        return set(), []
    by_month: dict[tuple[int, int], list[str]] = {}
    for day in flow:
        by_month.setdefault((int(day[:4]), int(day[5:7])), []).append(day)

    removed: set[str] = set()
    report: list[dict] = []
    with AUDIT.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            count = int(row["suspect_days"])
            if not count:
                continue
            key = (int(row["year"]), int(row["month"]))
            days = sorted(by_month.get(key, []))
            target = float(row["screened_mean"])
            found = None
            if count == 1:
                for candidate in days:
                    kept = [flow[day] for day in days if day != candidate]
                    if kept and abs(sum(kept) / len(kept) - target) < 1e-6:
                        found = candidate
                        break
            entry = {"period": row["period"], "suspectDays": count,
                     "rawMean": round(float(row["raw_mean"]), 3),
                     "screenedMean": round(target, 3),
                     "identified": found,
                     "value": None if found is None else flow[found]}
            if found:
                removed.add(found)
            report.append(entry)
    return removed, report


def load_inputs():
    forcing = {}
    with FORCING.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            forcing[row["date"]] = (
                float(row["temperature_c"]), float(row["precipitation_mm"]), float(row["potential_et_mm"]),
            )
    flow = {}
    with DISCHARGE.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if not row["discharge_cms"]:
                continue
            key = f"{int(row['year']):04d}-{int(row['month']):02d}-{int(row['day']):02d}"
            flow[key] = float(row["discharge_cms"])

    area = sum(feature["properties"]["SUB_AREA"]
               for feature in json.loads(CATCHMENT.read_text(encoding="utf-8"))["features"])
    days = sorted(forcing)
    scored = set(flow)
    if not (scored & set(days)):
        raise SystemExit("Forcing and discharge do not overlap")
    removed, screening = suspect_days(flow)
    detected = dropouts(flow)
    # The published screening is kept and extended, never overridden: its days stay
    # removed, and days it missed are added with the reason recorded.
    extra = [entry for entry in detected if entry["date"] not in removed]
    removed = removed | {entry["date"] for entry in detected}
    temperature = np.array([forcing[day][0] for day in days])
    precipitation = np.array([forcing[day][1] for day in days])
    pet = np.array([forcing[day][2] for day in days])
    # One cubic metre per second for a day, spread over the catchment, in mm.
    factor = 86400.0 / (area * 1e6) * 1000.0
    observed = np.array([flow.get(day, np.nan) * factor for day in days])
    # Scoring starts only once the snow and soil stores have had a year to fill:
    # the first simulated year begins empty, and judging it would blame the model
    # for a cold start. A day the published screening rejects is excluded too.
    warmup = min(scored)[:4]
    valid = np.array([day in scored and day not in removed and day[:4] != warmup
                      for day in days])
    return (days, temperature, precipitation, pet, observed, area, factor, valid,
            screening, extra, min(scored)[:4])


def simulate(parameters: np.ndarray, temperature, precipitation, pet, bands=None):
    """Run every candidate parameter set at once; the time loop is the slow axis.

    With bands, the snow routine runs per elevation band and their melt and rain
    are combined by area share before the soil store sees them.
    """
    tt, cfmax, sfcf, fc, beta, perc, k_fast, k_slow, lapse = (
        parameters[:, index] for index in range(len(ORDER)))
    count = parameters.shape[0]
    if bands is None:
        offsets = np.zeros((count, 1))
        weights = np.ones((1, 1))
    else:
        # degrees C offset of each band from the forcing's reference elevation
        drop = (bands["elevation"] - bands["meanElevation"]) / 1000.0
        offsets = lapse[:, None] * drop[None, :]
        weights = bands["fraction"][None, :]
    swe = np.zeros((count, offsets.shape[1]))
    soil = fc * 0.3
    fast = np.zeros(count)
    slow = np.zeros(count)
    discharge = np.empty((len(temperature), count))
    snow_store = np.empty((len(temperature), count))

    for step in range(len(temperature)):
        air = temperature[step] + offsets
        threshold = tt[:, None]
        rain = np.where(air > threshold, precipitation[step], 0.0)
        snowfall = np.where(air <= threshold, precipitation[step] * sfcf[:, None], 0.0)
        swe += snowfall
        melt = np.minimum(swe, np.maximum(cfmax[:, None] * (air - threshold), 0.0))
        swe -= melt

        liquid = ((rain + melt) * weights).sum(axis=1)
        wetness = np.clip(soil / fc, 0.0, 1.0)
        recharge = liquid * wetness ** beta
        soil += liquid - recharge
        evaporation = np.minimum(pet[step] * np.clip(soil / (0.7 * fc), 0.0, 1.0), soil)
        soil -= evaporation
        overflow = np.maximum(soil - fc, 0.0)
        soil -= overflow

        fast += recharge + overflow
        percolation = np.minimum(perc, fast)
        fast -= percolation
        slow += percolation
        flow_fast = k_fast * fast
        flow_slow = k_slow * slow
        fast -= flow_fast
        slow -= flow_slow
        discharge[step] = flow_fast + flow_slow
        snow_store[step] = (swe * weights).sum(axis=1)
    return discharge, snow_store


def kling_gupta(simulated, observed):
    """KGE keeps correlation, variability and bias visible instead of merging them."""
    mask = np.isfinite(simulated) & np.isfinite(observed)
    simulated, observed = simulated[mask], observed[mask]
    if simulated.size < 2 or simulated.std() == 0:
        return -np.inf, {}
    correlation = float(np.corrcoef(simulated, observed)[0, 1])
    alpha = float(simulated.std() / observed.std())
    beta = float(simulated.mean() / observed.mean())
    score = 1 - float(np.sqrt((correlation - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2))
    return score, {"r": correlation, "alpha": alpha, "beta": beta}


def scores(simulated, observed):
    kge, parts = kling_gupta(simulated, observed)
    residual = simulated - observed
    nse = 1 - float(np.sum(residual ** 2) / np.sum((observed - observed.mean()) ** 2))
    positive = (simulated > 0) & (observed > 0)
    log_nse = 1 - float(
        np.sum((np.log(simulated[positive]) - np.log(observed[positive])) ** 2)
        / np.sum((np.log(observed[positive]) - np.log(observed[positive]).mean()) ** 2)
    ) if positive.sum() > 2 else None
    return {
        "n": int(observed.size),
        "nse": round(nse, 4),
        "kge": round(kge, 4),
        "logNse": None if log_nse is None else round(log_nse, 4),
        "pbias": round(float(residual.sum() / observed.sum() * 100), 3),
        "rmseMm": round(float(np.sqrt(np.mean(residual ** 2))), 4),
        **{key: round(value, 4) for key, value in parts.items()},
    }


def sample(count: int, rng, centre=None, spread=0.15):
    lows = np.array([BOUNDS[key][0] for key in ORDER])
    highs = np.array([BOUNDS[key][1] for key in ORDER])
    if centre is None:
        return rng.uniform(lows, highs, size=(count, len(ORDER)))
    width = (highs - lows) * spread
    return np.clip(rng.normal(centre, width, size=(count, len(ORDER))), lows, highs)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=20000)
    parser.add_argument("--lumped", action="store_true", help="ignore the bands, for comparison")
    parser.add_argument("--split", choices=("chronological", "stratified"), default="chronological")
    parser.add_argument("--seed", type=int, default=1729)
    args = parser.parse_args()

    (days, temperature, precipitation, pet, observed, area, factor, valid,
     screening, extra, warmup_year) = load_inputs()
    years = np.array([int(day[:4]) for day in days])
    if args.split == "stratified":
        # A chronological cut trained on wet years and tested on dry ones, which
        # guarantees a high bias. Ranking years by yield and alternating puts wet
        # and dry years on both sides while keeping validation strictly unseen.
        totals = {int(year): float(observed[years == year].sum()) for year in set(years.tolist())}
        ranked = sorted(totals, key=totals.get)
        calibration_years = set(ranked[::2])
    else:
        calibration_years = {year for year in set(years.tolist())
                             if CALIBRATION[0] <= year <= CALIBRATION[1]}
    in_calibration = np.isin(years, list(calibration_years))
    calibration = in_calibration & valid
    validation = ~in_calibration & valid
    print(f"  split {args.split}: calibration {sorted(calibration_years)}")
    print(f"  screening removes {int((~valid).sum())} suspect day(s) from scoring")
    print(f"Pskem daily model | {len(days):,} days {days[0]}..{days[-1]} | catchment {area:,.0f} km2")
    print(f"  calibration {CALIBRATION[0]}-{CALIBRATION[1]} ({calibration.sum():,} days) | "
          f"validation {VALIDATION[0]}-{VALIDATION[1]} ({validation.sum():,} days)")

    bands = None if args.lumped else load_bands()
    if bands:
        print(f"  {bands['count']} elevation bands, mean {bands['meanElevation']:.0f} m, "
              f"published gradient {bands['measuredLapsePer1000m']:+.2f} degC/1000 m")
    else:
        print("  lumped: one basin-mean temperature")

    rng = np.random.default_rng(args.seed)
    best = None
    # Broad search, then narrowing rounds around the leader. Refinement matters:
    # the first round only locates the basin of attraction.
    plan = [(args.samples, None, 0.0)] + [(args.samples // 2, "refine", spread)
                                          for spread in (0.20, 0.10, 0.05, 0.02)]
    for round_index, (count, centre, spread) in enumerate(plan):
        candidates = sample(count, rng) if centre is None else sample(count, rng, best["parameters"], spread)
        simulated, _ = simulate(candidates, temperature, precipitation, pet, bands)
        for index in range(candidates.shape[0]):
            score, _ = kling_gupta(simulated[calibration, index], observed[calibration])
            if best is None or score > best["kge"]:
                best = {"kge": score, "parameters": candidates[index].copy()}
        print(f"  search round {round_index + 1}: best calibration KGE {best['kge']:.4f}")

    # A parameter resting on its bound means the model wants something the range
    # forbids, which is information about the forcing rather than a nuisance.
    pinned = [key for key, value in zip(ORDER, best["parameters"])
              if abs(value - BOUNDS[key][0]) < 1e-6 or abs(value - BOUNDS[key][1]) < 1e-6]
    if pinned:
        print(f"  parameters resting on a bound: {', '.join(pinned)}")

    parameters = best["parameters"].reshape(1, -1)
    simulated, snow = simulate(parameters, temperature, precipitation, pet, bands)
    simulated = simulated[:, 0]
    snow = snow[:, 0]

    result = {
        "calibration": scores(simulated[calibration], observed[calibration]),
        "validation": scores(simulated[validation], observed[validation]),
        "wholeRecord": scores(simulated, observed),
    }
    # A model that reproduces the hydrograph while losing the mass budget is not a
    # model, so the balance is reported next to the skill.
    # The balance is taken over the scored days only: forcing runs a year longer
    # than the gauge, and mixing the two would compare different periods.
    balance = {
        "precipitationMm": round(float(precipitation[valid].sum()), 1),
        "observedRunoffMm": round(float(observed[valid].sum()), 1),
        "simulatedRunoffMm": round(float(simulated[valid].sum()), 1),
        "runoffCoefficientObserved": round(float(observed[valid].sum() / precipitation[valid].sum()), 3),
        "runoffCoefficientSimulated": round(float(simulated[valid].sum() / precipitation[valid].sum()), 3),
        "peakSnowWaterEquivalentMm": round(float(snow.max()), 1),
        "scoredDays": int(valid.sum()),
    }

    # The published product is a monthly mean, so the model is also judged there:
    # daily skill can flatter a model that only gets the seasonal shape right.
    monthly_keys = sorted({(int(day[:4]), int(day[5:7])) for day in days})
    monthly_observed, monthly_simulated, monthly_period = [], [], []
    for key in monthly_keys:
        mask = np.array([int(day[:4]) == key[0] and int(day[5:7]) == key[1] for day in days]) & valid
        if mask.sum() < 20:
            continue
        monthly_observed.append(float(observed[mask].mean()))
        monthly_simulated.append(float(simulated[mask].mean()))
        monthly_period.append("calibration" if key[0] in calibration_years else "validation")
    monthly_observed = np.array(monthly_observed)
    monthly_simulated = np.array(monthly_simulated)
    monthly_period = np.array(monthly_period)
    monthly_scores = {
        "calibration": scores(monthly_simulated[monthly_period == "calibration"],
                              monthly_observed[monthly_period == "calibration"]),
        "validation": scores(monthly_simulated[monthly_period == "validation"],
                             monthly_observed[monthly_period == "validation"]),
    }

    # Seasonal volumes, so this can be compared with the annual regression directly.
    seasonal = []
    months = np.array([int(day[5:7]) for day in days])
    season = (months >= 4) & (months <= 9)
    for year in sorted(set(years.tolist())):
        mask = season & (years == year) & valid
        if mask.sum() < 150:
            continue
        to_mcm = area * 1e6 / 1000 / 1e6
        seasonal.append({
            "year": int(year),
            "observedMcm": round(float(observed[mask].sum() * to_mcm), 1),
            "simulatedMcm": round(float(simulated[mask].sum() * to_mcm), 1),
            "period": "calibration" if year in calibration_years else "validation",
        })
    seasonal_validation = [row for row in seasonal if row["period"] == "validation"]
    if seasonal_validation:
        sim = np.array([row["simulatedMcm"] for row in seasonal_validation])
        obs = np.array([row["observedMcm"] for row in seasonal_validation])
        seasonal_scores = scores(sim, obs)
    else:
        seasonal_scores = {}

    with SERIES.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "observed_mm", "simulated_mm", "snow_water_equivalent_mm",
                         "temperature_c", "precipitation_mm", "period"])
        for index, day in enumerate(days):
            writer.writerow([
                day, round(float(observed[index]), 4), round(float(simulated[index]), 4),
                round(float(snow[index]), 2), temperature[index], precipitation[index],
                "calibration" if calibration[index] else ("validation" if validation[index] else "unused"),
            ])

    payload = {
        "version": "1.0",
        "generatedAt": __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            .replace(microsecond=0).isoformat(),
        "model": {
            "family": "temperature-index snow with soil store and two linear reservoirs (HBV type)",
            "timestep": "day",
            "parameters": {key: round(float(value), 4) for key, value in zip(ORDER, best["parameters"])},
            "parameterBounds": BOUNDS,
            "calibration": {"years": sorted(calibration_years), "split": args.split, "objective": "KGE",
                            "search": "seeded random search then local refinement",
                            "samples": args.samples, "seed": args.seed},
        },
        "elevationBands": None if not bands else {
            "count": bands["count"],
            "meanElevationM": round(bands["meanElevation"], 1),
            "publishedGradientPer1000m": bands["measuredLapsePer1000m"],
            "calibratedLapsePer1000m": round(float(best["parameters"][ORDER.index("lapse")]), 3),
            "source": "PUBLISHED/data/case-studies/elevation-profiles.csv",
        },
        "warmUp": {"yearExcluded": warmup_year,
                   "reason": "stores start empty; the first simulated year is a cold start"},
        "catchment": {
            "areaKm2": round(area, 1),
            "gauge": "uz:station/gauge-16290",
            "caveat": ("The catchment is a candidate delineation: the gauge has not been snapped to a "
                       "reach and reviewed, so the area used to convert discharge to millimetres "
                       "carries that uncertainty."),
        },
        "skill": result,
        "monthlySkill": monthly_scores,
        "observationProvenance": {
            "sourceWorkbook": "Discharge_Pskem_Muallala_Monthly.xlsx",
            "note": ("The workbook is named Monthly but stores daily values: within every month the "
                     "days vary as a hydrograph, and no month repeats a single figure. The daily "
                     "series is the observation; the monthly table is derived from it."),
            "reconciliation": ("203 of 204 published monthly raw means reproduce exactly from these "
                               "daily values, the remaining one within rounding."),
            "screening": screening,
            "additionalDropoutsDetected": extra,
            "dropoutRule": ("a day below half the median of the surrounding six days; the published "
                            "audit catches only near-zero readings and misses partial dropouts"),
            # Two different exclusions, kept apart: days rejected for quality, and
            # days outside the scored window at all (warm-up, or no gauge record).
            "suspectDaysExcludedFromScoring": len(
                {entry["identified"] for entry in screening if entry["identified"]}
                | {entry["date"] for entry in extra}),
            "daysOutsideScoredWindow": int((~valid).sum()),
        },
        "parametersAtBounds": pinned,
        "seasonalVolumes": seasonal,
        "seasonalValidationScores": seasonal_scores,
        "waterBalance": balance,
        "qualityNotes": [
            "Calibration and validation periods are separate years; no validation day informs a parameter.",
            "The validation period is drier than the calibration period, which is the harder direction.",
            "Precipitation is gridded, not gauged; the snowfall correction factor absorbs undercatch and "
            "is reported rather than hidden.",
            "Discharge is a historical record ending in 2017; this is a hindcast, not an operational forecast.",
        ],
    }
    write_json(SUMMARY, payload)
    write_json(MANIFEST, {
        "version": "1.0",
        "generatedAt": payload["generatedAt"],
        "inputs": [str(path.relative_to(ROOT)).replace("\\", "/") for path in (FORCING, DISCHARGE, CATCHMENT)],
        "outputs": [str(path.relative_to(ROOT)).replace("\\", "/") for path in (SERIES, SUMMARY)],
        "observationClass": "model_hindcast",
    })

    print(f"  parameters: " + ", ".join(f"{key} {value:.3f}" for key, value in zip(ORDER, best["parameters"])))
    for label in ("calibration", "validation"):
        entry = result[label]
        print(f"  daily    {label:12} NSE {entry['nse']:+.3f}  KGE {entry['kge']:+.3f}  "
              f"logNSE {entry['logNse']}  bias {entry['pbias']:+.1f}%")
    for label in ("calibration", "validation"):
        entry = monthly_scores[label]
        print(f"  monthly  {label:12} NSE {entry['nse']:+.3f}  KGE {entry['kge']:+.3f}  "
              f"bias {entry['pbias']:+.1f}%  (n {entry['n']})")
    if seasonal_scores:
        print(f"  seasonal Apr-Sep volume, validation years: NSE {seasonal_scores['nse']:+.3f}  "
              f"bias {seasonal_scores['pbias']:+.1f}%")
    print(f"  runoff coefficient observed {balance['runoffCoefficientObserved']} "
          f"simulated {balance['runoffCoefficientSimulated']}")
    print(f"  -> {SUMMARY.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
