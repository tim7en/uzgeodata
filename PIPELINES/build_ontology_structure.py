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
    "LANDCOVER_ADMIN_YEAR": {
        "domain": "LAND", "table": "landcover-admin-year",
        "source": "PUBLISHED/data/analysis/landcover-admin-year.csv",
        "what": "Area of each land cover class per district per year.",
    },
    "LANDCOVER_BASIN_YEAR": {
        "domain": "LAND", "table": "landcover-basin-year",
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

    print(f"{'NO':6}{'DOMAIN':12}{'NAME':30}{'STATE':10}  TABLE")
    print("-" * 100)
    moved = missing = 0
    deferred: list[str] = []
    for row in rows:
        source = ROOT / row["source"]
        in_place = row.get("inPlace", False)
        target = TREE / row["folder"] / Path(row["source"]).name
        already_home = source.resolve() == target.resolve()
        if in_place:
            state = "in delivery" if source.exists() else "absent"
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
            "tables": [row["table"], *row.get("alsoTables", [])],
            "predicate": registry.get(row["table"], {}).get("predicate"),
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
    if deferred:
        print(f"  {len(deferred)} deferred while being written: {', '.join(deferred)}")
        print("  Re-run --apply once those pipelines finish.")

    if not args.apply:
        print("\n  Re-run with --apply to create the tree and move the tables.")
        return

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
