"""Rebuild the case study into a scratch directory and diff it against what is published.

"Do I obtain approximately the same result?" is the question a reader cannot
answer from a report, because a report is written once and the pipeline moves on.
So it is answered here by actually running the pipeline again, into a temporary
directory so nothing published is touched, and comparing the two documents field
by field.

Two kinds of difference are expected and are reported separately rather than
ignored quietly: the generation timestamp, and the provenance hashes, which
record the inputs as they are *now* and therefore change whenever an input is
regenerated. Everything else - every statistic, series and screening decision -
must match exactly, because this stage reads stored files and does deterministic
arithmetic. A difference there means the published study no longer describes
what the code produces.

    python PIPELINES/verify_case_study_reproduction.py
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STUDY = ROOT / "PUBLISHED/data/case-studies"
PUBLISHED = STUDY / "chirchik.json"
BUILDER = ROOT / "PIPELINES/build_chirchik_case_studies.py"
OUTPUT = STUDY / "reproduction-check.json"
# The builder defaults this input to its own output directory, so redirecting the
# output would silently starve it and make an empty comparison look like a
# reproduction failure. It is passed explicitly instead.
FORCING = STUDY / "station-product-monthly.csv"

# Fields that legitimately differ between two runs of the same code.
VOLATILE_KEYS = {"generated_at", "retrieved_at"}
PROVENANCE_PREFIX = ".provenance["


def compare(left, right, path: str = "") -> list:
    """Every leaf difference, with the path that reaches it."""
    if type(left) is not type(right):
        return [{"path": path, "published": repr(left)[:120], "rebuilt": repr(right)[:120]}]
    if isinstance(left, dict):
        differences = []
        for key in sorted(set(left) | set(right)):
            if key in VOLATILE_KEYS:
                continue
            if key not in left:
                differences.append({"path": f"{path}.{key}", "published": None, "rebuilt": "added"})
            elif key not in right:
                differences.append({"path": f"{path}.{key}", "published": "removed", "rebuilt": None})
            else:
                differences += compare(left[key], right[key], f"{path}.{key}")
        return differences
    if isinstance(left, list):
        differences = []
        if len(left) != len(right):
            differences.append({"path": f"{path}[length]", "published": len(left), "rebuilt": len(right)})
        for index, (a, b) in enumerate(zip(left, right)):
            differences += compare(a, b, f"{path}[{index}]")
        return differences
    if left != right:
        return [{"path": path, "published": repr(left)[:120], "rebuilt": repr(right)[:120]}]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="keep the scratch rebuild for inspection")
    arguments = parser.parse_args()

    if not PUBLISHED.exists():
        raise SystemExit(f"{PUBLISHED.name} is not published; run npm run cases:build first.")

    scratch = Path(tempfile.mkdtemp(prefix="case-study-reproduction-"))
    started = datetime.now(timezone.utc)
    if not FORCING.exists():
        raise SystemExit(f"{FORCING.name} is missing; the rebuild would have nothing to validate against.")
    completed = subprocess.run(
        [sys.executable, str(BUILDER), "--output", str(scratch), "--forcing", str(FORCING)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT))
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "").strip().splitlines()[-8:]
        raise SystemExit("The rebuild failed, so reproduction cannot be judged:\n  "
                         + "\n  ".join(tail))

    rebuilt_path = scratch / PUBLISHED.name
    if not rebuilt_path.exists():
        raise SystemExit(f"The rebuild wrote no {PUBLISHED.name} into {scratch}.")

    published = json.loads(PUBLISHED.read_text(encoding="utf-8"))
    rebuilt = json.loads(rebuilt_path.read_text(encoding="utf-8"))
    differences = compare(published, rebuilt)
    provenance = [row for row in differences if row["path"].startswith(PROVENANCE_PREFIX)]
    substantive = [row for row in differences if not row["path"].startswith(PROVENANCE_PREFIX)]

    payload = {
        "version": "1.0",
        "generatedAt": started.isoformat(timespec="seconds"),
        "stage": "npm run cases:build",
        "forcing": str(FORCING.relative_to(ROOT)).replace("\\", "/"),
        "compared": str(PUBLISHED.relative_to(ROOT)).replace("\\", "/"),
        "rebuildSeconds": round(elapsed, 1),
        "reproduced": not substantive,
        "substantiveDifferences": substantive[:50],
        "substantiveDifferenceCount": len(substantive),
        "provenanceDifferenceCount": len(provenance),
        "provenanceDifferences": [row["path"] for row in provenance],
        "method": ("The study is rebuilt into a temporary directory from the same "
                   "stored inputs and compared field by field. Generation "
                   "timestamps are excluded. Provenance hashes are counted "
                   "separately because they record the inputs as they are now."),
    }
    temporary = OUTPUT.with_suffix(OUTPUT.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, OUTPUT)

    if arguments.keep:
        print(f"  rebuild kept at {scratch}")
    else:
        for item in sorted(scratch.rglob("*"), reverse=True):
            item.unlink() if item.is_file() else item.rmdir()
        scratch.rmdir()

    print(f"  rebuilt {PUBLISHED.name} in {elapsed:.1f}s")
    print(f"  substantive differences: {len(substantive)}")
    print(f"  provenance hashes refreshed: {len(provenance)}")
    for row in substantive[:8]:
        print(f"    {row['path']}: {row['published']} -> {row['rebuilt']}")
    print(f"  reproduced: {payload['reproduced']}")
    print(f"  -> {OUTPUT.relative_to(ROOT)}")
    return 0 if payload["reproduced"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
