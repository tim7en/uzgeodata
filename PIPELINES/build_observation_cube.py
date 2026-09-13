"""Publish the analytical layer so something other than this machine can query it.

The store answers questions well and only here: it needs the repository and 442 MB
of partitions that exist on one disk. So the platform is the source of truth for its
own analyses in principle and not in practice, because nobody else -- a collaborator,
a notebook, the portal itself, an agent -- can ask it anything.

This publishes the narrow cube that fixes that: basin, variable, year, month, value,
and nothing else. One hundred megabytes rather than four hundred and forty, which is
what makes it fit beside a site that already spends most of its allowance. Hosts
serving byte ranges -- GitHub Pages does -- let a browser read only the row groups a
query touches, so a page can query twenty years of a variable without downloading the
file.

What the cube deliberately is not:

It is not the record. It carries no revisions, no run ids, no coverage counts and no
missing reasons, so a value in it cannot be defended, only used. Every file names the
release it was cut from, and that release is what a citation should point at. A fast
read path and a citable record are different things and conflating them is how a
number outlives the evidence for it.

It is not a substitute for the refusal rules either. A null here still means no
observation, never zero -- the one property too important to trade for size.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import query, variables
from ATLAS_MODULES.core.runtime import utc_now, write_json

STORE = ROOT / "PUBLISHED/data/atlas/observations"
OUT = ROOT / "PUBLISHED/data/atlas/cube"


def build(store=STORE, out=OUT, geometry="reg-"):
    import duckdb

    out.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    connection = query.connect(store, geometry=geometry)

    # One file per variable, not one file for everything. A single cube was both too
    # large to host - 103 MB against a 100 MB ceiling - and the wrong shape: almost
    # every question names its variables, so partitioning by variable lets a reader
    # open the one file that answers rather than seeking through all of them. Adding
    # a tenth variable then adds a file instead of growing one past the limit again.
    #
    # Sorted within each file by basin then date, so a query for one basin's series
    # reads a contiguous run of row groups.
    for path in out.glob("variable=*/*.parquet"):
        path.unlink()
    connection.execute(f"""
        COPY (SELECT basin_id,
                     regexp_extract(attribute_id, '([^.]+)$', 1) AS variable,
                     attribute_id, year, month, value, unit
              FROM observations
              ORDER BY variable, basin_id, year, month)
        TO '{out.as_posix()}'
        (FORMAT PARQUET, PARTITION_BY (variable), COMPRESSION zstd,
         ROW_GROUP_SIZE 100000, OVERWRITE_OR_IGNORE)
    """)
    files = sorted(out.glob("variable=*/*.parquet"))
    rows, basins, first, last = connection.execute(f"""
        SELECT count(*), count(DISTINCT basin_id), min(month_start), max(month_start)
        FROM observations
    """).fetchone()

    # The registry travels inside this file, so a reader with no access to the store
    # takes its word for what each variable covers. A declaration that has drifted from
    # the data is worse than none: it is wrong with authority, and nothing downstream
    # can tell. So the two are compared here and a mismatch stops the publish.
    #
    # This is not hypothetical. The declared span sat at 2003-2022 for two years after
    # the record reached 2024, and ERA5 mean temperature was declared from 2003 when it
    # begins in 2010.
    measured = dict(connection.execute("""
        SELECT attribute_id, [min(year), max(year)] FROM observations GROUP BY 1
    """).fetchall())
    connection.close()

    drifted = []
    for identifier, entry in variables.VARIABLES.items():
        actual = measured.get(entry["attribute"])
        if actual is None:
            drifted.append(f"{identifier} declares coverage but {entry['attribute']} "
                           f"is not in the cube")
        elif list(actual) != list(entry["coverage"]):
            drifted.append(f"{identifier} declares {entry['coverage']} "
                           f"but the cube holds {list(actual)}")
    if drifted:
        raise SystemExit("the registry disagrees with the data it describes:\n  "
                         + "\n  ".join(drifted))

    release = json.loads((store / "manifest.json").read_text(encoding="utf-8"))
    summary = {
        "generated_at": utc_now(),
        "rows": rows, "basins": basins,
        "months": [f"{first.year}-{first.month:02d}", f"{last.year}-{last.month:02d}"],
        "bytes": sum(path.stat().st_size for path in files),
        "base": "/data/atlas/cube/",
        "files": {path.parent.name.split("=")[1]:
                  {"path": f"/data/atlas/cube/{path.parent.name}/{path.name}",
                   "bytes": path.stat().st_size} for path in files},
        "query": "read_parquet('/data/atlas/cube/variable=*/*.parquet', hive_partitioning = true) "
                 "reads them all; naming one variable's directory reads only that file.",
        "release": {
            "store_rows": release.get("rows"),
            "generated_from_run": release.get("generated_from_run"),
            "contract": release.get("contract"),
        },
        "columns": {
            "basin_id": "HYBAS level-12 identifier, a string because it is an identifier",
            "variable": "the store's attribute id; resolve a concept through the registry",
            "year": "calendar year", "month": "calendar month, 1-12",
            "value": "null where there was no observation, never zero",
            "unit": "the physical unit of the value, as measured",
        },
        "registry": variables.registry(),
        "reading": {
            "scope": "Local basin support only. Upstream values accumulate everything draining "
                     "through a basin and cannot be summed across basins, so they are not here: "
                     "a cube inviting that sum would be a trap.",
            "evidence": "This is a read path, not the record. It carries no revisions, run ids, "
                        "coverage counts or missing reasons. Cite the store release named above, "
                        "not this file.",
            "nulls": "A null is a month with no observation. It is never a zero, and nothing "
                     "downstream may coalesce it into one.",
            "query": "Readable in place by anything that speaks Parquet. Over a host serving "
                     "byte ranges, a browser can query it without downloading it.",
        },
    }
    write_json(out / "index.json", summary)
    summary["wall_seconds"] = round(time.perf_counter() - started, 1)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(OUT))
    arguments = parser.parse_args()
    report = build(out=Path(arguments.out))
    print(json.dumps({k: v for k, v in report.items() if k != "registry"}, indent=2,
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
