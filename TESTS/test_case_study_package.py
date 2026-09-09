"""The reproducibility package must describe the repository, not a memory of it.

The package exists so a reader can obtain the data, run the procedure, compare
the result and see where the method has not been tried. Each of those claims is
only worth making if it is checked, so these tests assert that what the document
says can be resolved back to the repository: commands that exist, artefacts that
exist, numbers that still read back from their source, tests that are still
present under the names given.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "PUBLISHED/data/case-studies"
PACKAGE = STUDY / "reproducibility-package.json"


@pytest.fixture(scope="module")
def package():
    if not PACKAGE.exists():
        pytest.skip("reproducibility-package.json is not published")
    return json.loads(PACKAGE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def scripts():
    return json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["scripts"]


def test_every_stage_names_a_command_the_repository_defines(package, scripts):
    """A procedure a reader cannot run is not a procedure."""
    for stage in package["method"]:
        assert stage["command"].startswith("npm run "), stage["id"]
        name = stage["command"][len("npm run "):]
        assert name in scripts, f"{stage['id']} names missing script {name}"
        assert scripts[name] == stage["runs"], f"{stage['id']} records a stale command"


def test_every_declared_artefact_exists_and_matches_its_hash(package):
    """A hash that no longer matches is a silent lie about what produced the result."""
    for stage in package["method"]:
        for output in stage["produces"]:
            path = ROOT / output["path"]
            assert path.exists(), f"{stage['id']} claims {output['path']}"
            assert path.stat().st_size == output["bytes"], output["path"]
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            assert digest == output["sha256"], f"{output['path']} changed since publication"


def test_stage_order_runs_producers_before_consumers(package):
    """Reading the stages top to bottom has to be a runnable order."""
    produced = set()
    for stage in package["method"]:
        produced.update(output["path"] for output in stage["produces"])
    # The observation stage must come before the model that consumes its discharge.
    ids = [stage["id"] for stage in package["method"]]
    assert ids.index("observations") < ids.index("daily-model")
    assert ids.index("daily-model") < ids.index("review")
    assert ids.index("review") < ids.index("publish")
    assert "PUBLISHED/data/case-studies/pskem-daily-model.json" in produced


def test_every_published_result_still_reads_back_from_its_source(package):
    """A result table that drifts from the artefacts is worse than no table."""
    for row in package["results"]:
        source = ROOT / row["source"]
        assert source.exists(), row["source"]
        value = json.loads(source.read_text(encoding="utf-8"))
        for key in row["pointer"].split("."):
            value = value[int(key)] if isinstance(value, list) else value[key]
        if isinstance(value, float):
            assert round(value, 4) == pytest.approx(row["value"], abs=1e-4), row["label"]
        else:
            assert value == row["value"], row["label"]


def test_both_splits_are_reported_for_the_seasonal_volume(package):
    """The two splits disagree, so hiding either would let a reader pick a favourite."""
    seasonal = [row for row in package["results"] if "volume NSE" in row["label"]]
    splits = {row["split"] for row in seasonal}
    assert {"chronological", "stratified"} <= splits
    strict = next(row for row in seasonal
                  if row["split"] == "chronological" and "held-out" in row["label"])
    benchmark = next(row for row in package["results"] if "climatology" in row["label"])
    assert strict["value"] > benchmark["value"], (
        "the model should still beat the climatology it is compared against")


def test_declared_tests_exist_with_the_cases_named(package):
    """Test names are read from the files, so a renamed check cannot linger here."""
    import ast
    for suite in package["tests"]:
        path = ROOT / suite["path"]
        assert path.exists(), suite["path"]
        tree = ast.parse(path.read_text(encoding="utf-8"))
        present = {node.name for node in ast.walk(tree)
                   if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and node.name.startswith("test_")}
        named = {case["name"] for case in suite["cases"]}
        assert named <= present, f"{suite['path']} no longer defines {sorted(named - present)}"
        assert suite["caseCount"] == len(suite["cases"])


def test_verification_reports_a_real_rerun_not_a_claim(package):
    """The validation question is answered by rebuilding, so the rebuild must be recorded."""
    rerun = package["verification"]["rerun"]
    assert rerun["command"].startswith("npm run ")
    assert rerun["stage"]
    assert isinstance(rerun["reproduced"], bool)
    # If it reproduced, there must be no substantive differences left unexplained.
    if rerun["reproduced"]:
        assert rerun["substantiveDifferenceCount"] == 0
    else:
        assert rerun["substantiveDifferences"], "a failed reproduction must show what differed"


def test_recomputation_checks_carry_their_own_tolerance(package):
    """A published tolerance is what makes 'approximately the same' checkable."""
    checks = package["verification"]["checks"]
    assert checks
    for check in checks:
        assert check["tolerance"] > 0
        assert check["withinTolerance"] == (check["absoluteDifference"] <= check["tolerance"])


def test_transferability_lists_untested_domains_beside_tested_ones(package):
    """A method exercised in one catchment has not been shown to transfer."""
    transfer = package["transferability"]
    assert transfer["tested"], "the exercised domain must be stated"
    assert transfer["untested"], "untested domains must be visible, not omitted"
    for row in transfer["untested"]:
        assert row["status"] == "not attempted"
        assert row["requirement"], f"{row['domain']} must say what it would take"
    tested_periods = {row["period"] for row in transfer["tested"]}
    assert all("-" in period for period in tested_periods), "an exercised row needs a real period"


def test_input_files_are_hashed_and_drift_is_reported(package):
    """Silence about a changed input is the failure mode this document exists to prevent."""
    files = package["data"]["files"]
    assert files
    for entry in files:
        if not entry["available"]:
            continue
        path = ROOT / entry["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], entry["path"]
        # Drift is allowed to exist, but never silently: it must be flagged.
        if entry.get("recordedSha256"):
            assert entry["changedSinceRecorded"] is True


def test_the_builder_refuses_a_stage_whose_command_is_missing(tmp_path):
    """The guarantee is only real if an unrunnable stage stops the build."""
    builder = ROOT / "PIPELINES/build_case_study_package.py"
    source = builder.read_text(encoding="utf-8")
    assert '"npm": "cases:build"' in source
    broken = tmp_path / "broken_package_builder.py"
    # The copy lives outside PIPELINES, so its own path no longer locates the
    # repository; ROOT is pinned back before the stage name is broken.
    broken.write_text(
        source.replace("ROOT = Path(__file__).resolve().parent.parent",
                       f"ROOT = Path(r{str(ROOT)!r})")
              .replace('"npm": "cases:build"', '"npm": "cases:does-not-exist"'),
        encoding="utf-8")
    completed = subprocess.run([sys.executable, str(broken)], capture_output=True,
                               text=True, encoding="utf-8", errors="replace", cwd=str(ROOT))
    assert completed.returncode != 0
    assert "does not define" in (completed.stdout + completed.stderr)
