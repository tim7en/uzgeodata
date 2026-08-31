"""Name every data reference the project holds, present or not.

The group inventory says a family of data is partly here or wholly missing. This
says which pieces — because "the atlas is not here" is not something you can act
on, and "AT-100-LIVESTOCK, AT-101-FORAGE-LANDS, ... 134 of them, in the private
repository" is.

Every reference gets an upper-case name to quote, whether or not the bytes exist.
A missing item is still a real reference: something in the graph, a registry or a
download script points at it, and knowing its name is the difference between
noticing an absence and being able to go and fill it.

    HELD           the file is on this machine
    WORKSPACE      built into WORKSPACE/, which is not in version control
    OFFLINE        on an external drive that was profiled and unplugged
    NEVER_FETCHED  nothing has ever downloaded it here

Usage:
    python PIPELINES/build_data_items.py [--status HELD] [--group HYDROBASINS]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "PUBLISHED" / "data" / "data-items.json"


def read(relative: str, default=None):
    path = ROOT / relative
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf8"))


def caps(text: str) -> str:
    """A quotable upper-case handle: letters, digits and single separators."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", str(text)).strip("_").upper()
    return re.sub(r"_+", "_", cleaned)


def item(name, title, group, kind, status, where, detail=""):
    return {"name": name, "title": title, "group": group, "kind": kind,
            "status": status, "where": where, "detail": detail}


def review_layers() -> list[dict]:
    """Everything the review page can already draw."""
    index = read("PUBLISHED/data/review-layers.json", {"layers": []})
    rows = []
    for layer in index["layers"]:
        rows.append(item(
            caps(layer["layer"]), layer["title"], layer["group"], "LAYER", "HELD",
            layer["url"], f"{layer['features']:,} features · {layer['geometryType'] or '—'}",
        ))
    return rows


def geopackage_tables() -> list[dict]:
    """Attribute tables inside the deliveries — routing and hierarchy, no geometry."""
    rows = []
    for relative, group in (
        ("GEODATA/uzbekistan_hydrobasins_lake_v1c/uzbekistan_hydrobasins_lake_v1c.gpkg", "HYDROBASINS"),
        ("GEODATA/uzbekistan_basinatlas_v10/uzbekistan_basinatlas_v10.gpkg", "HYDROBASINS"),
    ):
        path = ROOT / relative
        if not path.exists():
            continue
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            for table, in connection.execute(
                    "SELECT table_name FROM gpkg_contents WHERE data_type='attributes' ORDER BY table_name"):
                count = connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
                rows.append(item(caps(table), table.replace("_", " "), group, "TABLE", "HELD",
                                 relative, f"{count:,} rows"))
    return rows


def relationship_tables() -> list[dict]:
    """The measured overlays, each pointing at a container that may not be here."""
    rows = []
    for table in read("ONTOLOGY/vocab/relationship-tables.json", {"tables": []})["tables"]:
        container = table["container"]
        present = (ROOT / container).exists()
        rows.append(item(
            caps(table["containerTable"] or table["id"]), table["label"], "LINKS", "TABLE",
            "HELD" if present else "WORKSPACE", container,
            f"{table['subjectType']} → {table['objectType']} · {table['predicate']}",
        ))
    return rows


def atlas_packages() -> list[dict]:
    """The 134 thematic packages. Catalogued here, the packages themselves are not."""
    rows = []
    for package in read("PUBLISHED/data/archive-catalog.json", []):
        rows.append(item(
            caps(f"AT-{package['atlasNumber']}-{package['title']}"), package["title"], "ENVATLAS",
            "PACKAGE", "WORKSPACE", "private repository / WORKSPACE/uploads",
            f"{package['category']} · {package['extension']} · {package['size'] / 1024:,.0f} KB",
        ))
    return rows


