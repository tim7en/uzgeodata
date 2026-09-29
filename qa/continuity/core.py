"""Small, auditable research registry. No scientific computation runs here."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


STATES = {"PROPOSED", "APPROVED", "IN_PROGRESS", "BLOCKED", "AWAITING_VALIDATION", "VALIDATED", "COMPLETED", "CANCELLED"}
TRANSITIONS = {
    "PROPOSED": {"APPROVED", "CANCELLED"},
    "APPROVED": {"IN_PROGRESS", "BLOCKED", "CANCELLED"},
    "IN_PROGRESS": {"BLOCKED", "AWAITING_VALIDATION", "CANCELLED"},
    "BLOCKED": {"APPROVED", "IN_PROGRESS", "CANCELLED"},
    "AWAITING_VALIDATION": {"VALIDATED", "IN_PROGRESS", "BLOCKED", "CANCELLED"},
    "VALIDATED": {"COMPLETED", "IN_PROGRESS"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}
DEFAULT_LIMITS = {
    "max_concurrent_tasks": 1,
    "max_execution_seconds": 3600,
    "max_storage_bytes": 1_000_000_000,
    "max_download_bytes": 0,
    "max_external_requests": 0,
    "max_retries": 0,
}


class ResearchError(ValueError):
    """Invalid state, unsafe path, or integrity failure."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class ResearchStore:
    def __init__(self, directory: str | Path, workspace: str | Path):
        self.directory = Path(directory).resolve()
        self.workspace = Path(workspace).resolve()
        self.registry = self.directory / "registry.json"
        self.lock = self.directory / ".registry.lock"

    def _relative_file(self, filename: str) -> Path:
        path = (self.workspace / filename).resolve()
        if not path.is_relative_to(self.workspace) or not path.is_file():
            raise ResearchError(f"File missing or outside workspace: {filename}")
        return path

    def _file_record(self, filename: str) -> dict:
        path = self._relative_file(filename)
        return {"path": path.relative_to(self.workspace).as_posix(), "sha256": sha256(path), "bytes": path.stat().st_size}

    @contextmanager
    def _locked(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise ResearchError(f"Registry locked: {self.lock}; inspect owner before manual removal") from exc
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(json.dumps({"pid": os.getpid(), "created_at": now()}))
                stream.flush()
                os.fsync(stream.fileno())
            yield
        finally:
            self.lock.unlink(missing_ok=True)

    def _load(self) -> dict:
        if not self.registry.exists():
            raise ResearchError("Registry absent; run init")
        try:
            data = json.loads(self.registry.read_text(encoding="utf-8"))
            if data["schema_version"] != 1 or not isinstance(data["projects"], dict):
                raise ResearchError("Unsupported registry schema")
            return data
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ResearchError("Registry malformed") from exc

    def _save(self, data: dict):
        self.directory.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".registry-", suffix=".tmp", dir=self.directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, indent=2, ensure_ascii=False, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.registry)
        finally:
            Path(name).unlink(missing_ok=True)

    def init(self):
        with self._locked():
            if self.registry.exists():
                raise ResearchError("Registry already exists")
            self._save({"schema_version": 1, "created_at": now(), "limits": DEFAULT_LIMITS.copy(), "projects": {}})

    def read(self) -> dict:
        return self._load()

    @staticmethod
    def _project(data: dict, project_id: str) -> dict:
        try:
            return data["projects"][project_id]
        except KeyError as exc:
            raise ResearchError(f"Unknown project: {project_id}") from exc

    @staticmethod
    def _task(project: dict, task_id: str) -> dict:
        try:
            return project["tasks"][task_id]
        except KeyError as exc:
            raise ResearchError(f"Unknown task: {task_id}") from exc

    def add_project(self, project_id: str, objective: str, questions: list[str], scope: str, basins: list[str], sources: list[str], methodology: str):
        if not all([project_id, objective, questions, scope, basins, sources, methodology]):
            raise ResearchError("Project identifier, objective, questions, scope, basins, sources, and methodology are required")
        with self._locked():
            data = self._load()
            if project_id in data["projects"]:
                raise ResearchError("Project identifier already exists")
            data["projects"][project_id] = {"objective": objective, "questions": questions, "scope": scope, "basins": basins, "sources": sources, "methodology": methodology, "tasks": {}, "memory": [], "outstanding_questions": [], "created_at": now()}
            self._save(data)

    def add_task(self, project_id: str, task_id: str, title: str, owner: str, dependencies: list[str], next_actions: list[str]):
        if not all([task_id, title, owner, next_actions]):
            raise ResearchError("Task identifier, title, owner, and next actions are required")
        with self._locked():
            data = self._load()
            project = self._project(data, project_id)
            if task_id in project["tasks"]:
                raise ResearchError("Task identifier already exists")
            if task_id in dependencies or any(dep not in project["tasks"] for dep in dependencies):
                raise ResearchError("Dependencies must already exist and cannot include the task")
            project["tasks"][task_id] = {"title": title, "owner": owner, "dependencies": dependencies, "next_actions": next_actions, "status": "PROPOSED", "checkpoints": [], "handoffs": [], "history": [{"at": now(), "to": "PROPOSED", "by": owner, "reason": "created"}]}
            self._save(data)

    def transition(self, project_id: str, task_id: str, state: str, actor: str, reason: str, validation_evidence: list[str] | None = None):
        if state not in STATES or not actor or not reason:
            raise ResearchError("Valid state, actor, and reason required")
        with self._locked():
            data = self._load()
            project = self._project(data, project_id)
            task = self._task(project, task_id)
            old = task["status"]
            if state not in TRANSITIONS[old]:
                raise ResearchError(f"Invalid transition: {old} -> {state}")
            if state == "APPROVED" and actor == task["owner"]:
                raise ResearchError("Task owner cannot approve their own work")
            if state == "IN_PROGRESS":
                unmet = [dep for dep in task["dependencies"] if project["tasks"][dep]["status"] not in ("VALIDATED", "COMPLETED")]
                if unmet:
                    raise ResearchError(f"Unvalidated dependencies: {', '.join(unmet)}")
                active = sum(t["status"] == "IN_PROGRESS" for p in data["projects"].values() for t in p["tasks"].values())
                if old != "IN_PROGRESS" and active >= data["limits"]["max_concurrent_tasks"]:
                    raise ResearchError("Concurrent task limit reached")
            evidence = []
            if state == "VALIDATED":
                if actor == task["owner"]:
                    raise ResearchError("Independent validator must differ from task owner")
                if not validation_evidence:
                    raise ResearchError("Validation evidence files required")
                evidence = [self._file_record(path) for path in validation_evidence]
            task["status"] = state
            task["history"].append({"at": now(), "from": old, "to": state, "by": actor, "reason": reason, "validation_evidence": evidence})
            self._save(data)

    def checkpoint(self, project_id: str, task_id: str, milestone: str, inputs: list[str], outputs: list[str], parameters: dict, instructions: str, code_version: str, actor: str):
        if not all([milestone, outputs, instructions, code_version, actor]):
            raise ResearchError("Milestone, outputs, instructions, code version, and actor required")
        with self._locked():
            data = self._load()
            task = self._task(self._project(data, project_id), task_id)
            if task["status"] != "IN_PROGRESS" or task["owner"] != actor:
                raise ResearchError("Only task owner may checkpoint work in progress")
            records = {"inputs": [self._file_record(p) for p in inputs], "outputs": [self._file_record(p) for p in outputs]}
            entry = {"at": now(), "milestone": milestone, **records, "parameters": parameters, "instructions": instructions, "code_version": code_version, "python_version": platform.python_version(), "status": "SUCCEEDED", "actor": actor}
            task["checkpoints"].append(entry)
            self._save(data)
            return entry

    def add_memory(self, project_id: str, kind: str, claim: str, evidence: list[str], actor: str):
        allowed = {"hypothesis", "supporting_evidence", "contradictory_evidence", "failed_experiment", "limitation", "method_decision", "unresolved_issue", "verified_finding"}
        if kind not in allowed or not claim or not actor or not evidence:
            raise ResearchError("Memory requires type, claim, actor, and evidence files")
        if kind == "verified_finding":
            raise ResearchError("Use independent task validation before publishing findings")
        with self._locked():
            data = self._load()
            project = self._project(data, project_id)
            project["memory"].append({"at": now(), "kind": kind, "claim": claim, "evidence": [self._file_record(p) for p in evidence], "actor": actor, "verified": False})
            self._save(data)

    def handoff(self, project_id: str, task_id: str, actor: str, completed: list[str], evidence: list[str], verified: list[str], discrepancies: list[str], files: list[str], blockers: list[str], next_actions: list[str], resume_commands: list[str], resources: list[str]):
        if not actor or not next_actions or not resume_commands:
            raise ResearchError("Handoff requires actor, next actions, and resume commands")
        with self._locked():
            data = self._load()
            task = self._task(self._project(data, project_id), task_id)
            if actor != task["owner"]:
                raise ResearchError("Only task owner may hand off")
            entry = {"at": now(), "actor": actor, "completed": completed, "evidence": [self._file_record(p) for p in evidence], "verified": verified, "discrepancies": discrepancies, "files": [self._file_record(p) for p in files], "blockers": blockers, "next_actions": next_actions, "resume_commands": resume_commands, "resources": resources}
            task["handoffs"].append(entry)
            task["next_actions"] = next_actions
            self._save(data)
            return entry

    def resume(self, project_id: str, task_id: str, owner: str, code_version: str | None = None) -> dict:
        data = self._load()
        project = self._project(data, project_id)
        task = self._task(project, task_id)
        if owner != task["owner"]:
            raise ResearchError("Task is assigned to another owner")
        valid = []
        invalid = []
        for index, checkpoint in enumerate(task["checkpoints"]):
            problems = []
            if code_version and checkpoint["code_version"] != code_version:
                problems.append(f"code version changed: {checkpoint['code_version']} -> {code_version}")
            for record in checkpoint["inputs"] + checkpoint["outputs"]:
                try:
                    current = self._file_record(record["path"])
                    if current["sha256"] != record["sha256"]:
                        problems.append(f"changed: {record['path']}")
                except ResearchError:
                    problems.append(f"missing: {record['path']}")
            if problems:
                invalid.append({"index": index, "milestone": checkpoint["milestone"], "problems": problems})
                break
            valid.append(checkpoint)
        last = valid[-1] if valid else None
        dependencies_ready = all(project["tasks"][dep]["status"] in ("VALIDATED", "COMPLETED") for dep in task["dependencies"])
        return {"project_id": project_id, "task_id": task_id, "status": task["status"], "owner": owner, "dependencies_ready": dependencies_ready, "last_valid_checkpoint": last, "validated_checkpoint_count": len(valid), "invalid_checkpoints": invalid, "safe_to_resume": task["status"] in ("APPROVED", "IN_PROGRESS", "BLOCKED") and dependencies_ready and not invalid, "methodology": project["methodology"], "sources": project["sources"], "next_actions": task["next_actions"], "last_handoff": task["handoffs"][-1] if task["handoffs"] else None}

    def status(self) -> dict:
        data = self._load()
        return {"limits": data["limits"], "projects": {pid: {"objective": p["objective"], "tasks": {tid: {"status": t["status"], "owner": t["owner"], "checkpoints": len(t["checkpoints"]), "dependencies": t["dependencies"]} for tid, t in p["tasks"].items()}} for pid, p in data["projects"].items()}}
