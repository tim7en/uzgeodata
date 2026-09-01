"""Check every registered table against the conventions the ontology has settled on.

Each convention here exists because breaking it cost something real:

    declared columns exist   The graph said cfsv2-basin-climatology carried a
                             unit column and it did not, so anything reading a
                             baseline's units got nothing.
    encoding                 Three delivery CSVs carry a byte-order mark their
                             siblings do not, which turns the first column name
                             into \\ufefflevel and makes a lookup raise KeyError.
    units on measurements    CFSv2 potential evaporation was read as a mass flux
                             when it is W/m2, giving values in the tens of
                             millions before anybody noticed.
    a quality column         CHIRPS marks gaps with a negative sentinel and CFSv2
                             published a twelvefold scaling fault for 2026. A
                             table with nowhere to say "this value is wrong" has
                             to either drop the row or lie.
    grain matches the grid   A basin smaller than the pixel it samples inherits
                             its neighbour's value. Level 12 against a 34.8 km
                             grid is nine and a half basins sharing one number.

Advisory, not fatal: a delivery's own tables are not ours to reshape, and a
derived table can inherit a filter rather than repeat a column. The point is that
nothing is out of line by accident.

    python PIPELINES/audit_ontology_tables.py
"""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TABLES = ROOT / "ONTOLOGY" / "vocab" / "relationship-tables.json"
STRUCTURE = ROOT / "PUBLISHED" / "data" / "ontology" / "INDEX.json"

# Source grid in metres for the tables built from a raster, so grain can be judged.
GRIDS = {
    "cfsv2-basin-monthly": 34771, "cfsv2-basin-climatology": 34771,
    "cfsv2-basin-anomaly": 34771,
    "chirps-v3-basin-pentad": 5566, "chirts-basin-monthly": 5566,
    "landcover-basin-year": 10, "landcover-admin-year": 10,
    "cpc-basin-monthly": 55660,
    "ghm-basin-modification": 1000, "ghm-district-modification": 1000,
}
# Which unit table a basin id belongs to, and its mean area in km2.
LEVEL_AREA = {}


def basin_areas() -> dict[int, float]:
    """Mean sub-basin area per level, to judge grain against a grid."""
    package = ROOT / "GEODATA" / "uzbekistan_basinatlas_v10" / "uzbekistan_basinatlas_v10.gpkg"
    if not package.exists():
        return {}
    areas = {}
    with sqlite3.connect(f"file:{package}?mode=ro", uri=True) as connection:
        for level in range(1, 13):
            try:
                areas[level] = connection.execute(
                    f"SELECT avg(SUB_AREA) FROM basinatlas_uz_lev{level:02d}").fetchone()[0]
            except sqlite3.Error:
                pass
    return areas


def level_of(table: dict, sample_ids: set[str]) -> int | None:
    """Infer the basin level a table is keyed at, from how many distinct ids it holds."""
    if table["objectType"] != "Basin" or not sample_ids:
        return None
    # Two populations exist per level: the atlas extraction, and the subset
    # clipped to the national boundary that the portal publishes. Matching only
    # against the atlas counts made the clipped level-12 tables — 2,732 basins
    # against the atlas's 3,981 — come out as level 9.
    counts = {1: (2,), 2: (2,), 3: (4,), 4: (12,), 5: (31,), 6: (92,), 7: (263,),
              8: (805,), 9: (1989,), 10: (3608,), 11: (3960,), 12: (3981, 2736)}
    n = len(sample_ids)
    return min(counts, key=lambda level: min(abs(c - n) for c in counts[level]))


def audit() -> list[dict]:
    registry = json.loads(TABLES.read_text(encoding="utf8"))["tables"]
    structure = {}
    if STRUCTURE.exists():
        for entry in json.loads(STRUCTURE.read_text(encoding="utf8"))["datasets"]:
            for name in [entry["table"], *entry.get("alsoTables", [])]:
                structure[name] = entry["name"]
    areas = basin_areas()

    findings = []
    for table in sorted(registry, key=lambda t: t["id"]):
        container = ROOT / table["container"]
        issues = []
        ours = table["container"].startswith("PUBLISHED/data/ontology")

        if not container.exists():
            findings.append({"table": table["id"], "state": "absent", "issues": [],
                             "classified": table["id"] in structure})
            continue

        if table["format"] == "CSV":
            if container.open("rb").read(3) == b"\xef\xbb\xbf":
                issues.append("byte-order mark: read with utf-8-sig")
            with container.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle)
                columns = next(reader)
                ids, rows = set(), 0
                position = columns.index(table["objectColumn"]) if table["objectColumn"] in columns else None
                for row in reader:
                    rows += 1
                    if position is not None and rows <= 200000:
                        ids.add(row[position])

            declared = [table.get(k) for k in ("subjectColumn", "objectColumn",
                                               "measureColumn", "scopeColumn", "measureUnitColumn")]
            declared += [c["column"] for c in table.get("dimensionColumns", [])]
            absent = [c for c in declared if c and c not in columns]
            if absent:
                issues.append(f"declared but not in the file: {', '.join(absent)}")

            if ours:
                # A missing quality column is only a finding when the table has
                # not said why. Derived and geometric tables have a standing
                # reason recorded in their note; sensor readings do not.
                exempt = ("derived" in (table.get("note") or "")
                          or "measured geometric overlap" in (table.get("note") or ""))
                if "quality" not in columns and not exempt:
                    issues.append("no quality column and no stated reason")
                if not table.get("measureUnitColumn") and "km2" not in (table.get("measureColumn") or ""):
                    issues.append("no unit column and none implied by the measure name")

            level = level_of(table, ids)
            grid = GRIDS.get(table["id"])
            if level and grid and areas.get(level):
                pixels = areas[level] / ((grid / 1000) ** 2)
                if pixels < 2:
                    issues.append(f"grain: level {level} is {pixels:.1f} px at {grid/1000:.1f} km")
        else:
            rows, level = 0, None

        if table["id"] not in structure:
            issues.append("not filed under a domain")

        findings.append({"table": table["id"], "state": "ours" if ours else "delivery",
                         "rows": rows, "level": level, "issues": issues,
                         "classified": table["id"] in structure})
    return findings


def main() -> None:
    findings = audit()
    clean = [f for f in findings if not f["issues"] and f["state"] != "absent"]
    print(f"{'TABLE':32}{'ORIGIN':10}{'LEVEL':7}{'ROWS':>10}  FINDINGS")
    print("-" * 112)
    for f in findings:
        if f["state"] == "absent":
            print(f"{f['table']:32}{'absent':10}{'—':7}{'—':>10}  not built yet")
            continue
        head = f["issues"][0] if f["issues"] else "ok"
        print(f"{f['table']:32}{f['state']:10}{str(f['level'] or '—'):7}{f['rows']:>10}  {head}")
        for extra in f["issues"][1:]:
            print(f"{'':59}  {extra}")
    print("-" * 112)
    total = sum(len(f["issues"]) for f in findings)
    print(f"  {len(clean)} clean · {total} findings across {len(findings)} tables")
    unfiled = [f["table"] for f in findings if not f["classified"]]
    if unfiled:
        print(f"  not filed under a domain: {', '.join(unfiled)}")


if __name__ == "__main__":
    main()
