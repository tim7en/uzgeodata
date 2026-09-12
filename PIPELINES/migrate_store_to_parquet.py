"""Rewrite the observation store from partitioned CSV to partitioned Parquet.

python PIPELINES/migrate_store_to_parquet.py [--dry-run]

The contract does not change and neither does a single value. What changes is the
bytes underneath: the same 17.9 million observations occupy 7.79 GB as CSV and about
0.44 GB as Parquet, a partition is read an order of magnitude faster, and a question
that spans every basin becomes answerable at all.

Every partition is read through the store's own reader and written through its own
writer, so anything the contract would refuse is refused here too. Each one is then
read back and compared record for record against what went in, and the CSV is only
removed once that comparison has passed. A partition that disagrees is left exactly
as it was found.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import observations

STORE = ROOT / "PUBLISHED/data/atlas/observations"


def comparable(record):
    """A record reduced to what the contract says it is, for comparison across
    formats. CSV carries every field as text and Parquet carries it typed, so the
    two are compared after both have been decoded, not as they sit on disk."""
    return tuple(record[field] for field in observations.FIELDS)


def migrate(store=STORE, dry_run=False):
    store = Path(store)
    report = {"partitions": [], "csv_bytes": 0, "parquet_bytes": 0, "rows": 0, "failed": []}
    started = time.perf_counter()

    for source in sorted(store.glob("**/part.csv")):
        target = source.with_name("part.parquet")
        relative = str(source.parent.relative_to(store))
        if target.exists():
            print(f"  {relative:<34} already Parquet, skipped", flush=True)
            continue

        rows = observations.read_partitions(source.parent)
        csv_bytes = source.stat().st_size
        if dry_run:
            print(f"  {relative:<34} {len(rows):>9,} rows, {csv_bytes/1e6:>7.1f} MB")
            report["rows"] += len(rows)
            report["csv_bytes"] += csv_bytes
            continue

        # The writer removes the CSV it replaces, which would leave a failed
        # comparison with nothing to fall back to. Held aside first, and only
        # discarded once the Parquet has been read back and agreed with.
        kept = source.with_suffix(".csv.pre-parquet")
        source.replace(kept)
        observations.write_partitions(store, rows)
        if not target.exists():
            kept.replace(source)
            report["failed"].append({"partition": relative, "reason": "no parquet written"})
            break

        back = observations.read_partitions(source.parent)
        if len(back) != len(rows) or sorted(map(comparable, back)) != sorted(map(comparable, rows)):
            target.unlink()
            kept.replace(source)
            report["failed"].append({"partition": relative, "reason": "round trip differs",
                                     "before": len(rows), "after": len(back)})
            print(f"  {relative:<34} MISMATCH - restored the CSV and stopped", flush=True)
            break
        kept.unlink()

        parquet_bytes = target.stat().st_size
        report["partitions"].append({"partition": relative, "rows": len(rows),
                                     "csv_bytes": csv_bytes, "parquet_bytes": parquet_bytes})
        report["rows"] += len(rows)
        report["csv_bytes"] += csv_bytes
        report["parquet_bytes"] += parquet_bytes
        print(f"  {relative:<34} {len(rows):>9,} rows  {csv_bytes/1e6:>7.1f} MB -> "
              f"{parquet_bytes/1e6:>6.1f} MB", flush=True)

    report["wall_seconds"] = round(time.perf_counter() - started, 1)
    if report["parquet_bytes"]:
        report["ratio"] = round(report["csv_bytes"] / report["parquet_bytes"], 1)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be converted without writing anything")
    arguments = parser.parse_args()
    report = migrate(dry_run=arguments.dry_run)
    print(json.dumps({k: v for k, v in report.items() if k != "partitions"}, indent=2))
    if report["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
