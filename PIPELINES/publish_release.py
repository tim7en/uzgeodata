"""Cut a release over what is published, and promote it only once it verifies.

This is the last step of an update and the only one that changes what a reader gets
by default. Everything before it writes artefacts; this fixes an identity over them.

The order matters and is the point. The record is written first and names every file
with its digest. Only then is it verified, and only then does the pointer move. A run
interrupted at any point before the final write leaves the previous release current,
so a reader never resolves to a half-built dataset. A run interrupted after it has
published a complete one.

What is deliberately not here: copying. A release points at the artefacts already
published rather than duplicating them, so cutting one costs a manifest. The cost of
that choice is that the paths can be rebuilt underneath an old release -- which is
exactly why the digests are recorded, so a mismatch is detectable rather than silent.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import releases, variables

PUBLISHED = ROOT / "PUBLISHED/data/atlas"
STORE = PUBLISHED / "observations"

# What a release covers: the fast read path and the metadata needed to interpret it.
# Not the observation store itself -- those partitions are not distributed in a Git
# checkout, and naming files a consumer cannot fetch would make every release fail its
# own verification.
def artefacts(published=PUBLISHED):
    found = sorted(published.glob("cube/variable=*/*.parquet"))
    for name in ("cube/index.json", "catalogue.json", "regional-coverage.json",
                 "analysis-layers.md", "observations/manifest.json"):
        path = published / name
        if path.is_file():
            found.append(path)
    for path in sorted(published.glob("observations/*-ledger.json")):
        found.append(path)
    return found


def commit_id():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return None


def cube_facts(published=PUBLISHED):
    path = published / "cube/index.json"
    if not path.is_file():
        return None, None
    index = json.loads(path.read_text(encoding="utf-8"))
    return index.get("rows"), index.get("months")


def publish(published=PUBLISHED, notes=None, promote=True):
    files = artefacts(published)
    if not files:
        raise SystemExit("nothing to release: no cube has been built")

    previous = None
    try:
        previous = releases.read(published)["release_id"]
    except releases.ReleaseError:
        pass  # the first release supersedes nothing

    rows, span = cube_facts(published)
    cube = json.loads((published / "cube/index.json").read_text(encoding="utf-8"))
    record = releases.cut(published, files, base=published, commit=commit_id(),
                          span=span, rows=rows, registry=cube.get("registry") or variables.registry(),
                          supersedes=previous, notes=notes)

    problems = releases.check(published, record["release_id"])
    if problems:
        raise SystemExit("the release does not verify against its own manifest:\n  "
                         + "\n  ".join(problems[:5]))
    if promote:
        releases.promote(published, record["release_id"])
    return {
        "release_id": record["release_id"],
        "promoted": promote,
        "supersedes": previous,
        "files": len(record["files"]),
        "bytes": sum(entry["bytes"] for entry in record["files"].values()),
        "rows": rows, "span": span,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notes", help="what changed in this release")
    parser.add_argument("--no-promote", action="store_true",
                        help="cut and verify without making it the default release")
    parser.add_argument("--verify", metavar="RELEASE_ID", nargs="?", const="",
                        help="check an existing release against what is on disk")
    parser.add_argument("--list", action="store_true", help="every release, newest first")
    arguments = parser.parse_args()

    if arguments.list:
        for record in releases.history(PUBLISHED):
            print(f"{record['release_id']}  rows={record.get('rows')}  "
                  f"span={record.get('span')}  files={len(record['files'])}")
        return
    if arguments.verify is not None:
        problems = releases.check(PUBLISHED, arguments.verify or None)
        print(json.dumps({"verified": not problems, "problems": problems}, indent=2))
        raise SystemExit(1 if problems else 0)

    print(json.dumps(publish(notes=arguments.notes, promote=not arguments.no_promote),
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
