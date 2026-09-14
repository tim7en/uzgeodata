"""Give each source back its account of the years it actually produced.

Every dated ledger was rewritten from scratch on each invocation, so the run that
extended the record to 2024 replaced six ledgers that covered 2003-2021. The
observations were never at risk -- their run ids still stand in run.csv, which is why
queries kept returning all twenty-two years and nothing failed loudly. What was lost
was the store's account of where most of its own record came from.

The runners no longer overwrite (see `merge_ledger`). This repairs what the overwrite
already did, and it repairs it from evidence rather than from memory: the store itself
records, for every row, the year it describes and the run that wrote it, so the missing
years can be counted rather than assumed. Each reconstructed year names the run that
actually produced it.

What a reconstructed entry deliberately does not carry is the original run's telemetry.
Wall seconds, batch timings and retry counts were only ever in the ledger that was
overwritten, and they are gone. Inventing plausible ones would make the repair
indistinguishable from the record it is standing in for, so every rebuilt year is
marked `reconstructed` and says what it was rebuilt from.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import query
from ATLAS_MODULES.core.runtime import utc_now, write_json
from PIPELINES.extract_regional_snow import is_complete

STORE = ROOT / "PUBLISHED/data/atlas/observations"

# A ledger names its source release differently depending on which runner wrote it, so
# the link back to the store is stated here rather than guessed from the file name.
RELEASE = {
    "regional-snow-ledger.json": "modis_myd10a1@061",
    "regional-terraclimate-ledger.json": "terraclimate@IDAHO_EPSCOR/TERRACLIMATE",
    "regional-terraclimate_temperature-ledger.json":
        "terraclimate_temperature@IDAHO_EPSCOR/TERRACLIMATE",
    "regional-era5_runoff-ledger.json": "era5_runoff@ECMWF/ERA5_LAND/MONTHLY_AGGR",
    "regional-era5_temperature-ledger.json": "era5_temperature@ECMWF/ERA5_LAND/MONTHLY_AGGR",
}


def measured(store=STORE, connection=None):
    """What the store can prove per release and year: rows, basins, nulls, and whose run.

    Read straight from the observations rather than from any ledger, because the
    ledgers are the thing being repaired and cannot be their own evidence.
    """
    own = connection is None
    connection = connection or query.connect(store)
    try:
        rows = connection.execute("""
            SELECT source_release_id, year, run_id,
                   count(*) AS rows,
                   count(DISTINCT basin_id) AS basins,
                   count(*) FILTER (WHERE value IS NULL) AS null_months,
                   count(*) FILTER (WHERE value IS NOT NULL) AS values,
                   count(DISTINCT attribute_id) AS bands
            FROM observations
            GROUP BY 1, 2, 3 ORDER BY 1, 2, 3""").fetchall()
    finally:
        if own:
            connection.close()

    found = {}
    for release, year, run_id, count, basins, nulls, values, bands in rows:
        # A year split across runs is recorded under the run that wrote most of it, and
        # the split is kept so the ambiguity is visible rather than resolved silently.
        entry = found.setdefault((release, int(year)), {
            "rows": 0, "basins": 0, "null_months": 0, "values": 0,
            "bands": bands, "contributors": {}})
        entry["rows"] += count
        entry["basins"] = max(entry["basins"], basins)
        entry["null_months"] += nulls
        entry["values"] += values
        entry["contributors"][run_id] = count
    return found


def availability(store, release, connection=None):
    """Rebuild the per-year null-month counts an overwritten ledger took with it.

    Filtered to the one release, because these year partitions now hold five sources
    and a count taken across all of them would attribute other sources' gaps to this
    one. The summer share and the size of the affected basins are what stop a change
    in what the sensor delivered from later being read as a change in the snow.
    """
    own = connection is None
    connection = connection or query.connect(store)
    try:
        rows = connection.execute("""
            SELECT year,
                   count(*) FILTER (WHERE value IS NULL) AS null_months,
                   count(DISTINCT basin_id) FILTER (WHERE value IS NULL) AS basins_affected,
                   median(expected_count) FILTER (WHERE value IS NULL) AS median_cells,
                   count(*) FILTER (WHERE value IS NULL AND expected_count > 100) AS over_100,
                   count(*) FILTER (WHERE value IS NULL AND month BETWEEN 6 AND 9) AS summer
            FROM observations WHERE source_release_id = ?
            GROUP BY 1 ORDER BY 1""", [release]).fetchall()
    finally:
        if own:
            connection.close()
    return {str(year): {
        "null_months": nulls, "basins_affected": affected,
        "median_affected_basin_cells": int(median) if median is not None else 0,
        "nulls_in_basins_over_100_cells": over,
        "summer_share": round(summer / nulls, 3) if nulls else 0.0,
        "reconstructed": True,
    } for year, nulls, affected, median, over, summer in rows}


def repair(path, evidence, expected_basins=7445):
    """Rebuild one ledger's missing years from the store's own rows."""
    ledger = json.loads(path.read_text(encoding="utf-8"))
    release = RELEASE[path.name]
    years = {year: entry for (found, year), entry in evidence.items() if found == release}
    if not years:
        return ledger, []

    by_year, rebuilt = dict(ledger.get("by_year", {})), []
    # Years the surviving ledger held predate years carrying their own run id, so they
    # have to be attributed from somewhere. Not from the ledger's top-level run_id:
    # that names whichever run wrote the file last, which after a merge is a run that
    # may never have touched those years -- attributing 2022 to the run that fetched
    # 2003-2009 would be a provenance claim that is simply false. The store records the
    # run behind every row, so the attribution comes from there or not at all.
    #
    # The check is against the store rather than merely filling a blank: a run id the
    # store cannot corroborate for that year is wrong, however confidently the ledger
    # states it, and an unverifiable attribution is worse than an absent one because it
    # reads as evidence. So each year's claim is confirmed against the runs that
    # actually wrote its rows, and replaced where it does not hold.
    for year, entry in by_year.items():
        contributors = years.get(int(year), {}).get("contributors") or {}
        if not contributors:
            continue
        if entry.get("run_id") in contributors:
            continue
        entry["run_id"] = max(contributors, key=contributors.get)
        entry["run_id_recovered_from_store"] = True
    for year in sorted(years):
        if str(year) in by_year:
            continue
        entry = years[year]
        owner = max(entry["contributors"], key=entry["contributors"].get)
        by_year[str(year)] = {
            "rows": entry["rows"], "basins": entry["basins"],
            "expected_basins": expected_basins,
            "complete": entry["basins"] == expected_basins,
            "values": entry["values"], "null_months": entry["null_months"],
            "run_id": owner,
            "reconstructed": True,
            "reconstructed_at": utc_now(),
            "reconstructed_from": "counted from the observation store, which records the "
                                  "run that wrote every row; the original run's timings "
                                  "were lost with the ledger it was overwritten in",
        }
        if len(entry["contributors"]) > 1:
            by_year[str(year)]["contributors"] = entry["contributors"]
        rebuilt.append(year)

    ledger["by_year"] = dict(sorted(by_year.items(), key=lambda item: int(item[0])))
    span = sorted(int(year) for year in ledger["by_year"])
    ledger["years"] = [span[0], span[-1]]
    ledger["stored_rows"] = sum(entry["rows"] for entry in ledger["by_year"].values())

    per_year = ledger["stored_rows"] // len(span) if span else 0
    ledger["expected_rows"] = expected_basins * 12 * len(span) * max(
        round(per_year / (expected_basins * 12)) if per_year else 1, 1)
    ledger["complete"] = is_complete(ledger)

    contributors = {}
    for year, entry in ledger["by_year"].items():
        contributors.setdefault(entry.get("run_id", ledger.get("run_id")), []).append(int(year))
    ledger["runs"] = [{"run_id": run, "years": sorted(covered)}
                      for run, covered in contributors.items() if run]
    if "availability" in ledger:
        rebuilt_availability = availability(STORE, release)
        kept = ledger["availability"].get("by_year", {})
        ledger["availability"]["by_year"] = dict(sorted(
            {**rebuilt_availability, **kept}.items(), key=lambda item: int(item[0])))

    ledger["span_note"] = ("Years accumulate across runs; each year names the run that "
                           "produced it. wall_seconds and retries describe the most recent "
                           "run only. Years marked reconstructed were counted back from the "
                           "observation store after an earlier ledger was overwritten.")
    return ledger, rebuilt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", default=str(STORE))
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would change without writing")
    arguments = parser.parse_args()
    store = Path(arguments.store)

    evidence = measured(store)
    report = []
    for name in sorted(RELEASE):
        path = store / name
        if not path.exists():
            report.append({"ledger": name, "skipped": "not present"})
            continue
        before = json.loads(path.read_text(encoding="utf-8"))
        ledger, rebuilt = repair(path, evidence)
        # Write on any difference, not only on a rebuilt year: rerunning after the
        # years were already restored still has the nested blocks to repair, and a
        # guard on `rebuilt` alone would quietly skip them.
        changed = ledger != before
        if not arguments.dry_run and changed:
            write_json(path, ledger)
        report.append({
            "ledger": name,
            "years_before": before.get("years"), "years_after": ledger.get("years"),
            "rows_before": before.get("stored_rows"), "rows_after": ledger.get("stored_rows"),
            "years_reconstructed": rebuilt,
            "changed": changed,
            "availability_years": len((ledger.get("availability") or {}).get("by_year", {})) or None,
            "complete": ledger.get("complete"),
        })
    print(json.dumps({"dry_run": arguments.dry_run, "ledgers": report},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
