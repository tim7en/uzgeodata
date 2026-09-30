"""Record where each monthly series was extracted to, when a file does not say.

python PIPELINES/declare_extraction_ends.py [--dry-run]

Every series in a basin history file shares one span, so a source that stops earlier is
null for the rest of it. `extracted_through` tells the two kinds of null apart: before
it, a month without a value; after it, a month nobody has fetched yet. Series written
before that field existed (ERA5-Land runoff and temperature, MODIS snow) lack it, so
the Monthly tab counted months never fetched as missing - MODIS snow as "264 of 288
months" when it had simply not been extracted after 2024.

The end is taken from the data: the last month in which any basin has a value. That is
the extraction's own end, since every extraction covers all basins; a month that is
empty everywhere was not fetched. Series that already declare an end are left alone.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core.runtime import utc_now, write_json
from PIPELINES.build_basin_history import write_compact
from PIPELINES.update_published_record import HISTORY, extracted_length


def month_label(start, slot):
    return f"{start + slot // 12:04d}-{slot % 12 + 1:02d}"


def run(history=HISTORY, dry_run=False):
    index = json.loads((history / "index.json").read_text(encoding="utf-8"))
    start = index["years"][0]
    undeclared = [name for name, series in index["series"].items() if not series.get("extracted_through")]
    if not undeclared:
        return {"declared": {}, "files": 0}
    paths = sorted(p for p in history.glob("*.json") if p.name != "index.json")
    last = {name: -1 for name in undeclared}
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for name in undeclared:
            values = payload["series"].get(name, {}).get("values", [])
            for slot in range(len(values) - 1, last[name], -1):
                if values[slot] is not None:
                    last[name] = slot
                    break
    ends = {name: month_label(start, slot) for name, slot in last.items() if slot >= 0}
    if dry_run:
        return {"dry_run": True, "declared": ends, "files": len(paths)}
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for name, through in ends.items():
            series = payload["series"].get(name)
            if series is None or series.get("extracted_through"):
                continue
            series["extracted_through"] = through
            limit = extracted_length(series, payload["years"][0], len(series["values"]))
            series["observed_months"] = sum(1 for value in series["values"][:limit] if value is not None)
            series["missing_months"] = limit - series["observed_months"]
            changed = True
        if changed:
            write_compact(path, payload)
    for name, through in ends.items():
        index["series"][name]["extracted_through"] = through
    index["generated_at"] = utc_now()
    index.setdefault("appended", []).append({
        "at": utc_now(), "mode": "declared extraction ends for series written before extracted_through existed",
        "declared": ends})
    write_json(history / "index.json", index)
    return {"declared": ends, "files": len(paths)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    print(json.dumps(run(dry_run=parser.parse_args().dry_run), indent=2))


if __name__ == "__main__":
    main()
