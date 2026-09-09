"""Publish the case study as plain tables anyone can open in R, pandas or a spreadsheet.

The study already published forty-two CSVs, but they were written for the
pipeline rather than for a reader: one carried the literal string `nan`, which
turns a numeric column into a character vector on import with no warning, and
most carried full float64 precision, which makes a table unreadable without
telling anyone anything a measurement supports. Everything else worth
downloading was nested JSON, which is not a table at all.

So this writes a small bundle of flat, tidy tables under `tidy/`:

  * one row per observation, no nesting, no repeated header blocks
  * snake_case columns, ISO dates, SI-ish units named in the column
  * missing values are empty, never `nan`, `None` or `-9999`
  * numbers rounded to what the measurement supports
  * a data dictionary describing every column of every table

Long format is used for the scores, because a reader comparing two evaluation
splits wants to filter rows, not hunt through differently named columns.

    python PIPELINES/build_tidy_downloads.py
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hydromet.io import atomic_write

ROOT = Path(__file__).resolve().parent.parent
STUDY = ROOT / "PUBLISHED/data/case-studies"
TIDY = STUDY / "tidy"
MANIFEST = STUDY / "tidy-downloads.manifest.json"

# What each table's numbers can actually support. Runoff in mm/day is reported
# to 0.001; a percentage or a score to 0.001; a volume in million m3 to 0.1.
DECIMALS = {"mm": 3, "mcm": 1, "score": 4, "percent": 3, "celsius": 2, "default": 3}


def clean(value, digits=DECIMALS["default"]):
    """One CSV cell: empty when absent, rounded when numeric, verbatim otherwise."""
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int,)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        rounded = round(value, digits)
        # Keep integers looking like integers: 12.0 reads as 12 in every tool.
        return int(rounded) if rounded == int(rounded) and abs(rounded) < 1e15 else rounded
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null", "na"} else text


def write(name: str, columns: list[str], rows: list[dict], digits=None) -> Path:
    digits = digits or {}
    path = TIDY / name

    def emit(handle):
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        for row in rows:
            writer.writerow([clean(row.get(column), digits.get(column, DECIMALS["default"]))
                             for column in columns])

    atomic_write(path, emit)
    return path


def load(name: str):
    return json.loads((STUDY / name).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ dictionary

# Column meanings are written once, here, and checked against the tables that
# are actually emitted, so a column can never ship without a description.
DICTIONARY = {
    "pskem_daily.csv": {
        "date": ("date", "ISO date, YYYY-MM-DD"),
        "observed_mm": ("mm/day", "Observed runoff depth over the catchment; empty where the gauge record has no accepted value"),
        "simulated_mm": ("mm/day", "Runoff simulated by the calibrated temperature-index model"),
        "snow_water_equivalent_mm": ("mm", "Modelled catchment snow storage as water equivalent"),
        "temperature_c": ("degrees C", "Catchment mean daily air temperature from reanalysis forcing"),
        "precipitation_mm": ("mm/day", "Catchment mean daily precipitation from reanalysis forcing"),
        "period": ("category", "calibration, validation or unused, for the published stratified split"),
    },
    "pskem_monthly.csv": {
        "month": ("date", "First day of the month, YYYY-MM-DD"),
        "split": ("category", "calibration, validation or unused"),
        "evaluation": ("category", "stratified (published reference) or chronological (stricter re-test)"),
        "observed_mm_day": ("mm/day", "Mean observed runoff over the paired days of the month"),
        "simulated_mm_day": ("mm/day", "Mean simulated runoff over the same days"),
        "benchmark_mm_day": ("mm/day", "Calibration-only monthly climatology; chronological evaluation only"),
        "valid_days": ("count", "Days with both an observation and a simulation"),
        "expected_days": ("count", "Calendar days in the month"),
    },
    "pskem_seasonal.csv": {
        "water_year": ("year", "Year of the April-September season"),
        "evaluation": ("category", "stratified or chronological"),
        "split": ("category", "calibration or validation"),
        "observed_mcm": ("million m3", "Observed April-September volume over the paired days"),
        "simulated_mcm": ("million m3", "Simulated volume over the same days"),
        "benchmark_mcm": ("million m3", "Calibration-only climatology; chronological evaluation only"),
        "valid_days": ("count", "Days contributing to the volume"),
        "expected_days": ("count", "Calendar days in April-September"),
    },
    "model_scores.csv": {
        "evaluation": ("category", "stratified or chronological"),
        "source": ("category", "model or benchmark climatology"),
        "target": ("category", "daily, monthly or seasonal"),
        "metric": ("category", "nse, kge, pbias, rmse_mm, r, alpha, beta, log_nse or n"),
        "value": ("number", "The score; units follow the metric, pbias in percent"),
    },
    "study_inputs.csv": {
        "path": ("text", "Repository path of the input"),
        "role": ("text", "How the study uses it"),
        "bytes": ("count", "File size when the package was built"),
        "sha256": ("text", "Content hash at that moment"),
        "available": ("boolean", "Whether the file was present"),
        "changed_since_recorded": ("boolean", "TRUE if the file no longer matches the hash recorded when the study was built"),
    },
    "method_stages.csv": {
        "step": ("count", "Order in which the stages run"),
        "stage": ("text", "Stage identifier"),
        "title": ("text", "What the stage does"),
        "command": ("text", "The command that runs it"),
        "produces": ("text", "Artefacts written, separated by a semicolon"),
    },
    "tests.csv": {
        "suite": ("text", "Test file"),
        "command": ("text", "How to run that suite"),
        "test": ("text", "Test function name"),
        "asserts": ("text", "What the test checks, from its docstring"),
    },
    "transferability.csv": {
        "domain": ("text", "Catchment or region"),
        "period": ("text", "Years covered, or 'any' where nothing has been attempted"),
        "status": ("category", "exercised or not attempted"),
        "detail": ("text", "Evidence where exercised; what would be required where not"),
    },
}


def dictionary_rows(emitted: dict[str, list[str]]) -> list[dict]:
    rows = []
    for name, columns in emitted.items():
        described = DICTIONARY.get(name)
        if described is None:
            raise SystemExit(f"{name} has no entry in the data dictionary.")
        for column in columns:
            if column not in described:
                raise SystemExit(f"{name} column '{column}' is undescribed.")
            unit, description = described[column]
            rows.append({"file": name, "column": column, "unit": unit, "description": description})
    return rows


README = """# Chirchik / Pskem case study - tidy tables

