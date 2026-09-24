"""Bring the published record up to date, and say what would change before it does.

The portal states a refresh policy -- "monthly check; append complete months after
QA" -- and until now nothing implemented it. Twenty scripts existed and the order to
run them in lived in whoever last did it. That is the difference between data that
is updatable in principle and updatable in practice: a record nobody can refresh is
a snapshot with a publication date on it.

Three things it does:

    --check     what the store holds, what the source offers, what is missing.
                Reads and asks; writes nothing. Safe at any time, including while an
                extraction is running.

    --extend    fetch the missing months, then republish everything downstream.

    --publish   republish from what is already stored, without fetching.

The order below is not arbitrary and is the reason this file exists. Climatologies
are derived from the dated series, upstream figures from the local ones, and the
monthly record, the per-basin API and the coverage ledger from all of them. Running
them out of order publishes a basin API describing values the history does not have.

Nothing publishes after a failed fetch. A partial extraction is exactly the state
the store is built to record and refuse to present: its rows stay, its run is marked
incomplete, and the published record keeps saying what it could last vouch for.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import observations, query, variables
from ATLAS_MODULES.hydrosheds.functions import dated_monthly

STORE = ROOT / "PUBLISHED/data/atlas/observations"

# Snow is part of the dated record but arrives through its own extractor, because it
# dates a daily product rather than a monthly one: it decides day by day whether a
# cell carried snow and then averages the decisions. A refresh that covered only the
# monthly sources would leave it a year or more behind the variables it sits beside
# in the same record, which is the kind of ragged span that makes a water balance
# quietly wrong.
EXTRA_SOURCES = {
    "snow": {
        "script": "PIPELINES/extract_regional_snow.py",
        "asset": "MODIS/061/MYD10A1",
        "attributes": ["uzgeodata.dated.v1.snw_pc_s"],
    },
}


def sources():
    """Every dated source of the published record, however it is extracted."""
    found = {name: {"script": "PIPELINES/extract_regional_monthly.py", "positional": name,
                    "asset": spec["asset"],
                    "attributes": [band["attribute"] for band in spec["bands"].values()]}
             for name, spec in dated_monthly.SOURCES.items()}
    found.update({name: {**spec, "positional": None} for name, spec in EXTRA_SOURCES.items()})
    return found

# Everything that has to be rebuilt once a new month lands, in the only order that
# leaves the published files agreeing with each other. `span` marks the steps that
# take a year window: both default to 2003-2022, which was right when the record
# ended there and silently wrong the moment it did not. Extending the store without
# passing the new window produces climatologies and a monthly record that stop two
# years before the data does, and every published file then agrees with every other
# about a record that is out of date.
PUBLISH = [
    ("derive climatologies from the dated series",
     ["PIPELINES/derive_regional_substitutes.py"], True),
    ("accumulate the upstream figures", ["PIPELINES/accumulate_upstream_annuals.py"], False),
    ("republish the monthly record", ["PIPELINES/build_basin_history.py"], True),
    # The whole-catchment package is delta-encoded from the per-basin history and
    # records its digest, so a republished record leaves it both stale and no longer
    # matching the hashes it declares. It reads the published JSON rather than the
    # store, which is why it belongs here and not beside the extractors.
    ("rebuild the whole-catchment statistics",
     ["PIPELINES/build_catchment_statistics.py"], False),
    ("republish the per-basin API", ["PIPELINES/build_basin_api.py"], False),
    ("rebuild the coverage ledger", ["PIPELINES/build_regional_coverage.py"], False),
    ("refresh the store manifest", ["PIPELINES/stage_pilot_observations.py"], False),
    # The cube is rebuilt before the release is cut, because the release records the
    # digest of every file it names and a cube rebuilt afterwards would not match it.
    ("rebuild the query cube", ["PIPELINES/build_observation_cube.py"], False),
    # Last, and last for a reason. Cutting the release is what changes the answer to
    # "which data", so it happens only once every artefact above it is in place and
    # verified. A refresh that fails anywhere earlier leaves the previous release
    # current rather than promoting a partially rebuilt one.
    ("cut and promote the release", ["PIPELINES/publish_release.py"], False),
]


def stored_span(store=STORE):
    """The years the dated record actually covers, as the publishers want them.

    Taken from the store rather than from a constant, so the published window follows
    the data instead of the other way round. The first year is the earliest any dated
    variable holds and the last is the latest, which is the widest window every
    publisher can be asked for; a variable that stops earlier says so in its own
    coverage rather than shortening everyone else's.
    """
    extent = stored_extent(store)
    if not extent:
        return None
    first = min(int(entry["first"].split("-")[0]) for entry in extent.values())
    last = max(int(entry["last"].split("-")[0]) for entry in extent.values())
    return first, last


def store_status(store=STORE):
    """Whether the dated partitions are present at all.

    The store is deliberately not in Git -- Parquet does not delta-compress, so every
    re-extraction would add another full copy to a history that cannot expire it --
    which means a fresh clone holds the ledgers and none of the rows. --check is
    documented as safe at any time, and that has to include before the store has been
    restored: an absent store is a state to report, not a DuckDB traceback.
    """
    partitions = list(store.glob("time_kind=*/*/part.parquet"))
    return {"present": bool(partitions), "partitions": len(partitions),
            "path": str(store.relative_to(ROOT)).replace("\\", "/")}


def stored_extent(store=STORE):
    """The last month the store holds for each dated variable."""
    if not store_status(store)["present"]:
        return {}
    extent = {}
    for attribute, unit, support, first, last, basins, observed, missing in query.available(store, observed_span=True):
        if support != "s":
            continue
        if first is None or last is None:
            continue
        extent[attribute] = {
            "first": f"{first.year}-{first.month:02d}", "last": f"{last.year}-{last.month:02d}",
            "basins": basins, "observed": observed, "missing": missing,
        }
    return extent


def source_extent(only=None, project=None):
    """The last month each source actually offers, asked of the source itself.

    Without this a refresh is a guess: re-running for a year the provider has not
    published yet costs an hour and stores nothing. Earth Engine is optional here --
    a check that cannot reach it still reports what the store holds.
    """
    try:
        import ee
        from PIPELINES.extract_dated_snow import PROJECT
        ee.Initialize(project=project or PROJECT)
    except Exception as error:  # pragma: no cover - depends on credentials
        return {"unavailable": f"{type(error).__name__}: {str(error)[:120]}"}

    import ee
    found = {}
    known = sources()
    for name in (only or known):
        spec = known[name]
        try:
            collection = ee.ImageCollection(spec["asset"])
            latest = collection.aggregate_max("system:time_start").getInfo()
            found[name] = {
                "asset": spec["asset"],
                "latest": time.strftime("%Y-%m", time.gmtime(latest / 1000)) if latest else None,
            }
        except Exception as error:  # pragma: no cover - network dependent
            found[name] = {"asset": spec["asset"], "error": str(error)[:120]}
    return found


def missing_years(store=STORE, through=None):
    """Which years each source would have to be re-run for to reach `through`."""
    extent = stored_extent(store)
    wanted = int(through.split("-")[0]) if through else None
    plan = {}
    for name, spec in sources().items():
        attributes = spec["attributes"]
        held = [extent[a]["last"] for a in attributes if a in extent]
        if not held:
            plan[name] = {"stored_to": None, "note": "nothing stored for this source"}
            continue
        last = min(held)
        last_year = int(last.split("-")[0])
        target = wanted if wanted is not None else last_year
        plan[name] = {
            "stored_to": last,
            "years_to_fetch": list(range(last_year, target + 1)) if through and through > last else [],
        }
    return plan


def run(command, dry_run=False):
    printable = " ".join(command)
    if dry_run:
        print(f"    would run: {printable}", flush=True)
        return True
    started = time.perf_counter()
    result = subprocess.run([sys.executable, *command], cwd=ROOT)
    ok = result.returncode == 0
    print(f"    {'ok' if ok else 'FAILED'} in {time.perf_counter() - started:.0f}s: {printable}",
          flush=True)
    return ok


def publish(dry_run=False, span=None):
    """Rebuild every published file from what the store holds, in dependency order."""
    span = span or stored_span()
    window = f"{span[0]}-{span[1]}" if span else None
    if window:
        print(f"  publishing the record as {window}", flush=True)
    for label, command, takes_span in PUBLISH:
        print(f"  {label}", flush=True)
        full = list(command) + (["--years", window] if takes_span and window else [])
        if not run(full, dry_run):
            return {"ok": False, "failed_at": label}
    return {"ok": True, "published_span": window}


def extend(through, only=None, dry_run=False):
    """Fetch what is missing, and publish only if every fetch succeeded."""
    plan, known = missing_years(through=through), sources()
    fetched = []
    for name, entry in sorted(plan.items()):
        if only and name not in only:
            continue
        if entry.get("stored_to") is None:
            return {"ok": False, "failed_at": f"missing store for {name}",
                    "note": "Restore or bootstrap this source before extending; no publication attempted."}
        years = entry.get("years_to_fetch") or []
        if not years:
            print(f"  {name}: already stored to {entry.get('stored_to')}", flush=True)
            continue
        span = f"{years[0]}-{years[-1]}"
        spec = known[name]
        command = [spec["script"]]
        if spec.get("positional"):
            command.append(spec["positional"])
        command += ["--years", span, "--refresh-cache"]
        print(f"  {name}: fetching {span}", flush=True)
        if not run(command, dry_run):
            return {"ok": False, "failed_at": f"fetch {name}",
                    "note": "nothing was published; the store keeps what it could vouch for"}
        fetched.append({"source": name, "years": span})
    return {"ok": True, "fetched": fetched, **publish(dry_run)}


def check(through=None, probe=True):
    report = {"checked_at": observations._text(__import__("datetime").datetime.now().isoformat()),
              "store": store_status(),
              "stored": stored_extent(), "plan": missing_years(through=through)}
    if probe:
        report["source"] = source_extent()
    report["registry"] = {
        "variables": len(variables.VARIABLES),
        "unavailable": sorted(variables.UNAVAILABLE),
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true",
                        help="report what is stored, offered and missing; write nothing")
    action.add_argument("--extend", metavar="YYYY-MM",
                        help="fetch up to this month, then republish")
    action.add_argument("--publish", action="store_true",
                        help="republish from the store without fetching")
    parser.add_argument("--source", action="append", dest="only",
                        choices=sorted(sources()),
                        help="limit to one source; repeatable")
    parser.add_argument("--dry-run", action="store_true", help="print the commands, run nothing")
    parser.add_argument("--no-probe", action="store_true",
                        help="skip asking the sources what they offer")
    arguments = parser.parse_args()

    if arguments.check:
        print(json.dumps(check(probe=not arguments.no_probe), indent=2, ensure_ascii=False))
        return
    outcome = (publish(arguments.dry_run) if arguments.publish
               else extend(arguments.extend, arguments.only, arguments.dry_run))
    print(json.dumps(outcome, indent=2, ensure_ascii=False))
    if not outcome.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
