"""Execute an allowlisted data group, keeping failures distinct from successful updates."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def emit(type, **fields):
    print(json.dumps({"type": type, **fields}), flush=True)


def preflight(group, root=ROOT):
    missing = [p for p in group.get("requires", []) if not (root / p).exists()]
    if missing:
        raise RuntimeError("Required local inputs are missing: " + ", ".join(missing))
    modules = [name for name in group.get("modules", []) if importlib.util.find_spec(name) is None]
    if modules:
        raise RuntimeError("Install requirements-pipelines.txt in the configured Python environment. Missing: " + ", ".join(modules))
    if group.get("earth_engine"):
        try:
            import ee
            from PIPELINES.extract_dated_snow import PROJECT
            ee.Initialize(project=PROJECT)
        except Exception:
            raise RuntimeError("Earth Engine is not ready. Authenticate the pipeline environment and verify access to the configured project.") from None


def execute(group, root=ROOT):
    preflight(group, root)
    commands = group.get("commands", [])
    if group["kind"] == "regional":
        from PIPELINES import refresh_regional_record as refresh
        report = refresh.source_extent(only=[group["source"]])
        latest = report.get(group["source"], {}).get("latest")
        if not latest:
            raise RuntimeError("The provider did not report an available month. No data were changed.")
        # Daily MODIS and monthly sources must not ingest the current, unfinished month.
        now = datetime.now(timezone.utc)
        previous = f"{now.year - (now.month == 1):04d}-{12 if now.month == 1 else now.month - 1:02d}"
        target = min(latest, previous)
        if all((root / p).exists() for p in group.get("full_requires", [])):
            commands = [["PIPELINES/refresh_regional_record.py", "--extend", target, "--source", group["source"]]]
        else:
            # Temporary: without the observation store, extend Git's published record directly.
            emit("progress", progress=1, message="Observation store not present: appending new months to the published record")
            commands = [["PIPELINES/update_published_record.py", group["source"], "--through", target]]
    log_dir = root / "WORKSPACE/data-updates/logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    with (log_dir / f"{group['id']}-{stamp}.log").open("w", encoding="utf-8") as log:
        for index, command in enumerate(commands):
            emit("progress", progress=round(index / (len(commands) + 1) * 100), message=f"Running step {index + 1} of {len(commands)}: {Path(command[0]).stem}")
            result = subprocess.run([sys.executable, *command], cwd=root, stdout=log, stderr=subprocess.STDOUT)
            log.flush()
            if result.returncode:
                raise RuntimeError(f"{Path(command[0]).stem} failed (exit {result.returncode}). Review the private log in WORKSPACE/data-updates/logs; this job has not been marked updated.")
    emit("progress", progress=95, message="Refreshing the variable inventory")
    # Only after all steps succeed may the inventory gain a successful update timestamp.
    from PIPELINES import build_variable_inventory as inventory
    finished = datetime.now(timezone.utc).isoformat()
    updates = inventory.read(root, "PUBLISHED/data/variable-updates.json")
    updates[group["id"]] = {"finished_at": finished}
    update_file = root / "PUBLISHED/data/variable-updates.json"
    temporary = update_file.with_suffix(".tmp")
    temporary.write_text(json.dumps(updates, indent=2) + "\n", encoding="utf-8")
    temporary.replace(update_file)
    report = inventory.build(root)
    out = root / "PUBLISHED/data/variable-inventory.json"
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(out)


def main():
    groups = json.loads((ROOT / "ATLAS_MODULES/update-groups.json").read_text())["groups"]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("group", choices=[g["id"] for g in groups])
    args = parser.parse_args()
    try:
        execute(next(g for g in groups if g["id"] == args.group))
    except Exception as error:
        emit("failure", message=str(error))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
