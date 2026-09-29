import json
import subprocess
import sys
from pathlib import Path

import pytest

from qa.continuity import ResearchError, ResearchStore


def seeded(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = ResearchStore(tmp_path / "state", workspace)
    store.init()
    store.add_project("amu", "Mean temperature", ["What is basin mean?"], "Amu Darya, 2000", ["AMU"], ["Synthetic sample v1"], "Area-weighted mean; independent verification")
    store.add_task("amu", "calculate", "Calculate mean", "agent-a", [], ["Prepare inputs"])
    store.transition("amu", "calculate", "APPROVED", "reviewer", "Authorized")
    store.transition("amu", "calculate", "IN_PROGRESS", "agent-a", "Start")
    return store, workspace


def test_new_process_resumes_two_checkpoints_and_detects_changed_input(tmp_path):
    store, workspace = seeded(tmp_path)
    (workspace / "input.csv").write_text("temperature,area\n10,2\n20,1\n", encoding="utf-8")
    (workspace / "prepared.csv").write_text("10,2\n20,1\n", encoding="utf-8")
    store.checkpoint("amu", "calculate", "preprocessed", ["input.csv"], ["prepared.csv"], {"units": "C"}, "Copy valid rows", "git:123", "agent-a")
    (workspace / "result.txt").write_text("13.3333333333", encoding="utf-8")
    store.checkpoint("amu", "calculate", "computed", ["prepared.csv"], ["result.txt"], {"weights": "area"}, "sum(temp*area)/sum(area)", "git:123", "agent-a")
    store.handoff("amu", "calculate", "agent-a", ["Prepared data", "Computed mean"], ["result.txt"], [], [], ["result.txt"], [], ["Independent validation"], ["python -m qa.continuity resume amu calculate --owner agent-a"], [])

    command = [sys.executable, "-m", "qa.continuity", "--store", str(store.directory), "--workspace", str(workspace), "resume", "amu", "calculate", "--owner", "agent-a", "--code-version", "git:123"]
    result = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, check=True)
    report = json.loads(result.stdout)
    assert report["validated_checkpoint_count"] == 2
    assert report["last_valid_checkpoint"]["milestone"] == "computed"
    assert report["safe_to_resume"] is True
    assert report["last_handoff"]["next_actions"] == ["Independent validation"]

    (workspace / "prepared.csv").write_text("CORRUPTED", encoding="utf-8")
    report = store.resume("amu", "calculate", "agent-a", "git:123")
    assert report["validated_checkpoint_count"] == 0
    assert report["safe_to_resume"] is False
    assert "changed: prepared.csv" in report["invalid_checkpoints"][0]["problems"]
    assert store.resume("amu", "calculate", "agent-a", "git:456")["safe_to_resume"] is False


def test_dependencies_validation_and_owner_separation(tmp_path):
    store, workspace = seeded(tmp_path)
    store.add_task("amu", "interpret", "Interpret", "agent-b", ["calculate"], ["Review evidence"])
    store.transition("amu", "interpret", "APPROVED", "reviewer", "Authorized")
    with pytest.raises(ResearchError, match="Unvalidated dependencies"):
        store.transition("amu", "interpret", "IN_PROGRESS", "agent-b", "Too early")
    store.transition("amu", "calculate", "AWAITING_VALIDATION", "agent-a", "Ready")
    with pytest.raises(ResearchError, match="Independent validator"):
        store.transition("amu", "calculate", "VALIDATED", "agent-a", "Self review", ["evidence.txt"])
    (workspace / "evidence.txt").write_text("Independent calculation agrees", encoding="utf-8")
    store.transition("amu", "calculate", "VALIDATED", "validator", "Separate implementation agrees", ["evidence.txt"])
    store.transition("amu", "interpret", "IN_PROGRESS", "agent-b", "Dependencies validated")
    assert store.status()["projects"]["amu"]["tasks"]["interpret"]["status"] == "IN_PROGRESS"


def test_atomic_registry_survives_failed_checkpoint_and_lock(tmp_path):
    store, workspace = seeded(tmp_path)
    original = store.registry.read_bytes()
    with pytest.raises(ResearchError, match="File missing"):
        store.checkpoint("amu", "calculate", "bad", [], ["missing.csv"], {}, "rerun", "git:123", "agent-a")
    assert store.registry.read_bytes() == original
    assert not store.lock.exists()
    store.lock.write_text('{"pid": 999999}', encoding="utf-8")
    with pytest.raises(ResearchError, match="Registry locked"):
        store.transition("amu", "calculate", "BLOCKED", "agent-a", "Cannot continue")
    assert store.registry.read_bytes() == original


def test_rejects_external_artifact_and_unverified_finding(tmp_path):
    store, workspace = seeded(tmp_path)
    outside = tmp_path / "external.txt"
    outside.write_text("outside", encoding="utf-8")
    with pytest.raises(ResearchError, match="outside workspace"):
        store.checkpoint("amu", "calculate", "bad", [], [str(outside)], {}, "rerun", "git:123", "agent-a")
    (workspace / "evidence.txt").write_text("Observation", encoding="utf-8")
    with pytest.raises(ResearchError, match="independent task validation"):
        store.add_memory("amu", "verified_finding", "Claim", ["evidence.txt"], "agent-a")
    store.add_memory("amu", "hypothesis", "Possible trend", ["evidence.txt"], "agent-a")
    assert store.read()["projects"]["amu"]["memory"][0]["verified"] is False
