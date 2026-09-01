"""How current each stored relationship is, and what would refresh it.

An ontology that answers questions about the present has to know how old its own
answers are. A basin that reports "extremely hot" is making a claim about now; if
the table behind it stopped in 2023 the claim is false in a way nothing on the
page would reveal. This reads every registered relationship table and reports
what period it actually covers, how far that is behind what the source could
supply, and the one command that closes the gap.

Coverage is read from the table itself, through the dimensionColumns the graph
already declares — so a table that gains a year column becomes checkable without
this script learning anything about it.

    CURRENT     the table reaches the latest period the source can offer, for
                every unit it is supposed to cover
    BEHIND      the source has moved on; the refresh command would extend it
    INCOMPLETE  the periods are current but units are missing — a run that has
                not finished, which reads as up to date if you only look at dates
    ARCHIVAL    the upstream record has ended; the table is complete once it
                reaches that final period, and can never fall behind
    STATIC      no time dimension — it is current by construction
    MISSING     the container the graph names is not on this machine

    python PIPELINES/build_data_currency.py
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TABLES = ROOT / "ONTOLOGY" / "vocab" / "relationship-tables.json"
OUTPUT = ROOT / "PUBLISHED" / "data" / "data-currency.json"

# What each source can supply today, and how to go and get it. Latest is a
# statement about the upstream product, not about our copy — the difference
# between the two is the whole point of this file.
SOURCES = {
    "cfsv2-basin-monthly": {
        "cadence": "monthly", "latest": "cfsv2",
        "units": 263,
        "command": "npm run cfsv2:observe -- --start <YYYY-MM> --end <YYYY-MM>",
        "note": "CFSv2 publishes six-hourly with a short lag; a month is complete once it ends.",
    },
    "cfsv2-basin-anomaly": {
        "cadence": "monthly", "latest": "cfsv2", "units": 263,
        "command": "npm run cfsv2:anomaly",
        "note": "Derived. Rebuilds in seconds once observations and climatology are current.",
    },
    "cfsv2-basin-climatology": {
        "cadence": "static", "latest": None,
        "command": "npm run cfsv2:climatology",
        "note": "A baseline should move rarely and deliberately; every stored anomaly shifts when it does.",
    },
    "chirps-v3-basin-pentad": {
        "cadence": "monthly", "latest": "chirps", "units": 263,
        "command": "npm run chirps:observe -- --start <YYYY-MM> --end <YYYY-MM>",
        "note": "CHIRPS v3 publishes pentads with a few weeks' lag; six complete a month.",
    },
    "chirts-basin-monthly": {
        "cadence": "closed", "latest": "chirts", "units": 263,
        "command": "npm run chirts:observe -- --start <YYYY-MM> --end <YYYY-MM>",
        "note": "The upstream record ended at 2016-12. Complete once it reaches that, and never behind.",
    },
    "landcover-admin-year": {
        "cadence": "annual", "latest": "landcover", "units": 199,
        "command": "npm run landcover:stats -- --level admin",
        "note": "The land cover product publishes one mosaic per calendar year.",
    },
    "landcover-basin-year": {
        "cadence": "annual", "latest": "landcover", "units": 2736,
        "command": "npm run landcover:stats -- --level basin",
        "note": "Not yet built; roughly ten hours for level 12.",
    },
    "admin-basin-province": {"cadence": "static", "latest": None,
                             "command": "npm run hydrography:adminlinks",
                             "note": "Boundaries and basins change only when a delivery is replaced."},
    "admin-basin-district": {"cadence": "static", "latest": None,
                             "command": "npm run hydrography:adminlinks",
                             "note": "Boundaries and basins change only when a delivery is replaced."},
}

# Where the upstream products currently stand. Kept here rather than queried, so
# this runs without Earth Engine; the note says how to confirm it.
UPSTREAM = {
    "cfsv2": {"latest": "2026-08", "checked": "2026-09-01",
              "how": "ee.ImageCollection('NOAA/CFSV2/FOR6H_HARMONIZED') reduceColumns on system:time_start"},
    "chirts": {"latest": "2016-12", "checked": "2026-09-01", "closed": True,
               "how": "ee.ImageCollection('UCSB-CHG/CHIRTS/DAILY') — zero images after 2016-12-31"},
    "chirps": {"latest": "2026-07", "checked": "2026-09-01",
               "how": "ee.ImageCollection('UCSB-CHC/CHIRPS/V3/DAILY_SAT') reduceColumns on system:time_start"},
    "landcover": {"latest": "2025", "checked": "2026-09-01",
                  "how": "the Impact Observatory / Esri annual series, last complete mosaic"},
}


def survey(container: Path, dimensions: list[dict], object_column: str):
    """Period covered, row count and how many distinct units appear.

    The unit count is what separates a finished table from a running one. A job
    part way through has every recent year in it and looks current by date while
    most of the country is still missing.
    """
    names = [d["column"] for d in dimensions]
    if not container.exists():
        return None, None, 0, 0
    has_year, has_month = "year" in names, "month" in names
    stamps, units, rows = set(), set(), 0
    with container.open(encoding="utf8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows += 1
            if object_column in row:
                units.add(row[object_column])
            if has_year and row.get("year"):
                stamps.add(f"{int(row['year']):04d}-{int(row['month']):02d}"
                           if has_month else f"{int(row['year']):04d}")
    return (min(stamps) if stamps else None, max(stamps) if stamps else None, rows, len(units))


def main() -> None:
    registry = json.loads(TABLES.read_text(encoding="utf8"))["tables"]
    report = []
    for table in registry:
        container = ROOT / table["container"]
        source = SOURCES.get(table["id"], {})
        dimensions = table.get("dimensionColumns", [])
        first, last, rows, units = survey(container, dimensions, table["objectColumn"])
        expected_units = source.get("units")

        if not container.exists():
            status, behind = "MISSING", None
        elif source.get("cadence") == "closed":
            # A closed source cannot move on, so BEHIND would be a lie: the only
            # question is whether the table has reached the end of the record.
            expected = UPSTREAM.get(source["latest"], {}).get("latest")
            if expected and last and last < expected:
                status, behind = "INCOMPLETE", f"{last} → {expected} (record ends)"
            else:
                status, behind = "ARCHIVAL", None
        elif source.get("cadence") in (None, "static") or last is None:
            status, behind = "STATIC", None
        else:
            expected = UPSTREAM.get(source["latest"], {}).get("latest")
            behind = None
            if expected and last < expected:
                status, behind = "BEHIND", f"{last} → {expected}"
            elif expected_units and units < expected_units:
                status = "INCOMPLETE"
                behind = f"{units}/{expected_units} units"
            elif expected:
                status = "CURRENT"
            else:
                status = "STATIC"

        report.append({
            "id": table["id"], "label": table["label"], "predicate": table["predicate"],
            "container": table["container"], "exists": container.exists(),
            "rows": rows or None,
            "units": units or None, "expectedUnits": expected_units,
            "coverage": {"from": first, "to": last} if first else None,
            "cadence": source.get("cadence", "static"),
            "upstreamLatest": UPSTREAM.get(source.get("latest"), {}).get("latest"),
            "gap": behind,
            "status": status,
            "refresh": source.get("command"),
            "note": source.get("note"),
            "lastModified": (datetime.fromtimestamp(container.stat().st_mtime, timezone.utc)
                             .isoformat(timespec="seconds") if container.exists() else None),
        })

    order = {"BEHIND": 0, "INCOMPLETE": 1, "MISSING": 2, "CURRENT": 3, "ARCHIVAL": 4, "STATIC": 5}
    report.sort(key=lambda row: (order[row["status"]], row["id"]))

    counts: dict[str, int] = {}
    for row in report:
        counts[row["status"]] = counts.get(row["status"], 0) + 1

    OUTPUT.write_text(json.dumps({
        "version": "1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "statuses": {
            "CURRENT": "Reaches the latest period the source can supply, for every unit.",
            "BEHIND": "The source has moved on; the refresh command would extend it.",
            "INCOMPLETE": "Periods are current but units are missing — usually a run still going.",
            "ARCHIVAL": "The upstream record has ended; complete once it reaches that period.",
            "STATIC": "No time dimension, or a baseline held deliberately still.",
            "MISSING": "The container the graph names is not on this machine.",
        },
        "upstream": UPSTREAM,
        "counts": counts,
        "tables": report,
    }, ensure_ascii=False, indent=2), encoding="utf8")

    print(f"{'TABLE':30}{'STATUS':12}{'COVERAGE':20}{'UNITS':>12}{'ROWS':>9}")
    print("-" * 100)
    for row in report:
        coverage = (f"{row['coverage']['from']}..{row['coverage']['to']}"
                    if row["coverage"] else "—")
        units = (f"{row['units']}/{row['expectedUnits']}" if row["expectedUnits"]
                 else (str(row["units"]) if row["units"] else "—"))
        print(f"{row['id']:30}{row['status']:12}{coverage:20}{units:>12}{row['rows'] or 0:>9}")
    print("-" * 108)
    print("  " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    print(f"  -> {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