Flat CSV, one row per observation. Missing values are empty, not `nan`. Numbers
are rounded to what the measurement supports. Column meanings, including units,
are in `data_dictionary.csv`.

R:

    daily <- read.csv("pskem_daily.csv")
    scores <- read.csv("model_scores.csv")
    subset(scores, evaluation == "chronological" & metric == "nse")

Python:

    import pandas as pd
    daily = pd.read_csv("pskem_daily.csv", parse_dates=["date"])

The two evaluations are different experiments on the same model structure and
are not directly comparable: `stratified` places wet and dry years on both sides
of the split, `chronological` scores only years that follow every calibration
year. Filter on `evaluation` before comparing anything.

Provenance, input hashes and the commands that produce these tables are in
`../reproducibility-package.json`.
"""


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    TIDY.mkdir(parents=True, exist_ok=True)
    reference = load("current-model.json")
    review = load("model-review.json")
    package = load("reproducibility-package.json")
    emitted: dict[str, list[str]] = {}
    written: list[Path] = []

    # 1. The daily series, copied through the same cleaning as everything else.
    with (STUDY / "pskem-daily-model.csv").open(encoding="utf-8-sig", newline="") as handle:
        daily = list(csv.DictReader(handle))
    columns = ["date", "observed_mm", "simulated_mm", "snow_water_equivalent_mm",
               "temperature_c", "precipitation_mm", "period"]
    digits = {"observed_mm": 3, "simulated_mm": 3, "snow_water_equivalent_mm": 2,
              "temperature_c": 2, "precipitation_mm": 3}
    rows = [{key: (float(value) if key not in {"date", "period"} and value not in ("", "nan") else value)
             for key, value in row.items()} for row in daily]
    written.append(write("pskem_daily.csv", columns, rows, digits))
    emitted["pskem_daily.csv"] = columns

    # 2 and 3. Monthly and seasonal, both evaluations stacked with a label, so a
    # reader filters rather than joining two differently shaped files.
    monthly_columns = ["month", "split", "evaluation", "observed_mm_day", "simulated_mm_day",
                       "benchmark_mm_day", "valid_days", "expected_days"]
    monthly: list[dict] = []
    for label, document in (("stratified", reference), ("chronological", review)):
        for row in document["monthly_rows"]:
            monthly.append({
                "month": f"{row['period']}-01", "split": row["split"], "evaluation": label,
                "observed_mm_day": row.get("observed"), "simulated_mm_day": row.get("simulated"),
                "benchmark_mm_day": row.get("benchmark"),
                "valid_days": row.get("valid_days"), "expected_days": row.get("expected_days"),
            })
    written.append(write("pskem_monthly.csv", monthly_columns, monthly,
                         {"observed_mm_day": 3, "simulated_mm_day": 3, "benchmark_mm_day": 3}))
    emitted["pskem_monthly.csv"] = monthly_columns

    seasonal_columns = ["water_year", "evaluation", "split", "observed_mcm", "simulated_mcm",
                        "benchmark_mcm", "valid_days", "expected_days"]
    seasonal: list[dict] = []
    calibration = set(reference.get("calibration_years", []))
    for label, document in (("stratified", reference), ("chronological", review)):
        for row in document["seasonal_rows"]:
            year = row["year"]
            if label == "stratified":
                split = "calibration" if year in calibration else "validation"
            else:
                split = "calibration" if year in set(review["train_years"]) else "validation"
            seasonal.append({
                "water_year": year, "evaluation": label, "split": split,
                "observed_mcm": row.get("observedMcm"), "simulated_mcm": row.get("simulatedMcm"),
                "benchmark_mcm": row.get("benchmark"),
                "valid_days": row.get("valid_days"), "expected_days": row.get("expected_days"),
            })
    written.append(write("pskem_seasonal.csv", seasonal_columns, seasonal,
                         {"observed_mcm": 1, "simulated_mcm": 1, "benchmark_mcm": 1}))
    emitted["pskem_seasonal.csv"] = seasonal_columns

    # 4. Scores in long format: one row per number, filterable.
    score_columns = ["evaluation", "source", "target", "metric", "value"]
    renamed = {"logNse": "log_nse", "rmseMm": "rmse_mm"}
    scores: list[dict] = []
    for target in ("daily", "monthly", "seasonal"):
        for source, block in (("model", review["candidate"].get(target)),
                              ("benchmark", review["benchmark"].get(target))):
            for metric, value in (block or {}).items():
                scores.append({"evaluation": "chronological", "source": source, "target": target,
                               "metric": renamed.get(metric, metric), "value": value})
    for target, block in (("daily", reference.get("daily")), ("monthly", reference.get("monthly")),
                          ("seasonal", reference.get("seasonal"))):
        for metric, value in (block or {}).items():
            scores.append({"evaluation": "stratified", "source": "model", "target": target,
                           "metric": renamed.get(metric, metric), "value": value})
    written.append(write("model_scores.csv", score_columns, scores, {"value": DECIMALS["score"]}))
    emitted["model_scores.csv"] = score_columns

    # 5-8. The reproducibility package, flattened into tables.
    input_columns = ["path", "role", "bytes", "sha256", "available", "changed_since_recorded"]
    inputs = [{"path": row["path"], "role": row["role"], "bytes": row.get("bytes"),
               "sha256": row.get("sha256"), "available": row["available"],
               "changed_since_recorded": bool(row.get("changedSinceRecorded"))}
              for row in package["data"]["files"]]
    written.append(write("study_inputs.csv", input_columns, inputs))
    emitted["study_inputs.csv"] = input_columns

    stage_columns = ["step", "stage", "title", "command", "produces"]
    stages = [{"step": index + 1, "stage": stage["id"], "title": stage["title"],
               "command": stage["command"],
               "produces": "; ".join(output["path"] for output in stage["produces"])}
              for index, stage in enumerate(package["method"])]
    written.append(write("method_stages.csv", stage_columns, stages))
    emitted["method_stages.csv"] = stage_columns

    test_columns = ["suite", "command", "test", "asserts"]
    tests = [{"suite": suite["path"], "command": suite["command"],
              "test": case["name"], "asserts": case.get("asserts")}
             for suite in package["tests"] for case in suite["cases"]]
    written.append(write("tests.csv", test_columns, tests))
    emitted["tests.csv"] = test_columns

    transfer_columns = ["domain", "period", "status", "detail"]
    transfer = [{"domain": row["domain"], "period": row["period"], "status": row["status"],
                 "detail": row.get("note") or row.get("requirement")}
                for row in (package["transferability"]["tested"]
                            + package["transferability"]["untested"])]
    written.append(write("transferability.csv", transfer_columns, transfer))
    emitted["transferability.csv"] = transfer_columns

    # 9. The dictionary, which fails the build if any column is undescribed.
    dictionary_columns = ["file", "column", "unit", "description"]
    written.append(write("data_dictionary.csv", dictionary_columns, dictionary_rows(emitted)))

    (TIDY / "README.md").write_text(README, encoding="utf-8")
    written.append(TIDY / "README.md")

    payload = {
        "version": "1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "convention": {
            "missingValue": "empty field",
            "dateFormat": "ISO 8601, YYYY-MM-DD",
            "lineTerminator": "LF",
            "encoding": "UTF-8 without BOM",
            "columnNaming": "snake_case with the unit in the name",
        },
        "tables": [{"file": path.name, "bytes": path.stat().st_size,
                    "rows": max(0, path.read_text(encoding="utf-8").count("\n") - 1)}
                   for path in written if path.suffix == ".csv"],
    }
    atomic_write(MANIFEST, lambda handle: handle.write(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"))

    total = sum(path.stat().st_size for path in written)
    for table in payload["tables"]:
        print(f"  {table['file']:26} {table['rows']:>6} rows  {table['bytes']/1000:>7.1f} kB")
    print(f"  {len(payload['tables'])} tables + README, {total/1000:.0f} kB total "
          f"-> {TIDY.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
