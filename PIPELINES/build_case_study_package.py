"""Assemble the Chirchik/Pskem case study into a self-contained research package.

The evidence for this study was already complete but scattered: nineteen
manifests carry input hashes, script hashes, Earth Engine asset ids and
retrieval timestamps, and none of it reached the page. A reader could see the
results and download the tables, but could not answer the four questions that
decide whether a study is usable by someone else:

    reproducibility  can I obtain the same input data?
    verification     can I run the same procedure?
    validation       do I obtain approximately the same result?
    transferability  does the method still work elsewhere, or in another period?

So this builds one document, `reproducibility-package.json`, laid out as
Data -> Method -> Results -> Tests -> Transferability -> Download.

Nothing here is prose about the repository. Every stage names an npm script that
must exist, every artefact must be on disk and is hashed as it is read, every
published number is pulled live from the file that holds it, and every test is
read out of the test file rather than described. A stage that cannot be
substantiated raises instead of being written, because a reproducibility record
that drifts from the repository is worse than none: it invites a reader to trust
a procedure that no longer exists.

    python PIPELINES/build_case_study_package.py
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STUDY = ROOT / "PUBLISHED/data/case-studies"
OUTPUT = STUDY / "reproducibility-package.json"
REPRODUCTION = STUDY / "reproduction-check.json"
PACKAGE_JSON = ROOT / "package.json"

# How close a re-run must land before the published number is called reproduced.
# Deterministic stages (a re-read of a stored series) get a tight tolerance; a
# calibrated fit is only expected to land in the same place to two decimals.
RECOMPUTATION_TOLERANCE = 0.005


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dig(document, pointer: str):
    """Read a value by dotted path, so a result can name where it came from."""
    value = document
    for key in pointer.split("."):
        if isinstance(value, list):
            value = value[int(key)]
        else:
            value = value[key]
    return value


# --------------------------------------------------------------------- method

# The order below is the order a reader would have to run. Each stage names the
# npm script that runs it and the artefacts it leaves behind; both are checked.
STAGES = [
    {
        "id": "observations",
        "title": "Read and screen the station and gauge record",
        "npm": "stations:pskem",
        "purpose": "Parse the Uzhydromet workbooks, transliterate names, screen "
                   "impossible calendar dates and flag suspect daily discharge.",
        "produces": [
            "PUBLISHED/data/hydroclimate/pskem-station-monthly.csv",
            "PUBLISHED/data/hydroclimate/pskem-discharge-daily.csv",
            "PUBLISHED/data/hydroclimate/pskem-observations.manifest.json",
        ],
    },
    {
        "id": "forcing",
        "title": "Extract daily catchment forcing",
        "npm": "cases:sabitov:inputs",
        "purpose": "Reduce reanalysis temperature and precipitation over the "
                   "candidate catchment and its elevation bands.",
        "produces": [
            "PUBLISHED/data/case-studies/sabitov-daily-forcing.csv",
            "PUBLISHED/data/case-studies/sabitov-inputs.manifest.json",
        ],
    },
    {
        "id": "study",
        "title": "Build the observation evidence record",
        "npm": "cases:build",
        "purpose": "Join stations to basins, compute climatologies, the seasonal "
                   "benchmark and the joint climate-discharge months.",
        "produces": [
            "PUBLISHED/data/case-studies/chirchik.json",
            "PUBLISHED/data/case-studies/chirchik.manifest.json",
        ],
    },
    {
        "id": "daily-model",
        "title": "Calibrate the daily snowmelt model",
        "npm": "casestudy:dailymodel",
        "purpose": "Fit the temperature-index model over elevation bands on the "
                   "stratified split, then republish the study artefacts.",
        "produces": [
            "PUBLISHED/data/case-studies/pskem-daily-model.json",
            "PUBLISHED/data/case-studies/pskem-daily-model.csv",
            "PUBLISHED/data/case-studies/pskem-daily-model.manifest.json",
        ],
    },
    {
        "id": "review",
        "title": "Re-test the same structure chronologically",
        "npm": "cases:model-review",
        "purpose": "Recalibrate on 2002-2010 only, score 2011-2017, and compare "
                   "against a calibration-only monthly climatology on identical support.",
        "produces": ["PUBLISHED/data/case-studies/model-review.json"],
    },
    {
        "id": "publish",
        "title": "Derive the findings and figures the page shows",
        "npm": "cases:publish",
        "purpose": "Recompute skill from the daily series, redraw the figures and "
                   "derive every finding headline from the evidence.",
        "produces": [
            "PUBLISHED/data/case-studies/case-study-highlights.json",
            "PUBLISHED/data/case-studies/current-model.json",
            "PUBLISHED/data/case-studies/study-landing.manifest.json",
        ],
    },
]

# --------------------------------------------------------------------- results

# Each row names the file and the path inside it, so a reader checks the claim
# against the artefact rather than against this script.
RESULTS = [
    ("Daily runoff NSE, chronological held-out years", "model-review.json",
     "candidate.daily.nse", None, "chronological"),
    ("Monthly mean NSE, chronological held-out years", "model-review.json",
     "candidate.monthly.nse", None, "chronological"),
    ("April-September volume NSE, chronological held-out years", "model-review.json",
     "candidate.seasonal.nse", None, "chronological"),
    ("April-September volume NSE, calibration-only climatology", "model-review.json",
     "benchmark.seasonal.nse", None, "chronological"),
    ("Daily runoff NSE, stratified held-out years", "pskem-daily-model.json",
     "skill.validation.nse", None, "stratified"),
    ("Monthly mean NSE, stratified held-out years", "pskem-daily-model.json",
     "monthlySkill.validation.nse", None, "stratified"),
    ("April-September volume NSE, stratified held-out years", "pskem-daily-model.json",
     "seasonalValidationScores.nse", None, "stratified"),
    ("Seasons within one class, chronological", "model-review.json",
     "classes.within_one", "of 7 held-out years", "chronological"),
    ("Seasons in the exact class, chronological", "model-review.json",
     "classes.exact", "of 7 held-out years", "chronological"),
]

TEST_FILES = [
    ("TESTS/test_chirchik_case_studies.py", "npm run test:cases",
     "The observation record: screening, joins, climatology and benchmark."),
    ("TESTS/test_chirchik_advanced.py", "npm run test:cases",
     "The advanced validation and environment modelling artefacts."),
    ("TESTS/test_sabitov_methods.py", "npm run test:sabitov",
     "The independent methodology reimplementation and its diagnostics."),
    ("TESTS/test_case_study_highlights.py", "python -m pytest TESTS/test_case_study_highlights.py",
     "Every published finding is derived from evidence, not written by hand."),
    ("TESTS/test_pskem_model_review.py", "python -m pytest TESTS/test_pskem_model_review.py",
     "The chronological re-test: split integrity, leakage and benchmark support."),
    ("TESTS/test_study_landing.py", "python -m pytest TESTS/test_study_landing.py",
     "The published study landing document and its recomputation checks."),
]


def npm_scripts() -> dict:
    return load(PACKAGE_JSON)["scripts"]


def build_method(scripts: dict) -> list:
    stages = []
    for stage in STAGES:
        name = stage["npm"]
        if name not in scripts:
            raise SystemExit(
                f"Stage '{stage['id']}' names npm script '{name}', which package.json "
                "does not define. Fix the stage or the script before publishing a "
                "procedure a reader cannot run.")
        produces = []
        for target in stage["produces"]:
            path = ROOT / target
            if not path.exists():
                raise SystemExit(
                    f"Stage '{stage['id']}' claims to produce {target}, which is not "
                    "on disk. Run the stage, or correct the claim.")
            produces.append({
                "path": target,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            })
        stages.append({
            "id": stage["id"],
            "title": stage["title"],
            "purpose": stage["purpose"],
            "command": f"npm run {name}",
            "runs": scripts[name],
            "produces": produces,
        })
    return stages


def build_data() -> dict:
    """Inputs, separated into files a reader can hash and remote assets they must fetch."""
    files, seen = [], set()

    def record(path_text: str, role: str, recorded_sha: str | None = None):
        if path_text in seen:
            return
        seen.add(path_text)
        path = ROOT / path_text
        entry = {"path": path_text, "role": role, "available": path.exists()}
        if path.exists():
            entry["bytes"] = path.stat().st_size
            entry["sha256"] = sha256(path)
            # A recorded hash that no longer matches is the single most useful
            # thing this document can tell a reader, so it is stated, not hidden.
            if recorded_sha and recorded_sha != entry["sha256"]:
                entry["recordedSha256"] = recorded_sha
                entry["changedSinceRecorded"] = True
        elif recorded_sha:
            entry["recordedSha256"] = recorded_sha
        files.append(entry)

    manifest = load(STUDY / "chirchik.manifest.json")
    for row in manifest["provenance"]:
        record(row["path"], "observation record input", row.get("sha256"))

    daily = load(STUDY / "pskem-daily-model.manifest.json")
    for path_text in daily.get("inputs", []):
        record(path_text, "daily model input")

    review = load(STUDY / "model-review.json")
    for path_text, recorded in (review.get("inputs") or {}).items():
        record(path_text, "chronological re-test input", recorded)

    # Remote sources are named by the manifests that reduced them. They cannot be
    # hashed here, so they are listed with the asset id and the retrieval date.
    # The same asset can serve two stages, so uses are collected under one entry
    # rather than repeated: a reader fetches the asset once.
    remote: dict[str, dict] = {}
    for name, keys in (
        ("sabitov-inputs.manifest.json",
         ("daily_asset", "dem_asset", "glacier_source")),
        ("environment-profile.manifest.json",
         ("dem_asset", "landcover_asset")),
    ):
        path = STUDY / name
        if not path.exists():
            continue
        document = load(path)
        for key in keys:
            value = document.get(key)
            if not value:
                continue
            entry = remote.setdefault(value, {"asset": value, "usedAs": [], "recordedIn": [],
                                              "retrievedAt": document.get("retrieved_at")})
            if key not in entry["usedAs"]:
                entry["usedAs"].append(key)
            if relative(path) not in entry["recordedIn"]:
                entry["recordedIn"].append(relative(path))

    products = []
    station_products = STUDY / "station-product-monthly.manifest.json"
    if station_products.exists():
        document = load(station_products)
        for product in document.get("products", []):
            products.append(product if isinstance(product, str) else json.dumps(product))

    return {
        "files": files,
        "remoteAssets": sorted(remote.values(), key=lambda entry: entry["asset"]),
        "griddedProducts": products,
        "note": ("Local files can be hashed and compared directly. Remote assets are "
                 "named by their catalogue id and the date they were reduced; a "
                 "re-run against a later collection version may differ."),
    }


def build_results() -> list:
    rows = []
    for label, file_name, pointer, unit, split in RESULTS:
        path = STUDY / file_name
        if not path.exists():
            raise SystemExit(f"Result '{label}' reads {file_name}, which is missing.")
        value = dig(load(path), pointer)
        rows.append({
            "label": label,
            "value": round(value, 4) if isinstance(value, float) else value,
            "unit": unit,
            "split": split,
            "source": f"PUBLISHED/data/case-studies/{file_name}",
            "pointer": pointer,
        })
    return rows


def build_tests() -> list:
    """Read the assertions out of the test files rather than describing them."""
    suites = []
    for path_text, command, purpose in TEST_FILES:
        path = ROOT / path_text
        if not path.exists():
            raise SystemExit(f"Declared test file {path_text} does not exist.")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        cases = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                doc = ast.get_docstring(node) or ""
                cases.append({
                    "name": node.name,
                    "asserts": doc.strip().splitlines()[0] if doc else None,
                })
        if not cases:
            raise SystemExit(f"{path_text} declares no test functions.")
        suites.append({
            "path": path_text,
            "command": command,
            "purpose": purpose,
            "sha256": sha256(path),
            "caseCount": len(cases),
            "cases": sorted(cases, key=lambda case: case["name"]),
        })
    return suites


def build_verification() -> dict:
    """What an independent recomputation of the published numbers produced."""
    landing = STUDY / "study-landing.manifest.json"
    if not landing.exists():
        raise SystemExit("study-landing.manifest.json is missing; run npm run cases:publish.")
    document = load(landing)
    model = load(STUDY / "pskem-daily-model.json")
    checks = []
    for key, pointer, label in (
        ("daily_validation_nse_recomputed", "skill.validation.nse",
         "Daily NSE recomputed from the published daily series"),
        ("monthly_validation_nse_recomputed", "monthlySkill.validation.nse",
         "Monthly NSE recomputed from the published daily series"),
    ):
        if key not in document:
            continue
        recomputed, published = document[key], dig(model, pointer)
        difference = abs(recomputed - published)
        checks.append({
            "label": label,
            "published": round(published, 4),
            "recomputed": round(recomputed, 4),
            "absoluteDifference": round(difference, 6),
            "tolerance": RECOMPUTATION_TOLERANCE,
            "withinTolerance": difference <= RECOMPUTATION_TOLERANCE,
        })
    if not checks:
        raise SystemExit("No recomputation checks were found to verify.")

    # The stronger check: the whole stage rerun and diffed, not one number redone.
    if not REPRODUCTION.exists():
        raise SystemExit("reproduction-check.json is missing; run npm run cases:reproduce.")
    rerun = load(REPRODUCTION)
    return {
        "checks": checks,
        "allWithinTolerance": all(check["withinTolerance"] for check in checks),
        "rerun": {
            "stage": rerun["stage"],
            "compared": rerun["compared"],
            "reproduced": rerun["reproduced"],
            "substantiveDifferenceCount": rerun["substantiveDifferenceCount"],
            "provenanceDifferenceCount": rerun["provenanceDifferenceCount"],
            "substantiveDifferences": rerun["substantiveDifferences"][:10],
            "checkedAt": rerun["generatedAt"],
            "command": "npm run cases:reproduce",
        },
        "method": ("Two independent checks. The scores the page shows are recomputed "
                   "from the published daily CSV and compared with the model's own "
                   "summary. Separately, the observation stage is rebuilt into a "
                   "temporary directory and diffed field by field against what is "
                   "published, so a drift between the code and the artefacts shows up "
                   "as a difference rather than as silence."),
    }


def build_transferability() -> dict:
    """Where the method has actually been exercised, and where it has not.

    A study that has run in one catchment for one period has not demonstrated
    transfer, so the untested rows are listed with the same weight as the tested
    ones. The requirements come from the study gates already recorded in
    chirchik.json, not from a judgement made here.
    """
    study = load(STUDY / "chirchik.json")
    review = load(STUDY / "model-review.json")
    model = load(STUDY / "pskem-daily-model.json")
    catchment = load(STUDY / "pskem-candidate-catchment.geojson")
    subbasins = catchment["features"]
    area = sum(feature["properties"].get("SUB_AREA", 0) for feature in subbasins)

    train, test = review["train_years"], review["test_years"]
    tested = [{
        "domain": "Pskem at Mullala, western Tian Shan",
        "extent": f"{len(subbasins)} level-12 sub-basins, {area:,.0f} km2 of candidate catchment",
        "period": f"{min(train)}-{max(test)}",
        "status": "exercised",
        "evidence": "PUBLISHED/data/case-studies/model-review.json",
        "note": (f"Calibrated on {min(train)}-{max(train)}, scored on {min(test)}-{max(test)}. "
                 "One gauge, one catchment, retrospective reanalysis forcing."),
    }]

    # Everything the study itself says it has not established.
    untested = [
        {
            "domain": "Chatkal, Ugam and the wider Chirchik",
            "period": "any",
            "status": "not attempted",
            "requirement": ("Independent tributary discharge, and a catchment delineation "
                            "confirmed against the surveyed gauge position."),
        },
        {
            "domain": "Amu Darya headwaters (Pyanj, Vakhsh, Surkhandarya)",
            "period": "any",
            "status": "not attempted",
            "requirement": ("Gauge records of comparable length, and a glacier melt term: "
                            "the Pskem fit carries no explicit ice component."),
        },
        {
            "domain": "Pskem, forward period after the record ends",
            "period": f"after {max(test)}",
            "status": "not attempted",
            "requirement": ("Forecast forcing rather than reanalysis, and discharge to "
                            "score against. The published record ends at "
                            f"{max(test)}."),
        },
    ]
    return {
        "tested": tested,
        "untested": untested,
        "gates": [gate for entry in study["studies"] for gate in entry.get("gates", [])],
        "warmUpYear": model.get("warmUp"),
        "statement": ("The model has been calibrated and held out within a single "
                      "catchment and a single 16-year record. No result here bears on "
                      "another basin or on a future period; those rows are open, not "
                      "pending publication."),
    }


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    scripts = npm_scripts()
    study = load(STUDY / "chirchik.json")
    review = load(STUDY / "model-review.json")

    package = {
        "version": "1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "study": {
            "id": "chirchik-pskem",
            "title": study["title"],
            "scope": study["scope"],
            "url": "/case-studies/chirchik",
            "question": ("Can daily snow accumulation and melt, driven by gridded "
                         "temperature and precipitation over elevation bands, reproduce "
                         "observed Pskem runoff well enough to classify a water year?"),
            "decision": review.get("decision"),
        },
        "data": build_data(),
        "method": build_method(scripts),
        "results": build_results(),
        "verification": build_verification(),
        "tests": build_tests(),
        "transferability": build_transferability(),
        "limitations": review.get("limitations", []),
    }
    package["counts"] = {
        "inputFiles": len(package["data"]["files"]),
        "remoteAssets": len(package["data"]["remoteAssets"]),
        "stages": len(package["method"]),
        "results": len(package["results"]),
        "testSuites": len(package["tests"]),
        "testCases": sum(suite["caseCount"] for suite in package["tests"]),
    }

    temporary = OUTPUT.with_suffix(OUTPUT.suffix + ".tmp")
    temporary.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, OUTPUT)

    counts = package["counts"]
    missing = [row["path"] for row in package["data"]["files"] if not row["available"]]
    changed = [row["path"] for row in package["data"]["files"] if row.get("changedSinceRecorded")]
    print(f"  data      {counts['inputFiles']} input files, {counts['remoteAssets']} remote assets")
    print(f"  method    {counts['stages']} stages, every npm script resolved")
    print(f"  results   {counts['results']} published values read from their source files")
    rerun = package["verification"]["rerun"]
    print(f"  verify    recomputation within tolerance: {package['verification']['allWithinTolerance']}; "
          f"stage rerun reproduced: {rerun['reproduced']} "
          f"({rerun['substantiveDifferenceCount']} substantive differences)")
    print(f"  tests     {counts['testSuites']} suites, {counts['testCases']} cases")
    print(f"  transfer  {len(package['transferability']['tested'])} exercised, "
          f"{len(package['transferability']['untested'])} open")
    if missing:
        print(f"  MISSING   {len(missing)} declared inputs are not on disk: {missing[:3]}")
    if changed:
        print(f"  CHANGED   {len(changed)} inputs differ from their recorded hash: {changed[:3]}")
    print(f"  -> {relative(OUTPUT)}")


if __name__ == "__main__":
    main()
