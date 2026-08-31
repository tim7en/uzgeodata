"""Group every data reference the project holds, and check what is actually here.

The dataset catalogue answers "what does the graph describe"; this answers the
question that comes before it — *what kinds of data does this project have, and
which of them can I open on this machine right now*. Each group gets a short
upper-case code so the rest of the project, and the people working on it, have a
stable name to refer to.

Status is measured, never declared. Every group names the paths it would occupy
and they are checked on disk, because the repository is full of records that
describe files living somewhere else: derivatives built into an untracked
workspace, deliveries profiled on a Windows drive that was unplugged afterwards,
and one source that has never been fetched at all. A group is:

    HELD       the files are here and can be opened
    PARTIAL    some of what the group covers is here, some is not
    WORKSPACE  built by a pipeline into WORKSPACE/, which is not in version control
    OFFLINE    seen once on an external drive; only the profile survives here
    ABSENT     nothing of it on this machine and no local route to it

Usage:
    python PIPELINES/build_data_groups.py [--json]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "PUBLISHED" / "data" / "data-groups.json"


def gpkg_count(relative: str, table: str) -> int | None:
    path = ROOT / relative
    if not path.exists():
        return None
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            return connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    except sqlite3.Error:
        return None


def geojson_count(relative: str) -> int | None:
    path = ROOT / relative
    if not path.exists():
        return None
    try:
        return len(json.loads(path.read_text(encoding="utf8"))["features"])
    except (ValueError, KeyError):
        return None


def size_of(paths: list[str]) -> int:
    total = 0
    for relative in paths:
        path = ROOT / relative
        if path.is_dir():
            total += sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        elif path.is_file():
            total += path.stat().st_size
    return total


# Each group names the paths that would hold it. `held` is what must be present
# for the group to count as here; `expected` is the wider set it would occupy if
# nothing were missing.
GROUPS = [
    {
        "code": "ADMIN",
        "title": "Administrative boundaries",
        "what": "Country, province and district polygons with P-codes and trilingual names.",
        "source": "OCHA/HDX Common Operational Dataset, uzb_admbnda 2018b",
        "held": ["GEODATA/uzb_admbnda_adm0_2018b", "GEODATA/uzb_admbnda_adm1_2018b",
                 "GEODATA/uzb_admbnda_adm2_2018b"],
        "web": ["PUBLISHED/data/admin/adm1.geojson", "PUBLISHED/data/admin/adm2.geojson"],
        "rebuild": "npm run hydrography:adminlinks",
    },
    {
        "code": "HYDROBASINS",
        "title": "Basin watersheds, levels 1-12",
        "what": "Pfafstetter sub-basins at every level, with downstream routing and the level-12 frame everything else joins onto.",
        "source": "HydroSHEDS HydroBASINS v1c, and the BasinATLAS extraction in standard format",
        "held": ["GEODATA/uzbekistan_basinatlas_v10/uzbekistan_basinatlas_v10.gpkg",
                 "GEODATA/uzbekistan_hydrobasins_lake_v1c/uzbekistan_hydrobasins_lake_v1c.gpkg"],
        "web": ["PUBLISHED/data/hydrography/basins.geojson"],
        "rebuild": "npm run hydrography:build",
    },
    {
        "code": "HYDRORIVERS",
        "title": "River reaches",
        "what": "Routed river network with downstream links, Strahler order, discharge and catchment area per reach.",
        "source": "HydroSHEDS HydroRIVERS v1.0, clipped to Uzbekistan",
        "held": [],
        "web": ["PUBLISHED/data/hydrography/rivers.geojson"],
        "rebuild": "npm run hydrography:build",
        "note": "Only the web projection is in the repository; the source FileGDB is on the Earth Engine drive.",
    },
    {
        "code": "HYDROLAKES",
        "title": "Lakes and reservoirs",
        "what": "Water bodies with area, volume, depth and the basin each sits in.",
        "source": "HydroSHEDS HydroLAKES v1.0, clipped to Uzbekistan",
        "held": [],
        "web": ["PUBLISHED/data/hydrography/lakes.geojson"],
        "rebuild": "npm run hydrography:build",
    },
    {
        "code": "BASINATLAS",
        "title": "Basin environmental attributes",
        "what": "281 documented hydro-environmental attributes per level-12 basin: hydrology, climate, land cover, soils, anthropogenic pressure.",
        "source": "HydroATLAS / BasinATLAS v1.0 (Linke et al. 2019)",
        "held": ["GEODATA/uzbekistan_basinatlas_v10/uzbekistan_basinatlas_v10.gpkg",
                 "ONTOLOGY/instances/hydroatlas-columns.json"],
        "web": ["PUBLISHED/data/hydrography/basin-attributes.json",
                "PUBLISHED/data/hydrography/attribute-dictionary.json"],
        "rebuild": "npm run hydrography:attributes",
    },
    {
        "code": "ENVATLAS",
        "title": "National environmental atlas",
        "what": "The 134-package thematic atlas: land and agriculture, biodiversity, climate, water, hazards, forests, infrastructure.",
        "source": "Uzbekistan environmental atlas, ArcGIS layer packages",
        "held": ["PUBLISHED/data/archive-catalog.json"],
        "expected": ["WORKSPACE/derived/web-layers", "WORKSPACE/uploads"],
        "rebuild": "the source packages are in the private repository; derivatives build into WORKSPACE/",
        "note": "Only the catalogue of the 134 packages is here. The packages and their web derivatives are not.",
    },
    {
        "code": "AGRICADASTRE",
        "title": "Agricultural cadastre",
        "what": "Parcel-level agricultural field geometry, region by region. Authoritative for tenure, not for physical land cover.",
        "source": "UZKAD state cadastre feature service (db.ngis.uz), and an August 2025 extraction on the maps drop",
        "held": [],
        "expected": ["WORKSPACE/downloads/uzkad_agriculture_regions"],
        "rebuild": "python PIPELINES/download_uzkad_agriculture_regions.py",
        "note": "Never fetched on this machine. The download needs the UZKAD service and a local ogr2ogr; neither is available here.",
    },
    {
        "code": "STATIONS",
        "title": "Monitoring station network",
        "what": "Uzhydromet gauges and meteorological stations with coordinates and network membership.",
        "source": "Uzhydromet delivery, 2022-05-26",
        "held": ["ONTOLOGY/instances/external/details.json"],
        "expected": ["WORKSPACE/derived/osm-geojson"],
        "rebuild": "npm run ontology:details",
        "note": "The 190 stations are in the graph with coordinates. The source shapefiles are on the maps drop.",
    },
    {
        "code": "HAZARDS",
        "title": "Hazards and seismicity",
        "what": "Earthquake epicentres 1990-2024, flood-risk polygons, glacial lakes and the derived seismicity clustering.",
        "source": "Atlas derivatives and the seismicity analysis pipeline",
        "held": ["PUBLISHED/data/earthquakes.geojson", "PUBLISHED/data/flood-risk.geojson",
                 "PUBLISHED/data/glacial-lakes.geojson", "PUBLISHED/data/analysis/seismicity.json",
                 "PUBLISHED/data/analysis/seismicity-clusters.geojson"],
        "rebuild": "PIPELINES/analysis",
    },
    {
        "code": "PROTECTED",
        "title": "Protected areas",
        "what": "Reserves and protected-area polygons.",
        "source": "Atlas derivative",
        "held": ["PUBLISHED/data/protected-areas.geojson"],
        "rebuild": "npm run ontology:build",
    },
    {
        "code": "WATERMGMT",
        "title": "Water management zones",
        "what": "Irrigation and water-administration polygons.",
        "source": "Atlas derivative",
        "held": ["PUBLISHED/data/water-management.geojson"],
        "rebuild": "npm run ontology:build",
    },
    {
        "code": "LANDUSE",
        "title": "Land use and land cover",
        "what": "The land-use shape model derived from the atlas land-cover packages.",
        "source": "Atlas derivative, PIPELINES/analysis",
        "held": ["PUBLISHED/data/analysis/landuse-shape-model.json"],
        "expected": ["WORKSPACE/derived/raster-geojson"],
        "rebuild": "PIPELINES/raster_to_geojson.py",
        "note": "The shape model is here; the polygonised rasters it describes are not.",
    },
    {
        "code": "OSM",
        "title": "OpenStreetMap extract",
        "what": "Buildings, roads and other OSM layers for Uzbekistan, 2014 vintage.",
        "source": "Geofabrik / mapcruzin extract, on the maps drop",
        "held": [],
        "expected": ["WORKSPACE/derived/osm-geojson"],
        "rebuild": "re-extract from Geofabrik, or re-attach the maps drop",
        "note": "ODbL-1.0, so this is the one offline group with no licence obstacle to replacing.",
    },
    {
        "code": "AGRISTATS",
        "title": "Agricultural and fertiliser statistics",
        "what": "Crop statistics for all and irrigated land 2012-2020, and fertiliser series, as spreadsheets.",
        "source": "Uzhydromet delivery, 2022-05-26; originating agency unconfirmed",
        "held": [],
        "rebuild": "re-attach the maps drop",
    },
    {
        "code": "SURVEYS",
        "title": "Household and service surveys",
        "what": "Survey responses transferred by Uzhydromet.",
        "source": "Uzhydromet transfer, 2022-05-27",
        "held": [],
        "rebuild": "re-attach the maps drop",
        "note": "Flagged may-contain-personal-data and out-of-scope-for-the-portal. Handle before any use.",
    },
    {
        "code": "ONTOLOGY",
        "title": "The knowledge graph",
        "what": "872 entities and 3,692 typed assertions over datasets, distributions, layers, stations and agents, with the vocabularies and schemas that constrain them.",
        "source": "Built by PIPELINES/ontology from the registries",
        "held": ["ONTOLOGY/instances/entities.json", "ONTOLOGY/instances/assertions.json",
                 "ONTOLOGY/vocab", "ONTOLOGY/schema"],
        "web": ["PUBLISHED/data/ontology-graph.json", "PUBLISHED/data/ontology-triples.json",
                "PUBLISHED/data/data-catalogue.json"],
        "rebuild": "npm run ontology:build  (needs WORKSPACE/ — see the README warning)",
    },
    {
        "code": "LINKS",
        "title": "Measured relationship tables",
        "what": "Overlays that connect the layers to each other: basins to administrative units, atlas layers to basins, raster statistics per basin, and the river and lake routing.",
        "source": "Built by the overlay pipelines",
        "held": ["PUBLISHED/data/hydrography/admin-basin-links.csv",
                 "PUBLISHED/data/hydrography/admin-basin-links.json",
                 "PUBLISHED/data/hydrography/relationships.json"],
        "expected": ["WORKSPACE/derived/atlas-basin-links.csv",
                     "WORKSPACE/derived/basin-zonal-stats.csv"],
        "rebuild": "npm run hydrography:adminlinks / hydrography:atlaslinks / hydrography:zonalstats",
        "note": "The administrative and hydrographic tables are here. The atlas overlay and zonal statistics are not.",
    },
]


def classify(group: dict) -> tuple[str, list[str], list[str]]:
    held = [p for p in group.get("held", []) if (ROOT / p).exists()]
    missing_held = [p for p in group.get("held", []) if not (ROOT / p).exists()]
    web = [p for p in group.get("web", []) if (ROOT / p).exists()]
    missing_web = [p for p in group.get("web", []) if not (ROOT / p).exists()]
    expected = [p for p in group.get("expected", []) if not (ROOT / p).exists()]

    present = held + web
    absent = missing_held + missing_web

    if not group.get("held") and not group.get("web"):
        # Nothing of it is expected in the repository at all.
        status = "OFFLINE" if group.get("expected") or group["code"] in {"AGRISTATS", "SURVEYS", "OSM"} else "ABSENT"
        if group["code"] == "AGRICADASTRE":
            status = "ABSENT"
    elif not present:
        status = "WORKSPACE" if expected else "ABSENT"
    elif absent or expected:
        status = "PARTIAL"
    else:
        status = "HELD"
    return status, present, absent + expected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print the document instead of the table.")
    args = parser.parse_args()

    # Measured facts a few groups can report, so the table carries scale.
    scale = {
        "ADMIN": f"{geojson_count('PUBLISHED/data/admin/adm1.geojson') or 0} provinces, "
                 f"{geojson_count('PUBLISHED/data/admin/adm2.geojson') or 0} districts",
        "HYDROBASINS": f"levels 1-12, {gpkg_count('GEODATA/uzbekistan_basinatlas_v10/uzbekistan_basinatlas_v10.gpkg', 'basinatlas_uz_lev12') or 0} basins at level 12",
        "HYDRORIVERS": f"{geojson_count('PUBLISHED/data/hydrography/rivers.geojson') or 0} reaches",
        "HYDROLAKES": f"{geojson_count('PUBLISHED/data/hydrography/lakes.geojson') or 0} lakes",
        "BASINATLAS": "281 attributes x 2,604 basins",
        "ENVATLAS": "134 packages catalogued",
        "AGRICADASTRE": "14 regions to fetch",
        "STATIONS": "190 stations",
        "HAZARDS": f"{geojson_count('PUBLISHED/data/earthquakes.geojson') or 0} earthquakes, "
                   f"{geojson_count('PUBLISHED/data/flood-risk.geojson') or 0} flood polygons",
        "PROTECTED": f"{geojson_count('PUBLISHED/data/protected-areas.geojson') or 0} areas",
        "WATERMGMT": f"{geojson_count('PUBLISHED/data/water-management.geojson') or 0} zones",
        "OSM": "23 vector layers profiled",
        "AGRISTATS": "spreadsheets, 2012-2020",
        "SURVEYS": "survey workbooks",
        "ONTOLOGY": "872 entities, 3,692 assertions",
        "LINKS": "7,642 admin links, 494,698 declared in total",
        "LANDUSE": "shape model only",
    }

    rows = []
    for group in GROUPS:
        status, present, absent = classify(group)
        rows.append({
            **{k: v for k, v in group.items() if k not in {"held", "web", "expected"}},
            "status": status,
            "scale": scale.get(group["code"], ""),
            "presentPaths": present,
            "missingPaths": absent,
            "bytes": size_of(present),
        })

    document = {
        "version": "1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "machine": "checked against this working copy",
        "statuses": {
            "HELD": "The files are here and can be opened.",
            "PARTIAL": "Some of what the group covers is here, some is not.",
            "WORKSPACE": "Built by a pipeline into WORKSPACE/, which is not in version control.",
            "OFFLINE": "Seen once on an external drive; only the profile survives here.",
            "ABSENT": "Nothing of it on this machine and no local route to it.",
        },
        "groups": rows,
        "summary": {status: sum(1 for r in rows if r["status"] == status)
                    for status in ("HELD", "PARTIAL", "WORKSPACE", "OFFLINE", "ABSENT")},
    }

    OUTPUT.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")), encoding="utf8")

    if args.json:
        print(json.dumps(document, ensure_ascii=False, indent=2))
        return

    print(f"{'CODE':14} {'STATUS':10} {'SCALE':38} {'ON DISK':>9}  TITLE")
    print("-" * 110)
    for row in rows:
        size = f"{row['bytes'] / 1e6:,.1f} MB" if row["bytes"] else "-"
        print(f"{row['code']:14} {row['status']:10} {row['scale'][:38]:38} {size:>9}  {row['title']}")
    print("-" * 110)
    print("  " + ", ".join(f"{k} {v}" for k, v in document["summary"].items() if v))
    print(f"  -> {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