def external_datasets() -> list[dict]:
    """Everything the two profiled drives were declared to contain."""
    group_for = {
        "osm-geofabrik-2014": "OSM",
        "uzkad-cadastre-2025-08": "AGRICADASTRE",
        "uzhydromet-stations-2022": "STATIONS",
        "agricultural-statistics": "AGRISTATS",
        "socio-economic-surveys": "SURVEYS",
        "hydrosheds-uz-2026": "HYDROBASINS",
        "atlas-missing-package": "ENVATLAS",
    }
    rows = []
    for source in read("ONTOLOGY/vocab/external-sources.json", {"sources": []})["sources"]:
        group = group_for.get(source["id"], "OFFLINE")
        for dataset in source.get("datasets", []):
            match = dataset.get("match", [])
            derived = dataset.get("derived", [])
            # A derivative that survived into the repository outranks the source
            # delivery: it is what a reader can actually open.
            here = [p for p in derived if (ROOT / p).exists()]
            rows.append(item(
                caps(dataset["slug"]), dataset["label"], group, "DATASET",
                "HELD" if here else "OFFLINE",
                here[0] if here else f"{source['inventory']} :: {match[0] if match else '—'}",
                source["label"],
            ))
    return rows


def uzkad_regions() -> list[dict]:
    """The fourteen regional downloads the cadastre script would produce."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "regions", ROOT / "PIPELINES" / "download_uzkad_agriculture_regions.py")
    rows = []
    try:
        # The module imports requests at load time; read the table without executing.
        text = (ROOT / "PIPELINES" / "download_uzkad_agriculture_regions.py").read_text(encoding="utf8")
        block = re.search(r"REGIONS = \((.*?)\n\)", text, re.S).group(1)
        entries = re.findall(r'\("(\d+)",\s*"([a-z_]+)",\s*"([^"]+)"\)', block)
    except (AttributeError, OSError):
        return rows
    target = ROOT / "WORKSPACE" / "downloads" / "uzkad_agriculture_regions"
    for code, slug, label in entries:
        output = target / f"{code}_{slug}.gpkg"
        rows.append(item(
            caps(f"UZKAD-{code}-{slug}"), label, "AGRICADASTRE", "DATASET",
            "HELD" if output.exists() else "NEVER_FETCHED",
            str(output.relative_to(ROOT)) if output.exists()
            else f"db.ngis.uz UZKAD/AGR_ONLY_UZKAD_DB16 · soato_region={code}",
            "regional GeoPackage from the cadastre feature service",
        ))
    return rows


def workspace_layers() -> list[dict]:
    """Atlas derivatives the graph advertises a URL for but which are not here."""
    rows = []
    seen = set()
    for entity in read("ONTOLOGY/instances/entities.json", {"entities": []})["entities"]:
        url = entity.get("url") or ""
        if entity.get("type") != "Distribution" or not url.startswith("/data/layers/"):
            continue
        if (ROOT / "PUBLISHED" / url.lstrip("/")).exists() or url in seen:
            continue
        seen.add(url)
        rows.append(item(
            caps(Path(url).stem), entity.get("label", url), "ENVATLAS", "LAYER", "WORKSPACE",
            url, f"{entity.get('role', '')} · {entity.get('format', '')}",
        ))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", help="Show only this status.")
    parser.add_argument("--group", help="Show only this group.")
    args = parser.parse_args()

    items = (review_layers() + geopackage_tables() + relationship_tables()
             + external_datasets() + uzkad_regions() + atlas_packages() + workspace_layers())

    order = {"HELD": 0, "WORKSPACE": 1, "OFFLINE": 2, "NEVER_FETCHED": 3}
    items.sort(key=lambda row: (row["group"], order[row["status"]], row["name"]))

    counts: dict[str, int] = {}
    by_group: dict[str, dict[str, int]] = {}
    for row in items:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
        by_group.setdefault(row["group"], {})
        by_group[row["group"]][row["status"]] = by_group[row["group"]].get(row["status"], 0) + 1

    OUTPUT.write_text(json.dumps({
        "version": "1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "statuses": {
            "HELD": "The file is on this machine.",
            "WORKSPACE": "Built into WORKSPACE/, which is not in version control.",
            "OFFLINE": "On an external drive that was profiled and then unplugged.",
            "NEVER_FETCHED": "Nothing has ever downloaded it here.",
        },
        "counts": counts,
        "byGroup": by_group,
        "items": items,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf8")

    shown = [r for r in items
             if (not args.status or r["status"] == args.status)
             and (not args.group or r["group"] == args.group)]
    width = max((len(r["name"]) for r in shown), default=10)
    for row in shown:
        print(f"  {row['name']:<{width}}  {row['status']:<14} {row['group']:<13} {row['kind']:<8} {row['title'][:44]}")
    print(f"\n{len(items):,} named references -> {OUTPUT.relative_to(ROOT)}")
    print("  " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: order[kv[0]])))


if __name__ == "__main__":
    main()
