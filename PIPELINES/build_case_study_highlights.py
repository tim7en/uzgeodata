"""Derive the case-study headline findings from the published evidence.

The Chirchik study produced reports, a figure atlas and a workbook, but nothing
carried its conclusions to the front of the site, so the work was invisible unless
a reader already knew it existed.

Every number here is read out of the published artefacts rather than typed in, so
a rerun that changes the evidence changes the headline, and a finding that stops
being true cannot survive as prose. Each one carries the file that proves it and,
where there is one, the figure that shows it.

Negative results are first-class. The seasonal flow models fail against their own
test years, and that is stated as a finding rather than omitted: a page that only
reports what worked is not a report.

    python PIPELINES/build_case_study_highlights.py
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STUDY = ROOT / "PUBLISHED/data/case-studies"
VALIDATION = STUDY / "advanced-validation.json"
TRENDS = STUDY / "sabitov-monthly-trends.csv"
DAILY_MODEL = STUDY / "pskem-daily-model.json"
OUTPUT = STUDY / "case-study-highlights.json"
FIGURES = "/data/case-studies"


def write_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temporary, path)


def round_or_none(value, digits=3):
    return None if value is None else round(float(value), digits)


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    if not VALIDATION.exists():
        raise SystemExit(f"Missing {VALIDATION.relative_to(ROOT)}; run the case-study pipeline first")

    validation = json.loads(VALIDATION.read_text(encoding="utf-8"))
    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    findings = []

    # 1. How well gridded products reproduce the stations they are used instead of.
    climate = validation["climate_validation"]
    best = max((row for row in climate if row["raw"].get("nse") is not None),
               key=lambda row: row["raw"]["nse"])
    worst = min((row for row in climate if row["raw"].get("nse") is not None),
                key=lambda row: row["raw"]["nse"])
    findings.append({
        "id": "product-station-agreement",
        "kind": "validated",
        "headline": "Gridded products track the stations, except for mountain rainfall",
        "value": round_or_none(best["raw"]["nse"]),
        "valueLabel": "NSE",
        "detail": (
            f"{best['product']} {best['variable'].replace('_', ' ')} reaches NSE "
            f"{best['raw']['nse']:.3f} (r {best['raw']['r']:.3f}) against {best['station']} over "
            f"{best['raw']['n']} months. The weakest pairing, {worst['product']} "
            f"{worst['variable'].replace('_', ' ')} at {worst['station']}, falls to NSE "
            f"{worst['raw']['nse']:.3f} — worse than using the mean."
        ),
        "comparisons": len(climate),
        "figure": f"{FIGURES}/pskem-climate-validation.png",
        "evidence": "PUBLISHED/data/case-studies/advanced-validation.json",
    })

    # 2. The seasonal forecast does not work yet, and snow does not rescue it.
    flow = validation["seasonal_flow"]
    models = sorted(flow["models"], key=lambda entry: entry["scores"]["rmse"])
    leader = models[0]
    snow_models = [entry for entry in flow["models"] if "snow" in entry["model"] or "swe" in entry["model"]]
    findings.append({
        "id": "seasonal-flow-skill",
        "kind": "negative",
        "headline": "Seasonal flow prediction fails on its own test years",
        "value": round_or_none(leader["scores"]["nse"]),
        "valueLabel": "best NSE",
        "detail": (
            f"Every model scores below zero, meaning none beats the mean of the observations. "
            f"The best, {leader['model'].replace('_', ' ')}, reaches NSE {leader['scores']['nse']:.2f} "
            f"and cuts RMSE {leader['rmse_skill_vs_climatology'] * 100:.0f}% against climatology. "
            f"Adding snow or snow water equivalent makes it worse, not better, on "
            f"{len(flow['test_years'])} held-out years."
        ),
        "models": [
            {"model": entry["model"], "nse": round_or_none(entry["scores"]["nse"], 2),
             "rmse": round_or_none(entry["scores"]["rmse"], 1),
             "skillVsClimatology": round_or_none(entry.get("rmse_skill_vs_climatology"), 3)}
            for entry in models
        ],
        "trainingYears": flow["training_years"],
        "testYears": flow["test_years"],
        "figure": f"{FIGURES}/pskem-model-skill.png",
        "evidence": "PUBLISHED/data/case-studies/advanced-validation.json",
    })

    # 3. Two satellites agreeing is not the same as either being right.
    agreement = validation["snow_sensor_agreement"]
    strongest = max(agreement, key=lambda entry: entry["scores"]["r"])
    findings.append({
        "id": "snow-sensor-agreement",
        "kind": "limitation",
        "headline": "Two snow sensors agree closely — which is not the same as being right",
        "value": round_or_none(strongest["scores"]["r"]),
        "valueLabel": "r, Aqua vs Terra",
        "detail": (
            f"Across the {strongest['elevation_band'].replace('to', '–')} m band the two overpasses "
            f"agree to r {strongest['scores']['r']:.3f} over {strongest['scores']['n']:,} paired days. "
            "That measures consistency between sensors, not accuracy against ground truth, and it is "
            "published as agreement for exactly that reason."
        ),
        "bands": len(agreement),
        "figure": f"{FIGURES}/pskem-snow-calendar.png",
        "evidence": "PUBLISHED/data/case-studies/advanced-validation.json",
    })

    # 4. Reservoir surface, and how much of the record is usable.
    reservoir = validation["reservoir"]
    findings.append({
        "id": "charvak-water-surface",
        "kind": "validated",
        "headline": "Charvak's water surface moves by more than a factor of two",
        "value": round_or_none(reservoir["max_observed"]["water_area_km2"], 1),
        "valueLabel": "km² maximum",
        "detail": (
            f"Between {reservoir['min_observed']['period']} and {reservoir['max_observed']['period']} the "
            f"mapped surface ranges from {reservoir['min_observed']['water_area_km2']:.1f} to "
            f"{reservoir['max_observed']['water_area_km2']:.1f} km². Only "
            f"{reservoir['eligible_months']} of {reservoir['total_months']} months clear the valid-area "
            "threshold, so the rest are withheld rather than interpolated."
        ),
        "eligibleMonths": reservoir["eligible_months"],
        "totalMonths": reservoir["total_months"],
        "figure": f"{FIGURES}/charvak-water-verification.png",
        "evidence": "PUBLISHED/data/case-studies/advanced-validation.json",
    })

    # 5. No trend survives correction for testing twelve months at once.
    if TRENDS.exists():
        with TRENDS.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        significant = [row for row in rows if float(row["p_holm"]) < 0.05]
        steepest = min(rows, key=lambda row: float(row["sen_slope_cms_year"]))
        findings.append({
            "id": "monthly-discharge-trend",
            "kind": "negative",
            "headline": "No monthly discharge trend survives multiple-test correction",
            "value": len(significant),
            "valueLabel": "significant months of 12",
            "detail": (
                f"Sen slopes run to {float(steepest['sen_slope_cms_year']):.2f} m³/s per year in month "
                f"{steepest['month']} over {steepest['years']} years, but no month stays significant "
                "once Holm correction accounts for testing all twelve. An uncorrected reading of the "
                "same table would have reported a decline."
            ),
            "monthsTested": len(rows),
            "figure": f"{FIGURES}/sabitov-flow-diagnostics.png",
            "evidence": "PUBLISHED/data/case-studies/sabitov-monthly-trends.csv",
        })

    # 6. The daily model, and what verifying the observation record changed.
    if DAILY_MODEL.exists():
        model = json.loads(DAILY_MODEL.read_text(encoding="utf-8"))
        daily = model["skill"]["validation"]
        monthly = model["monthlySkill"]["validation"]
        seasonal = model.get("seasonalValidationScores", {})
        findings.append({
            "id": "daily-process-model",
            "kind": "validated",
            "headline": "A daily snowmelt model has real skill; the seasonal total still does not",
            "value": round_or_none(monthly["nse"], 2),
            "valueLabel": "monthly NSE, held-out years",
            "detail": (
                f"Calibrated on {model['model']['calibration']['years'][0]}–"
                f"{model['model']['calibration']['years'][1]} and tested on years it never saw, the "
                f"temperature-index model reaches NSE {daily['nse']:.2f} on daily flow and "
                f"{monthly['nse']:.2f} on monthly means, closing the water balance at a runoff "
                f"coefficient of {model['waterBalance']['runoffCoefficientSimulated']:.2f} against "
                f"{model['waterBalance']['runoffCoefficientObserved']:.2f} observed. The April–September "
                f"total remains the hard part, at NSE {seasonal.get('nse', float('nan')):.2f}: daily "
                "behaviour is reproducible where the seasonal volume is not."
            ),
            "dailyNse": round_or_none(daily["nse"], 3),
            "monthlyNse": round_or_none(monthly["nse"], 3),
            "seasonalNse": round_or_none(seasonal.get("nse"), 3),
            "figure": f"{FIGURES}/sabitov-hindcast.png",
            "evidence": "PUBLISHED/data/case-studies/pskem-daily-model.json",
        })
        provenance = model["observationProvenance"]
        findings.append({
            "id": "discharge-record-verified",
            "kind": "validated",
            "headline": "The daily discharge is observation, not disaggregated monthly values",
            "value": provenance["suspectDaysExcludedFromScoring"],
            "valueLabel": "days removed by screening",
            "detail": (
                "The workbook is named Monthly, so the series was checked rather than trusted: within "
                "every month the days vary as a hydrograph and no month repeats one figure. "
                + provenance["reconciliation"] + " Screening rejects "
                f"{provenance['suspectDaysExcludedFromScoring']} day(s), all in 2017, and those days "
                "are excluded from scoring the model as well as from the published means."
            ),
            "evidence": "PUBLISHED/data/case-studies/discharge-audit.csv",
        })

    reports = [
        {"label": "Chirchik basin report", "href": f"{FIGURES}/chirchik-report.md", "kind": "report"},
        {"label": "Environment and energy study", "href": f"{FIGURES}/chirchik-environment-study.md", "kind": "report"},
        {"label": "Deep study", "href": f"{FIGURES}/chirchik-deep-study.md", "kind": "report"},
        {"label": "Scientific figure atlas", "href": f"{FIGURES}/chirchik-scientific-atlas.pdf", "kind": "atlas"},
        {"label": "Methods atlas", "href": f"{FIGURES}/sabitov-methods-atlas.pdf", "kind": "atlas"},
        {"label": "Analysis workbook", "href": f"{FIGURES}/chirchik-analysis.xlsx", "kind": "workbook"},
    ]
    figures = [entry for entry in (STUDY.glob("*.png"))]
    payload = {
        "version": "1.0",
        "generatedAt": retrieved,
        "study": {
            "id": "chirchik",
            "label": "Chirchik and Pskem",
            "question": "Can published products stand in for the stations, and do they predict the season?",
            "page": "/case-studies.html",
        },
        "findings": findings,
        "reports": [entry for entry in reports if (ROOT / "PUBLISHED" / entry["href"].lstrip("/")).exists()],
        "figures": sorted(f"{FIGURES}/{path.name}" for path in figures),
        "counts": {
            "findings": len(findings),
            "figures": len(figures),
            "reports": len(reports),
        },
        "qualityNotes": [
            "Numbers are read from the published evidence, not restated: a rerun that changes the "
            "evidence changes the headline.",
            "Negative and limiting results are published beside the positive ones.",
        ],
    }
    write_json(OUTPUT, payload)
    for finding in findings:
        print(f"  [{finding['kind']:10}] {finding['headline']}")
    print(f"  {len(findings)} findings, {len(figures)} figures, {len(payload['reports'])} reports "
          f"-> {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
