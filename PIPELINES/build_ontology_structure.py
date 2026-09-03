"""Lay the ontology's datasets out by domain, numbered, capitalised and sorted.

Every dataset the ontology stores belongs to a domain — the atmosphere above the
ground, the land itself, or the water moving through it — and finding one should
not require knowing which pipeline happened to write it. This arranges them:

    PUBLISHED/data/ontology/
        1_ATMOSPHERE/
            1.1_CFSV2_BASIN_MONTHLY/
            1.2_CHIRPS_V3_BASIN_MONTHLY/
        2_LAND/
            2.1_LANDCOVER_ADMIN_YEAR/
        3_WATER/
            3.1_ADMIN_BASIN_LINKS/

Domains are numbered and datasets within them numbered again, both in
alphabetical order, and every name is upper case. Each dataset folder holds its
table and a DATASET.json describing it.

One thing to understand before relying on the numbers: **the number is a
position, not an identity**. Inserting a dataset alphabetically shifts everything
after it, so a reference to "2.1" silently becomes a reference to a different
dataset. The upper-case name is the stable identifier and is what the graph, the
relationship tables and any later model should quote. The number exists so a
person reading a directory listing sees an order; it is recomputed on every run
and must never be stored as a key.

Domains are assigned per dataset by its primary subject. Some datasets span more
than one — CFSv2 carries both meteorology and four soil-moisture depths — so the
variables that sit outside their dataset's domain are recorded in DATASET.json
under crossDomain rather than being silently filed under one heading.

    python PIPELINES/build_ontology_structure.py            # show the plan
    python PIPELINES/build_ontology_structure.py --apply    # move the files
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TREE = ROOT / "PUBLISHED" / "data" / "ontology"
INDEX = TREE / "INDEX.json"
TABLES = ROOT / "ONTOLOGY" / "vocab" / "relationship-tables.json"

# Alphabetical, which is also the order they are numbered in.
DOMAINS = {
    "ATMOSPHERE": "What happens above the surface: precipitation, temperature, humidity, "
                  "radiation and evaporative demand.",
    "LAND": "The surface itself: cover, use, soil and terrain.",
    "REFERENCE": "The frames everything else is measured against — administrative and "
                 "hydrological geography that is not itself a measurement.",
    "WATER": "Water in the landscape: catchments, rivers, lakes and the routing between them.",
}

# name -> where it goes, what it is, and which of its variables belong elsewhere.
DATASETS = {
    "CFSV2_BASIN_ANOMALY": {
        "domain": "ATMOSPHERE", "table": "cfsv2-basin-anomaly",
        "source": "PUBLISHED/data/analysis/cfsv2-basin-anomaly.csv",
        "what": "Basin monthly state expressed as z-scores against its own climatological normal.",
        "crossDomain": {"LAND": ["soil_moisture_5cm", "soil_moisture_25cm",
                                 "soil_moisture_70cm", "soil_moisture_150cm"]},
    },
    "CFSV2_BASIN_CLIMATOLOGY": {
        "domain": "ATMOSPHERE", "table": "cfsv2-basin-climatology",
        "source": "PUBLISHED/data/analysis/cfsv2-basin-climatology.csv",
        "what": "Mean and standard deviation per basin, month and variable over a stated baseline.",
        "crossDomain": {"LAND": ["soil_moisture_5cm", "soil_moisture_25cm",
                                 "soil_moisture_70cm", "soil_moisture_150cm"]},
    },
    "CFSV2_BASIN_MONTHLY": {
        "domain": "ATMOSPHERE", "table": "cfsv2-basin-monthly",
        "source": "PUBLISHED/data/analysis/cfsv2-basin-monthly.csv",
        "what": "Monthly mean land-atmosphere state per level-7 basin from the 6-hourly CFSv2 field.",
        "crossDomain": {"LAND": ["soil_moisture_5cm", "soil_moisture_25cm",
                                 "soil_moisture_70cm", "soil_moisture_150cm"]},
    },
    "CAMS_BASIN_MONTHLY": {
        "domain": "ATMOSPHERE", "table": "cams-basin-monthly",
        "source": "PUBLISHED/data/ontology/1_ATMOSPHERE/1.1_CAMS_BASIN_MONTHLY/cams-basin-monthly.csv",
        "what": ("Aerosol optical depth and PM2.5 per level-6 basin from the CAMS +0h analysis — "
                 "the assimilated estimate of what the atmosphere was, not a forecast."),
    },
    "CAMS_EVENT_VERIFICATION": {
        "domain": "ATMOSPHERE", "table": None,
        "tableNote": ("Not a relationship table. Its rows describe how a forecast performed at a "
                      "point, which is a statement about the dataset rather than a relation "
                      "between two features, and the registry has no object type that fits a "
                      "site. It was registered as Dataset-to-Basin once and that was wrong."),
        "source": "PUBLISHED/data/ontology/_ATMOSPHERE/_CAMS_EVENT_VERIFICATION/cams-event-verification.csv",
        "what": ("Whether CAMS forecasts caught pollution and dust events at a point, by lead "
                 "time: detection rate, false alarms and bias above a percentile threshold. "
                 "Events, not averages — a product can track the mean and miss every spike."),
    },
    "CAMS_FORECAST_SKILL": {
        "domain": "ATMOSPHERE", "table": None,
        "tableNote": ("Not a relationship table. Skill is computed over the country as a whole, "
                      "so there is no basin on the other end of the row; declaring one implied a "
                      "spatial resolution the numbers do not have."),
        "source": "PUBLISHED/data/ontology/_ATMOSPHERE/_CAMS_FORECAST_SKILL/cams-forecast-skill.csv",
        "what": ("How far CAMS forecasts diverge from their own analysis at 24 to 120 hours "
                 "ahead: error, bias and correlation per lead time. Tells a user of the state "
                 "table how far ahead the product is worth believing."),
    },
    "CHIRPS_V3_BASIN_PENTAD": {
        "domain": "ATMOSPHERE", "table": "chirps-v3-basin-pentad",
        "source": "PUBLISHED/data/ontology/1_ATMOSPHERE/1.4_CHIRPS_V3_BASIN_PENTAD/chirps-v3-basin-pentad.csv",
        "what": ("Pentadal precipitation total per level-12 basin at 5.6 km — six per month. "
                 "CHIRPS is computed at this scale and its daily product is a disaggregation "
                 "of it, so this is the authoritative quantity. Monthly and seasonal totals "
                 "are sums of pentads and are derived rather than stored."),
    },
    "CHIRTS_BASIN_MONTHLY": {
        "domain": "ATMOSPHERE", "table": "chirts-basin-monthly",
        "source": "PUBLISHED/data/ontology/1_ATMOSPHERE/1.5_CHIRTS_BASIN_MONTHLY/chirts-basin-monthly.csv",
        "what": ("Monthly temperature and humidity statistics per level-12 basin from CHIRTS-daily "
                 "at 5.6 km, including counts of days above 35 and 40 degrees that only a daily "
                 "record can give. Closed: the record runs 1983 to 2016 and stops."),
    },
    "CPC_BASIN_MONTHLY": {
        "domain": "ATMOSPHERE", "table": "cpc-basin-monthly",
        "source": "PUBLISHED/data/ontology/1_ATMOSPHERE/1.6_CPC_BASIN_MONTHLY/cpc-basin-monthly.csv",
        "what": ("Monthly temperature statistics per level-6 basin from the CPC gauge-based "
                 "half-degree analysis, 1979 to the present, with the station count that "
                 "informed each cell."),
    },
    "GHM_UNIT_MODIFICATION": {
        "domain": "LAND", "table": "ghm-basin-modification",
        "alsoTables": ["ghm-district-modification"],
        "source": "PUBLISHED/data/ontology/2_LAND/2.1_GHM_UNIT_MODIFICATION/ghm-unit-modification.csv",
        "what": ("Human modification index for 2016 at 1 km, reduced over both level-12 basins "
                 "and districts: the mean plus the share of area in each modification band. The "
                 "only timeless layer here — one image, no timestamp."),
    },
    "LANDCOVER_ADMIN_YEAR": {
        "domain": "LAND", "table": "landcover-admin-year",
        "source": "PUBLISHED/data/analysis/landcover-admin-year.csv",
        "what": "Area of each land cover class per district per year.",
    },
    "LANDCOVER_BASIN_YEAR": {
        "domain": "LAND", "table": None,
        "tableNote": ("Planned but never built, so the graph does not declare it. The entry stays "
                      "so the gap is visible; it gains a table when the basin run produces rows."),
        "source": "PUBLISHED/data/analysis/landcover-basin-year.csv",
        "what": "Area of each land cover class per level-12 basin per year. Not yet built.",
    },
    # These live inside the HydroSHEDS deliveries. A delivery is a signed unit with
    # its own manifest, so its files stay where they are and the tree records the
    # dataset with a pointer rather than a copy — a second copy would be a second
    # thing to keep in step.
    "BASINATLAS_DOWNSTREAM_ROUTING": {
        "domain": "WATER", "table": "basinatlas-uz-downstream", "inPlace": True,
        "source": "GEODATA/uzbekistan_basinatlas_v10/relationships/downstream_links.csv",
        "what": "Which basin each BasinATLAS basin drains into.",
    },
    "BASINATLAS_PFAFSTETTER_HIERARCHY": {
        "domain": "WATER", "table": "basinatlas-uz-pfaf", "inPlace": True,
        "source": "GEODATA/uzbekistan_basinatlas_v10/relationships/pfaf_hierarchy.csv",
        "what": "Parent and child basins by Pfafstetter code, level 1 to 12.",
    },
    "BASINATLAS_SUBBASIN_HIERARCHY": {
        "domain": "WATER", "table": "basinatlas-uz-hierarchy", "inPlace": True,
        "source": "GEODATA/uzbekistan_basinatlas_v10/relationships/feature_hierarchy_links.csv",
        "what": "Basin containment confirmed by spatial overlap rather than by code alone.",
    },
    "HYDROBASINS_LAKE_DOWNSTREAM_ROUTING": {
        "domain": "WATER", "table": "hydrobasins-lake-uz-downstream", "inPlace": True,
        "source": "GEODATA/uzbekistan_hydrobasins_lake_v1c/relationships/downstream_links.csv",
        "what": "Downstream routing in the lake-format HydroBASINS extraction.",
    },
    "HYDROBASINS_LAKE_PFAFSTETTER_HIERARCHY": {
        "domain": "WATER", "table": "hydrobasins-lake-uz-pfaf", "inPlace": True,
        "source": "GEODATA/uzbekistan_hydrobasins_lake_v1c/relationships/pfaf_hierarchy.csv",
        "what": "Pfafstetter parentage in the lake-format extraction.",
    },
    "HYDROBASINS_LAKE_SUBBASIN_HIERARCHY": {
        "domain": "WATER", "table": "hydrobasins-lake-uz-hierarchy", "inPlace": True,
        "source": "GEODATA/uzbekistan_hydrobasins_lake_v1c/relationships/feature_hierarchy_links.csv",
        "what": "Basin containment in the lake-format extraction.",
    },
    # Declared by the graph but built into WORKSPACE/, so absent here. They are
    # classified anyway: a dataset that is missing still has a domain, and leaving
    # it unfiled would make the tree describe only what happens to be present.
    "ATLAS_BASIN_COVERAGE": {
        "domain": "REFERENCE", "table": "atlas-basin-coverage", "inPlace": True,
        "source": "WORKSPACE/derived/atlas-basin-links.csv",
        "what": "Which environmental atlas layers overlap which level-12 basin, and by how much.",
    },
    "ATLAS_BASIN_STATISTICS": {
        "domain": "REFERENCE", "table": "atlas-basin-statistics", "inPlace": True,
        "source": "WORKSPACE/derived/basin-zonal-stats.csv",
        "what": "What each atlas raster reads inside each level-12 basin.",
    },
    "HYDROGRAPHY_LAKE_BASIN": {
        "domain": "WATER", "table": "hydrography-lake-basin", "inPlace": True,
        "source": "WORKSPACE/derived/hydrography/uzbekistan-hydrography.gpkg",
        "what": "Which level-12 basin each lake sits in.",
    },
    "HYDROGRAPHY_RIVER_BASIN": {
        "domain": "WATER", "table": "hydrography-river-basin", "inPlace": True,
        "source": "WORKSPACE/derived/hydrography/uzbekistan-hydrography.gpkg",
        "what": "Which level-12 basin each river reach drains.",
    },
    "HYDROGRAPHY_RIVER_DOWNSTREAM": {
        "domain": "WATER", "table": "hydrography-river-downstream", "inPlace": True,
        "source": "WORKSPACE/derived/hydrography/uzbekistan-hydrography.gpkg",
        "what": "Reach-to-reach downstream routing for the 17,447 published reaches.",
    },
    "ADMIN_BASIN_LINKS": {
        "domain": "REFERENCE", "table": "admin-basin-province",
        "source": "PUBLISHED/data/hydrography/admin-basin-links.csv",
        "what": "Shared area between every level-12 basin and every province and district.",
        "alsoTables": ["admin-basin-district"],
    },
}

NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


def in_use(path: Path) -> bool:
    """Whether something currently has the file open for writing.

    A pipeline that appends as it goes keeps its handle open, and moving the file
    out from under it does not fail — the writer keeps filling the old inode and
    the rows quietly stop arriving where anything is looking for them. Worth one
    lsof to avoid.
    """
    try:
        result = subprocess.run(["lsof", "-t", str(path)], capture_output=True, text=True, timeout=10)
        return bool(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return False


def plan() -> list[dict]:
    """Domain and dataset numbering, both alphabetical."""
    rows = []
    for domain_index, domain in enumerate(sorted(DOMAINS), start=1):
        members = sorted(name for name, entry in DATASETS.items() if entry["domain"] == domain)
        for member_index, name in enumerate(members, start=1):
            entry = DATASETS[name]
            rows.append({
                "number": f"{domain_index}.{member_index}",
                "domain": domain, "domainNumber": str(domain_index), "name": name,
                "folder": f"{domain_index}_{domain}/{domain_index}.{member_index}_{name}",
                **entry,
            })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Move files. Without it, only report.")
    args = parser.parse_args()

    bad = [name for name in DATASETS if not NAME_PATTERN.match(name)]
    if bad:
        raise SystemExit(f"These names break the convention (upper case, digits, underscore): {bad}")

    rows = plan()
    registry = {t["id"]: t for t in json.loads(TABLES.read_text(encoding="utf8"))["tables"]}

    # Every table this tree names must be one the graph declares. Deregistering a
    # table without updating the tree left three entries pointing at ids that no
    # longer existed, and nothing noticed: the audit walks tables looking for a
    # domain, never the other way round.
    dangling = [(row["name"], name) for row in rows
                for name in [row.get("table"), *row.get("alsoTables", [])]
                if name and name not in registry]
    if dangling:
        raise SystemExit(
            "These datasets name a relationship table the graph does not declare:\n"
            + "\n".join(f"    {n} -> {t}" for n, t in dangling)
            + "\n  Either register the table in relationship-tables.json, or set table: None "
              "with a tableNote saying why it has none.")

    print(f"{'NO':6}{'DOMAIN':12}{'NAME':30}{'STATE':10}  TABLE")
    print("-" * 100)
    moved = missing = 0
    deferred: list[str] = []
    renumbered: list[str] = []
    for row in rows:
        source = ROOT / row["source"]
        in_place = row.get("inPlace", False)
        target = TREE / row["folder"] / Path(row["source"]).name

        # Find the dataset's folder by name, wherever it is currently numbered.
        # Renumbering happens whenever a dataset is inserted alphabetically, and
        # a recorded path with a number in it goes stale the moment it does —
        # which is how CFSv2 ended up with its data under 1.1 while the tree
        # expected 1.3, beside an empty folder at the new number.
        existing = [d for d in TREE.glob(f"*/*_{row['name']}") if d.is_dir()]
        # More than one folder can carry the name after a renumber: the old one
        # holding the data and an empty one created at the new number. Drop the
        # empties first, or they block the rename that would fix it.
        # DATASET.json is this tool's own card, written into whatever folder the
        # numbering said at the time. It is not evidence that a folder holds the
        # dataset; only the table itself is.
        def holds_data(folder: Path) -> bool:
            return any(f.name != "DATASET.json" for f in folder.iterdir())

        filled = [d for d in existing if holds_data(d)]
        for shell in [d for d in existing if d not in filled and d != target.parent]:
            for leftover in shell.iterdir():
                leftover.unlink()
            shell.rmdir()
        if len(filled) > 1:
            raise SystemExit(
                f"{row['name']} has data in {len(filled)} folders: "
                + ", ".join(str(d.relative_to(ROOT)) for d in filled)
                + "\n  Merge them by hand; this tool will not guess which is current.")
        current = filled[0] if filled else None
        if current is not None and current != target.parent:
            target.parent.parent.mkdir(parents=True, exist_ok=True)
            # The destination may already hold a card this tool wrote on an earlier
            # run under the old numbering. That is not data and must not block the
            # folder that actually holds the table from taking its place.
            if target.parent.exists() and not holds_data(target.parent):
                for leftover in target.parent.iterdir():
                    leftover.unlink()
                target.parent.rmdir()
            if not target.parent.exists():
                current.rename(target.parent)
                renumbered.append(f"{row['name']}: {current.name} -> {target.parent.name}")
        already_home = source.resolve() == target.resolve() if source.exists() else False
        landed = target.exists()
        if in_place:
            state = "in delivery" if source.exists() else "absent"
        elif landed:
            state = "filed"
        elif already_home:
            # Its pipeline writes straight into the tree; nothing to move.
            state = "filed" if source.exists() else "absent"
        else:
            state = "present" if source.exists() else ("filed" if target.exists() else "absent")
        if state == "absent":
            missing += 1
        print(f"{row['number']:6}{row['domain']:12}{row['name']:30}{state:10}  {row['table']}")

        if not args.apply:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.exists() and not in_place and not already_home:
            if in_use(source):
                deferred.append(row["name"])
                print(f"       ^ deferred: something is still writing to {row['source']}")
            else:
                shutil.move(str(source), str(target))
                moved += 1
        # Every dataset gets its card, whether or not the table is here yet.
        card = {
            "name": row["name"], "number": row["number"], "domain": row["domain"],
            "what": row["what"],
            "tables": [t for t in [row.get("table"), *row.get("alsoTables", [])] if t],
            "tableNote": row.get("tableNote"),
            "predicate": registry.get(row.get("table"), {}).get("predicate"),
            "file": Path(row["source"]).name,
            "storedInPlace": in_place,
            "path": row["source"] if in_place else str((target).relative_to(ROOT)),
            "present": source.exists() if in_place else target.exists(),
            "crossDomain": row.get("crossDomain", {}),
            "note": ("The number is a position and is recomputed whenever a dataset is added. "
                     "Quote the name, never the number."),
        }
        (target.parent / "DATASET.json").write_text(
            json.dumps(card, ensure_ascii=False, indent=2), encoding="utf8")

    print("-" * 100)
    print(f"  {len(rows)} datasets across {len(DOMAINS)} domains"
          + (f" · {moved} files moved" if args.apply else " · dry run, nothing moved")
          + (f" · {missing} not yet built" if missing else ""))
    if renumbered:
        print(f"  {len(renumbered)} folders renumbered in place:")
        for line in renumbered:
            print(f"      {line}")
    if deferred:
        print(f"  {len(deferred)} deferred while being written: {', '.join(deferred)}")
        print("  Re-run --apply once those pipelines finish.")

    if not args.apply:
        print("\n  Re-run with --apply to create the tree and move the tables.")
        return

    # The numbering is this tool's to assign, so the container paths that carry it
    # are this tool's to keep correct. Leaving them to be edited by hand is how
    # LANDCOVER_ADMIN_YEAR ended up with a pipeline writing to 2.1 and a graph
    # pointing at 2.2 after a new dataset took the slot.
    registry_path = TABLES
    registry_doc = json.loads(registry_path.read_text(encoding="utf8"))
    by_table = {}
    for row in rows:
        for name in [row["table"], *row.get("alsoTables", [])]:
            by_table[name] = row
    repointed = 0
    for table in registry_doc["tables"]:
        row = by_table.get(table["id"])
        if not row or row.get("inPlace"):
            continue
        want = str((TREE / row["folder"] / Path(row["source"]).name).relative_to(ROOT))
        if table["container"] != want:
            table["container"] = want
            repointed += 1
    if repointed:
        registry_path.write_text(json.dumps(registry_doc, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf8")
        print(f"  {repointed} container paths repointed to their current numbers")

    for domain_index, domain in enumerate(sorted(DOMAINS), start=1):
        folder = TREE / f"{domain_index}_{domain}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "DOMAIN.json").write_text(json.dumps({
            "domain": domain, "number": str(domain_index), "definition": DOMAINS[domain],
            "datasets": sorted(n for n, e in DATASETS.items() if e["domain"] == domain),
        }, ensure_ascii=False, indent=2), encoding="utf8")

    INDEX.write_text(json.dumps({
        "version": "1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "convention": {
            "naming": "Upper case, digits and underscores only.",
            "ordering": "Domains alphabetical, datasets alphabetical within a domain.",
            "numbering": "<domain>.<dataset>, recomputed on every run.",
            "identity": ("The name is the stable identifier. The number is a position and moves "
                         "when a dataset is inserted alphabetically, so nothing should store it."),
            "domains": DOMAINS,
        },
        "datasets": [{k: v for k, v in row.items() if k != "source"} for row in rows],
    }, ensure_ascii=False, indent=2), encoding="utf8")
    print(f"  -> {INDEX.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
