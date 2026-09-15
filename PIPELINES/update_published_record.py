"""Extend the published monthly record when the full observation store is not on this machine.

python PIPELINES/update_published_record.py terraclimate --through 2026-08 [--dry-run]

A temporary path. The proper refresh (refresh_regional_record.py --extend) appends to
the observation store and republishes everything from it, but the store's bulk
partitions are not in Git, so a fresh checkout cannot run it. What Git does carry is
the published read path: the per-basin history files the site draws from and the
query cube. This extends those two directly:

  1. The last month each variable of the source holds is read from the cube. A
     variable the cube has never held starts at the first month of the record.
  2. Only the months after it are extracted, with the regional extractor unchanged,
     into a scratch store under WORKSPACE/ so the run keeps its own ledger.
  3. Those months are appended to history/ and cube/. Nothing earlier is rewritten.

What it does not do: rebuild climatologies, the basin API, the coverage ledger or
cut a release. Those are derived from the whole store and stay as last published;
each updated index says so under "appended". When the store is restored, the full
refresh supersedes this.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import query, variables
from ATLAS_MODULES.core.runtime import utc_now, write_json
from PIPELINES.build_basin_history import labelled, write_compact
from PIPELINES.refresh_regional_record import sources

CUBE = ROOT / "PUBLISHED/data/atlas/cube"
HISTORY = ROOT / "PUBLISHED/data/atlas/history"
SCRATCH = ROOT / "WORKSPACE/data-updates/stores"
EXPECTED_GEOMETRY = "reg-166479294ef8"
MODE = "appended from Git's published record; observation store not present"


def short(attribute):
    return attribute.rsplit(".", 1)[-1]


def month_index(stamp):
    year, month = (int(part) for part in stamp.split("-"))
    return year * 12 + month - 1


def month_stamp(index):
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def published_through(attributes, cube=CUBE):
    """The last observed month the cube holds for every one of these attributes.

    None when any of them has never been published: a newly registered variable has
    to be fetched from the start of the record, and the source travels as one pass.
    """
    import duckdb
    last = []
    for attribute in attributes:
        path = cube / f"variable={short(attribute)}" / "data_0.parquet"
        if not path.exists():
            return None
        year, month = duckdb.sql(f"""
            SELECT year, month FROM read_parquet('{path.as_posix()}')
            WHERE value IS NOT NULL ORDER BY year DESC, month DESC LIMIT 1""").fetchone()
        last.append(f"{year:04d}-{month:02d}")
    return min(last)


def extract(source, years, store):
    """Run the regional extractor for these years into its own store."""
    if source == "snow":
        from PIPELINES import extract_regional_snow
        ledger = extract_regional_snow.run(years=years, store=store, refresh_cache=True)
    else:
        from PIPELINES import extract_regional_monthly
        ledger = extract_regional_monthly.run(source, years=years, store=store, refresh_cache=True)
    if ledger.get("geometry_version") != EXPECTED_GEOMETRY:
        raise RuntimeError(f"Basin geometry {ledger.get('geometry_version')} does not match the "
                           f"published record ({EXPECTED_GEOMETRY}). Nothing was published.")
    if not ledger.get("complete"):
        raise RuntimeError(f"The {source} extraction did not complete "
                           f"({len(ledger.get('failures', []))} failed batches). Nothing was published.")
    return ledger


def extracted_rows(store, attributes, first, through):
    """The fetched months, one current value per basin, attribute and month."""
    connection = query.connect(store)
    try:
        marks = ", ".join("?" for _ in attributes)
        return connection.execute(f"""
            SELECT basin_id, attribute_id, year, month, value, unit, run_id, recipe_version
            FROM observations
            WHERE spatial_support = 's' AND attribute_id IN ({marks})
              AND month_start BETWEEN ? AND ?
            ORDER BY attribute_id, basin_id, year, month""",
            [*attributes, f"{first}-01", f"{through}-01"]).fetchall()
    finally:
        connection.close()


def count_rows(store, attribute, first, through):
    connection = query.connect(store)
    try:
        return connection.execute("""
            SELECT count(*) FROM observations
            WHERE spatial_support = 's' AND attribute_id = ? AND month_start BETWEEN ? AND ?""",
            [attribute, f"{first}-01", f"{through}-01"]).fetchone()[0]
    finally:
        connection.close()


def check_complete(rows, attributes, basins, first, through):
    months = month_index(through) - month_index(first) + 1
    expected = len(attributes) * basins * months
    if len(rows) != expected:
        raise RuntimeError(f"Expected {expected:,} values ({basins} basins x {months} months x "
                           f"{len(attributes)} variables) but the extraction holds {len(rows):,}. "
                           "Nothing was published.")


def series_meta(attribute, rows):
    """What a series newly added to the history says about itself, as the builder writes it."""
    meta = dict(labelled().get(attribute) or {"label": short(attribute), "unit": rows[0][5] if rows else None})
    if "source" in meta and "asset" in meta:
        meta["source_release"] = f"{meta['source']}@{meta['asset']}"
    meta.update({"statistic": "monthly_mean", "geometry_version": EXPECTED_GEOMETRY})
    return meta


def update_history(rows, attributes, first, through, note, history=HISTORY):
    """Append the fetched months to every basin file, widening the span if needed.

    Every series in a file shares one span, so extending one source leaves the others
    null past their own end. Each series therefore records `extracted_through`: a null
    after that month is a month nobody has fetched yet, not a month without data.

    A variable no file holds yet is added to each, null before `first`.
    """
    index = json.loads((history / "index.json").read_text(encoding="utf-8"))
    start = index["years"][0]
    previous_end = index["years"][1]
    end = max(previous_end, int(through.split("-")[0]))
    width = (end - start + 1) * 12
    names = {short(attribute) for attribute in attributes}
    first_slot = month_index(first) - start * 12
    last_slot = month_index(through) - start * 12

    by_basin = {}
    runs, methods = set(), set()
    for basin, attribute, year, month, value, _unit, run_id, recipe in rows:
        slots = by_basin.setdefault(basin, {}).setdefault(short(attribute), {})
        slots[(year - start) * 12 + month - 1] = None if value is None or math.isnan(value) else round(value, 4)
        runs.add(run_id)
        methods.add(recipe)

    metas = {short(attribute): series_meta(attribute, rows[:1]) for attribute in attributes}
    updated = 0
    for basin, fetched in by_basin.items():
        path = history / f"{basin}.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for name in sorted(names - set(payload["series"])):
            payload["series"][name] = {**metas[name], "values": [None] * payload["months"]}
        payload["series"] = dict(sorted(payload["series"].items()))
        for name, series in payload["series"].items():
            values = series["values"]
            if len(values) < width:
                if name not in names and "extracted_through" not in series:
                    series["extracted_through"] = f"{payload['years'][1]:04d}-12"
                values.extend([None] * (width - len(values)))
            if name in fetched:
                for slot in range(first_slot, width):
                    values[slot] = fetched[name].get(slot) if slot <= last_slot else None
                series["extracted_through"] = through
                series["run_ids"] = sorted(set(series.get("run_ids", [])) | runs)
                series["methods"] = sorted(set(series.get("methods", [])) | methods)
            limit = extracted_length(series, start, len(values))
            observed = sum(1 for value in values[:limit] if value is not None)
            series["observed_months"] = observed
            series["missing_months"] = limit - observed
        payload["years"] = [start, end]
        payload["months"] = width
        write_compact(path, payload)
        index["observed_months"].setdefault(basin, {}).update(
            {name: series["observed_months"] for name, series in payload["series"].items()})
        updated += 1

    for name in names - set(index["series"]):
        index["series"][name] = dict(metas[name])
    index["series"] = dict(sorted(index["series"].items()))
    for name, series in index["series"].items():
        if name in names:
            series["extracted_through"] = through
            series["run_ids"] = sorted(set(series.get("run_ids", [])) | runs)
            series["methods"] = sorted(set(series.get("methods", [])) | methods)
        elif end > previous_end and "extracted_through" not in series:
            series["extracted_through"] = f"{previous_end:04d}-12"
    index["years"] = [start, end]
    index["months"] = width
    index["generated_at"] = utc_now()
    appended = index.setdefault("appended", [])
    if not appended or appended[-1] != note:
        appended.append(note)
    write_json(history / "index.json", index)
    return updated


def extracted_length(series, start, length):
    through = series.get("extracted_through")
    if not through:
        return length
    return min(length, month_index(through) - start * 12 + 1)


def update_cube(rows, attributes, first, note, cube=CUBE):
    """Replace each variable file with its earlier months plus the fetched ones."""
    write_cube(rows, attributes, first, cube)
    return index_cube(note, cube)


def write_cube(rows, attributes, first, cube=CUBE):
    """The variable files only. The index is rebuilt separately, once every file is in place."""
    import duckdb
    import pyarrow as pa
    table = pa.table({
        "basin_id": [row[0] for row in rows], "attribute_id": [row[1] for row in rows],
        "year": pa.array([row[2] for row in rows], pa.int64()),
        "month": pa.array([row[3] for row in rows], pa.int64()),
        "value": pa.array([None if row[4] is None or math.isnan(row[4]) else row[4] for row in rows],
                          pa.float64()),
        "unit": [row[5] for row in rows]})
    connection = duckdb.connect()
    connection.register("fetched", table)
    cutoff = month_index(first)
    staged = []
    for attribute in attributes:
        path = cube / f"variable={short(attribute)}" / "data_0.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name("data_0.parquet.tmp")
        # A variable published for the first time has no earlier months to keep.
        earlier = f"""
                    SELECT basin_id, attribute_id, year, month, value, unit
                    FROM read_parquet('{path.as_posix()}', hive_partitioning = false)
                    WHERE year * 12 + month - 1 < {cutoff}
                    UNION ALL""" if path.exists() else ""
        connection.execute(f"""
            COPY (
                SELECT basin_id, attribute_id, year, month, value, unit FROM ({earlier}
                    SELECT basin_id, attribute_id, year, month, value, unit
                    FROM fetched WHERE attribute_id = '{attribute}')
                ORDER BY basin_id, year, month)
            TO '{temporary.as_posix()}' (FORMAT PARQUET, COMPRESSION zstd, ROW_GROUP_SIZE 100000)""")
        staged.append((temporary, path))
    for temporary, path in staged:
        temporary.replace(path)
    connection.close()


def index_cube(note, cube=CUBE):
    """Describe the cube as it now stands. The registry refuses a cube missing a variable."""
    import duckdb
    connection = duckdb.connect()
    files = sorted(cube.glob("variable=*/*.parquet"))
    pattern = (cube / "variable=*" / "*.parquet").as_posix()
    rows_total, basins, first_month, last_month = connection.execute(f"""
        SELECT count(*), count(DISTINCT basin_id), min(year * 12 + month - 1), max(year * 12 + month - 1)
        FROM read_parquet('{pattern}', hive_partitioning = false)""").fetchone()
    measured = dict(connection.execute(f"""
        SELECT attribute_id, [min(year), max(year)]
        FROM read_parquet('{pattern}', hive_partitioning = false) GROUP BY 1""").fetchall())
    observed_through = {attribute: month_stamp(last) if last is not None else None
                        for attribute, last in connection.execute(f"""
        SELECT attribute_id, max(year * 12 + month - 1) FILTER (WHERE value IS NOT NULL)
        FROM read_parquet('{pattern}', hive_partitioning = false) GROUP BY 1""").fetchall()}
    connection.close()

    summary = json.loads((cube / "index.json").read_text(encoding="utf-8"))
    summary.update({
        "generated_at": utc_now(), "rows": rows_total, "basins": basins,
        "months": [month_stamp(first_month), month_stamp(last_month)],
        "bytes": sum(path.stat().st_size for path in files),
        "files": {path.parent.name.split("=")[1]:
                  {"path": f"/data/atlas/cube/{path.parent.name}/{path.name}",
                   "bytes": path.stat().st_size} for path in files},
        "registry": variables.registry(coverage=measured, observed_through=observed_through),
    })
    appended = summary.setdefault("appended", [])
    if not appended or appended[-1] != note:
        appended.append(note)
    write_json(cube / "index.json", summary)
    return rows_total


def update(source, through, dry_run=False, cube=CUBE, history=HISTORY):
    known = sources()
    if source not in known:
        raise ValueError(f"Unknown source {source}")
    attributes = known[source]["attributes"]
    stored = published_through(attributes, cube)
    if stored is None:
        start = json.loads((history / "index.json").read_text(encoding="utf-8"))["years"][0]
        first = f"{start:04d}-01"
    else:
        first = month_stamp(month_index(stored) + 1)
    if month_index(first) > month_index(through):
        print(f"{source}: published through {stored}; nothing newer than {through} to fetch", flush=True)
        return {"ok": True, "source": source, "published_through": stored, "fetched": None}
    years = (int(first.split("-")[0]), int(through.split("-")[0]))
    print(f"{source}: published through {stored or 'never'}; fetching {first} to {through}", flush=True)
    if dry_run:
        return {"ok": True, "source": source, "published_through": stored,
                "would_fetch": [first, through]}

    started = time.perf_counter()
    store = SCRATCH / f"{source}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    store.mkdir(parents=True, exist_ok=True)
    ledger = extract(source, years, store)
    # Check every variable before publishing any, so a short one leaves nothing half-written.
    months = month_index(through) - month_index(first) + 1
    for attribute in attributes:
        held = count_rows(store, attribute, first, through)
        if held != ledger["basins"] * months:
            raise RuntimeError(f"Expected {ledger['basins'] * months:,} values for {short(attribute)} "
                               f"({ledger['basins']} basins x {months} months) but the extraction holds "
                               f"{held:,}. Nothing was published.")

    note = {"at": utc_now(), "source": source, "months": [first, through],
            "run_id": ledger["run_id"], "mode": MODE,
            "scratch_store": store.relative_to(ROOT).as_posix() if store.is_relative_to(ROOT) else str(store),
            "not_rebuilt": ["climatologies", "basin API", "coverage ledger", "release"]}
    # One variable at a time: a full record for a new source is millions of rows, and
    # holding every variable's at once costs gigabytes for no gain.
    values = basins = 0
    for attribute in attributes:
        rows = extracted_rows(store, [attribute], first, through)
        check_complete(rows, [attribute], ledger["basins"], first, through)
        basins = update_history(rows, [attribute], first, through, note, history)
        write_cube(rows, [attribute], first, cube)
        values += len(rows)
        print(f"{short(attribute)}: {len(rows):,} values published", flush=True)
    cube_rows = index_cube(note, cube)
    return {"ok": True, "source": source, "fetched": [first, through], "values": values,
            "history_basins": basins, "cube_rows": cube_rows,
            "wall_seconds": round(time.perf_counter() - started)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", choices=sorted(sources()))
    parser.add_argument("--through", required=True, help="Last complete month to fetch, YYYY-MM")
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()
    print(json.dumps(update(arguments.source, arguments.through, arguments.dry_run), indent=2), flush=True)


if __name__ == "__main__":
    main()
