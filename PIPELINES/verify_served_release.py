"""Check a release against what the site actually serves, then (optionally) promote it.

python PIPELINES/verify_served_release.py [RELEASE_ID] [--base URL] [--promote]

A release verified only against local files can still be promoted over served bytes
that differ - a failed upload, a stale cache, an object never written. This downloads
every file of the release from its content-addressed object path
(/data/atlas/objects/<sha256>) and checks its size and digest. Only when all of them
match does --promote move latest.json; publish again afterwards to serve the pointer.

The publish sequence:
  1. python PIPELINES/publish_release.py --no-promote     cut the release
  2. npm run publish:r2                                   gate, build, upload its objects
  3. python PIPELINES/verify_served_release.py --promote  check served bytes, promote
  4. npm run publish:r2                                   serve the new latest.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import releases

ATLAS = ROOT / "PUBLISHED/data/atlas"


def fetch_digest(url):
    """(bytes, sha256) of a served URL, streamed. curl uses the system certificate store,
    which some local Python installations lack."""
    digest, size = hashlib.sha256(), 0
    process = subprocess.Popen(["curl", "-sSfL", "--max-time", "900", url], stdout=subprocess.PIPE)
    for block in iter(lambda: process.stdout.read(1 << 20), b""):
        digest.update(block)
        size += len(block)
    if process.wait() != 0:
        return None, None
    return size, digest.hexdigest()


def verify(release_id, base):
    record = releases.read(ATLAS, release_id)
    if record.get("schema_version", 1) < 2:
        raise SystemExit(f"{record['release_id']} predates content-addressed objects; it cannot be checked this way.")
    problems = []
    for name, stated in record["files"].items():
        size, digest = fetch_digest(f"{base.rstrip('/')}/{stated['object']}")
        if digest is None:
            problems.append(f"{name}: {stated['object']} is not served")
        elif size != stated["bytes"] or digest != stated["sha256"]:
            problems.append(f"{name}: served {size} bytes / {digest[:12]}, release says {stated['bytes']} / {stated['sha256'][:12]}")
    return record, problems


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("release_id", nargs="?", help="default: the newest release cut")
    parser.add_argument("--base", default="https://uzgeodata.uz/data/atlas")
    parser.add_argument("--promote", action="store_true")
    arguments = parser.parse_args()
    release_id = arguments.release_id or releases.history(ATLAS)[0]["release_id"]
    record, problems = verify(release_id, arguments.base)
    result = {"release_id": release_id, "files": len(record["files"]), "served_and_matching": not problems,
              "problems": problems[:20]}
    if arguments.promote and not problems:
        releases.promote(ATLAS, release_id)
        result["promoted"] = True
    print(json.dumps(result, indent=2))
    raise SystemExit(1 if problems else 0)


if __name__ == "__main__":
    main()
