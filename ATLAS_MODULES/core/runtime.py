"""Monotonic wall/CPU timing, progress and immutable run provenance helpers."""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


class RunTimer:
    """Sequential stages partition total wall time; subtask times are not added twice."""
    def __init__(self, run_id, directory, progress_path=None):
        self.run_id = run_id
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.progress_path = progress_path
        self.started_at = utc_now()
        self.started = time.perf_counter()
        self.cpu_started = time.process_time()
        self.stages = []
        self.current = None
        self.status = "running"
        self.events = []
        self.publish()

    def snapshot(self):
        wall = time.perf_counter() - self.started
        result = {"run_id": self.run_id, "status": self.status,
                  "started_at": self.started_at, "updated_at": utc_now(),
                  "wall_seconds": wall, "cpu_seconds": time.process_time() - self.cpu_started,
                  "stages": self.stages, "active_stage": self.current,
                  "events": self.events[-100:],
                  "timing_note": "Wall time runs from timer initialization through scientific run-package export; excludes development, research, tests, final timing serialization and web publication. CPU is the main Python process only. Subtasks are included in their parent stage; shared preparation is not charged to every attribute."}
        if self.status != "running":
            result["overhead_seconds"] = max(0, wall - sum(s["wall_seconds"] for s in self.stages))
            result["finished_at"] = result["updated_at"]
        return result

    def publish(self):
        value = self.snapshot()
        write_json(self.directory / "timing.json", value)
        if self.progress_path:
            write_json(self.progress_path, value)
        return value

    def event(self, message, **details):
        entry = {"at": utc_now(), "message": message, **details}
        self.events.append(entry)
        with (self.directory / "processing.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"[{time.perf_counter() - self.started:8.2f}s] {message}", flush=True)
        self.publish()

    @contextmanager
    def stage(self, name, **details):
        if self.current is not None:
            raise RuntimeError("Stages cannot overlap; time shared work only once")
        start, cpu = time.perf_counter(), time.process_time()
        self.current = {"name": name, "started_at": utc_now(), **details}
        self.event(f"START {name}")
        status = "complete"
        try:
            yield
        except BaseException:
            status = "failed"
            raise
        finally:
            self.stages.append({**self.current, "status": status,
                                "wall_seconds": time.perf_counter() - start,
                                "cpu_seconds": time.process_time() - cpu})
            self.current = None
            self.event(f"END {name}: {self.stages[-1]['wall_seconds']:.3f}s")

    def finish(self, status="complete"):
        self.status = status
        return self.publish()
