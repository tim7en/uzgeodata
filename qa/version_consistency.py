"""Refuse to publish a dataset whose parts are on different versions.

python -m qa.version_consistency [--json]

The rule: no product changes version without the products derived from it changing
too, and without a new release being cut. Both inconsistencies found in the
2026-09 review broke it - the independent estimates stayed on TerraClimate v1.0 after
the monthly record moved to v1.1, and the cube was rebuilt without a release, so the
promoted release no longer described the served data. PIPELINES/publish_r2.mjs runs
this before uploading anything and stops if it fails.

Checks:
1. every family of independent estimates names the same source release as the
   monthly series it is derived from;
2. the catchment matrices name the same release as the monthly record they package;
3. the newest release cut matches the files it names (the promoted one may lag until
   the newest is verified on the site).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import releases

ATLAS = ROOT / "PUBLISHED/data/atlas"
# Estimate family (first three letters of the column) -> the monthly series it is derived from.
DERIVED_FROM = {
    "pre": "pre_mm_s", "aet": "aet_mm_s", "pet": "pet_mm_s", "cmi": "pre_mm_s", "ari": "pre_mm_s",
    "swc": "soil_mm_s", "run": "run_mm_s", "snw": "snw_pc_s", "tmp": "tmp_dc_s",
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def estimates_follow_record(catalogue, history):
    problems = []
    for family, series in DERIVED_FROM.items():
        record = history["series"].get(series, {}).get("source_release")
        found = {(m.get("substitute") or {}).get("source_release") for a, m in catalogue["meta"].items()
                 if a.startswith(family) and (m.get("substitute") or {}).get("source_release")}
        stale = sorted(r for r in found if r != record)
        if record and stale:
            problems.append(f"estimates {family}_*: {', '.join(stale)}, but the monthly {series} is {record}")
    return problems


def matrices_follow_record(catchments, history):
    problems = []
    for name, entry in catchments["series"].items():
        record = history["series"].get(name, {}).get("source_release")
        packaged = {p.get("source_release") for p in entry.get("provenance", [])}
        if record and packaged and packaged != {record}:
            problems.append(f"catchment matrix {name}: {', '.join(sorted(map(str, packaged)))}, but the monthly record is {record}")
    return problems


def release_matches_files():
    """The newest release cut must describe the files. The promoted one may lag behind it
    while the newest awaits verify_served_release.py - that is the publish sequence -
    but files that no release describes can never be published."""
    history = releases.history(ATLAS)
    if not history:
        return ["no release has been cut"]
    newest = history[0]["release_id"]
    return [f"release {newest}: {problem}" for problem in releases.check(ATLAS, newest)[:10]]


def run():
    catalogue, history = read(ATLAS / "catalogue.json"), read(ATLAS / "history/index.json")
    catchments = read(ATLAS / "catchments/index.json")
    checks = {
        "estimates_follow_record": estimates_follow_record(catalogue, history),
        "matrices_follow_record": matrices_follow_record(catchments, history),
        "release_matches_files": release_matches_files(),
    }
    return {"status": "PASS" if not any(checks.values()) else "FAIL", "checks": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true")
    result = run()
    if parser.parse_args().json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Version consistency: {result['status']}")
        for name, problems in result["checks"].items():
            print(f"  {name}: {'ok' if not problems else ''}")
            for problem in problems:
                print(f"    - {problem}")
    raise SystemExit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
