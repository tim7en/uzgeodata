"""Publish the wastewater treatment plants discharging into the Amu and Syr systems.

This is the bridge from water quantity to water quality. Everything the project
measured before this describes how much water there is; HydroWASTE describes what
is put into it, and where. Each plant is co-registered by its source to the
HydroRIVERS reach receiving its outfall, so a plant reaches a basin in two hops
through links this project already publishes: plant to reach here, reach to
level-12 basin in river-basin-unified.csv.

The dilution factor is the reason the layer is worth holding. It is the ratio of
the receiving reach's natural discharge to the effluent discharge, so it says how
much water there is to absorb what a city releases — the first-order contamination
pressure downstream of Tashkent, Samarkand or Dushanbe.

One caveat travels with every Central Asian row and is recorded in the manifest
rather than hidden: these plants come from HydroWASTE's source 12, "remaining
countries", which means they are inferred from urban population, not reported by
a national register. The quality codes are published per plant so a reader can
see which number was reported and which was modelled.

    python PIPELINES/build_basin_wastewater.py
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hydrosheds_sources  # noqa: E402  (path set above)

ROOT = Path(__file__).resolve().parent.parent
PUBLISHED_DIR = ROOT / "PUBLISHED/data/hydroclimate"
REACHES = ROOT / "PUBLISHED/data/hydrography/rivers-unified.csv"
REACH_BASIN = ROOT / "PUBLISHED/data/hydrography/river-basin-unified.csv"

TABLE = PUBLISHED_DIR / "wastewater-plants-transboundary.csv"
GEOJSON = PUBLISHED_DIR / "wastewater-plants-transboundary.geojson"
REACH_LINKS = PUBLISHED_DIR / "wastewater-reach-links.csv"
BASIN_LINKS = PUBLISHED_DIR / "wastewater-basin-links.csv"
MANIFEST = PUBLISHED_DIR / "wastewater-plants-transboundary.manifest.json"

SOURCE_ID = "hydrowaste-2026"
SOURCE_ASSET = "HydroWASTE v1.0"
CSV_PATH = "HydroWASTE_v10/HydroWASTE_v10.csv"
# The delivered CSV is not UTF-8: plant names carry Latin-1 accented bytes.
ENCODING = "latin-1"

# HydroWASTE publishes a quality code beside every estimated attribute. Decoding
# them here is what lets the portal say "modelled" instead of quietly presenting
# an inferred population as a measured one.
QUAL_POP = {"1": "reported as population served", "2": "reported as population equivalent",
            "3": "estimated, discharge available", "4": "estimated, no discharge available"}
QUAL_WASTE = {"1": "reported as treated", "2": "reported as design capacity",
              "3": "reported, type not identified", "4": "estimated"}
QUAL_LEVEL = {"1": "reported", "2": "estimated"}
QUAL_LOC = {"1": "high", "2": "medium", "3": "low", "4": "not analysed"}

TABLE_FIELDS = [
    "plant_id", "name", "country", "country_iso", "status", "treatment_level",
    "population_served", "wastewater_discharge_m3_d", "design_capacity",
    "dilution_factor", "river_discharge_cms", "outfall_longitude",
    "outfall_latitude", "plant_longitude", "plant_latitude", "hyriv_id",
    "system_id", "hybas_id_level12", "in_headwater_formation",
    "location_quality", "population_quality", "discharge_quality",
    "treatment_level_quality", "reported_by_register", "source_asset", "retrieved_at",
]
REACH_LINK_FIELDS = [
    "plant_id", "hyriv_id", "system_id", "dilution_factor",
    "wastewater_discharge_m3_d", "river_discharge_cms", "population_served",
    "method", "retrieved_at",
]
BASIN_LINK_FIELDS = [
    "plant_id", "system_id", "basin_level", "hybas_id", "hyriv_id",
    "wastewater_discharge_m3_d", "population_served", "method", "retrieved_at",
]


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def write_json(path: Path, payload: object, indent: int | None = None) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=indent,
                  separators=(",", ":") if indent is None else None)
        handle.write("\n")
    os.replace(temporary, path)


def number(value):
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return None if result != result else result


def decimal(value, places: int) -> str:
    result = number(value)
    return "" if result is None else f"{result:.{places}f}"


def read_reaches() -> dict[int, dict]:
    with REACHES.open(encoding="utf-8", newline="") as handle:
        return {int(row["HYRIV_ID"]): row for row in csv.DictReader(handle)}


def read_reach_basins() -> dict[int, int]:
    """Reach to level-12 basin, from the link table the project already publishes."""
    if not REACH_BASIN.exists():
        return {}
    with REACH_BASIN.open(encoding="utf-8", newline="") as handle:
        return {
            int(row["river_id"]): int(row["basin_id"])
            for row in csv.DictReader(handle)
            if row.get("basin_id") and row["basin_id"] != "0"
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    source = hydrosheds_sources.require(
        CSV_PATH,
        hint="HydroWASTE v1.0; free at https://www.hydrosheds.org/products/hydrowaste.",
        source_id=SOURCE_ID,
    )
    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    reaches = read_reaches()
    reach_basin = read_reach_basins()
    print(f"Wastewater | frame: {len(reaches):,} reaches, {len(reach_basin):,} reach-to-basin links")

    with source.open(encoding=ENCODING, newline="") as handle:
        plants = list(csv.DictReader(handle))
    print(f"  {len(plants):,} plants in {SOURCE_ASSET}")

    rows, features, reach_links, basin_links = [], [], [], []
    for plant in plants:
        raw = (plant.get("HYRIV_ID") or "").strip()
        if not raw:
            continue
        try:
            reach_id = int(float(raw))
        except ValueError:
            continue
        reach = reaches.get(reach_id)
        if reach is None:
            continue

        plant_id = int(float(plant["WASTE_ID"]))
        system_id = reach["system_id"]
        basin_id = reach_basin.get(reach_id) or int(reach["HYBAS_L12"])
        formation = int(reach.get("in_headwater_formation") or 0)
        discharge = decimal(plant.get("WASTE_DIS"), 3)
        population = "" if number(plant.get("POP_SERVED")) is None else f"{int(number(plant['POP_SERVED']))}"
        dilution = decimal(plant.get("DF"), 3)
        river_discharge = decimal(plant.get("RIVER_DIS"), 4)
        longitude, latitude = number(plant.get("LON_OUT")), number(plant.get("LAT_OUT"))

        rows.append({
            "plant_id": plant_id,
            "name": (plant.get("WWTP_NAME") or "").strip(),
            "country": (plant.get("COUNTRY") or "").strip(),
            "country_iso": (plant.get("CNTRY_ISO") or "").strip(),
            "status": (plant.get("STATUS") or "").strip(),
            "treatment_level": (plant.get("LEVEL") or "").strip(),
            "population_served": population,
            "wastewater_discharge_m3_d": discharge,
            "design_capacity": decimal(plant.get("DESIGN_CAP"), 2),
            "dilution_factor": dilution,
            "river_discharge_cms": river_discharge,
            "outfall_longitude": "" if longitude is None else f"{longitude:.5f}",
            "outfall_latitude": "" if latitude is None else f"{latitude:.5f}",
            "plant_longitude": decimal(plant.get("LON_WWTP"), 5),
            "plant_latitude": decimal(plant.get("LAT_WWTP"), 5),
            "hyriv_id": reach_id,
            "system_id": system_id,
            "hybas_id_level12": basin_id,
            "in_headwater_formation": formation,
            "location_quality": QUAL_LOC.get((plant.get("QUAL_LOC") or "").strip(), ""),
            "population_quality": QUAL_POP.get((plant.get("QUAL_POP") or "").strip(), ""),
            "discharge_quality": QUAL_WASTE.get((plant.get("QUAL_WASTE") or "").strip(), ""),
            "treatment_level_quality": QUAL_LEVEL.get((plant.get("QUAL_LEVEL") or "").strip(), ""),
            # Source 12 is HydroWASTE's residual bucket: no national register
            # supplied the plant, so it was inferred from urban population.
            "reported_by_register": int((plant.get("SOURCE") or "").strip() != "12"),
            "source_asset": SOURCE_ASSET,
            "retrieved_at": retrieved,
        })

        reach_links.append({
            "plant_id": plant_id, "hyriv_id": reach_id, "system_id": system_id,
            "dilution_factor": dilution, "wastewater_discharge_m3_d": discharge,
            "river_discharge_cms": river_discharge, "population_served": population,
            "method": "native HydroWASTE HYRIV_ID at the estimated outfall",
            "retrieved_at": retrieved,
        })
        basin_links.append({
            "plant_id": plant_id, "system_id": system_id, "basin_level": 12,
            "hybas_id": basin_id, "hyriv_id": reach_id,
            "wastewater_discharge_m3_d": discharge, "population_served": population,
            "method": "outfall reach resolved to its level-12 basin",
            "retrieved_at": retrieved,
        })

        if longitude is not None and latitude is not None:
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(longitude, 5), round(latitude, 5)]},
                "properties": {key: rows[-1][key] for key in (
                    "plant_id", "name", "country", "treatment_level",
                    "population_served", "wastewater_discharge_m3_d",
                    "dilution_factor", "river_discharge_cms", "hyriv_id",
                    "system_id", "hybas_id_level12", "reported_by_register")},
            })

    rows.sort(key=lambda row: -(float(row["population_served"] or 0)))
    reach_links.sort(key=lambda row: -(float(row["population_served"] or 0)))
    write_csv(TABLE, TABLE_FIELDS, rows)
    write_csv(REACH_LINKS, REACH_LINK_FIELDS, reach_links)
    write_csv(BASIN_LINKS, BASIN_LINK_FIELDS, basin_links)
    write_json(GEOJSON, {"type": "FeatureCollection", "features": features})

    dilutions = sorted(float(row["dilution_factor"]) for row in rows if row["dilution_factor"])
    served = sum(float(row["population_served"] or 0) for row in rows)
    effluent = sum(float(row["wastewater_discharge_m3_d"] or 0) for row in rows)
    manifest = {
        "version": "1.0",
        "generatedAt": retrieved,
        "observationClass": "inventory",
        "spatialScope": "full_basin",
        "source": {
            "asset": SOURCE_ASSET,
            "container": str(source.relative_to(ROOT)).replace("\\", "/"),
            "selection": "outfall reach present in the published Amu and Syr river network",
            "license": "CC-BY-4.0",
        },
        "counts": {
            "plants": len(rows),
            "named": sum(1 for row in rows if row["name"]),
            "reportedByRegister": sum(1 for row in rows if row["reported_by_register"] == 1),
            "withDilutionFactor": len(dilutions),
            "reachLinks": len(reach_links),
            "basinLinks": len(basin_links),
            "distinctBasins": len({row["hybas_id"] for row in basin_links}),
            "inHeadwaterFormation": sum(1 for row in rows if row["in_headwater_formation"] == 1),
        },
        "populationServed": int(served),
        "effluentM3PerDay": round(effluent, 1),
        "dilutionFactor": {
            "min": dilutions[0] if dilutions else None,
            "median": dilutions[len(dilutions) // 2] if dilutions else None,
            "max": dilutions[-1] if dilutions else None,
            "below10": sum(1 for value in dilutions if value < 10),
        },
        "byCountry": dict(Counter(row["country"] for row in rows if row["country"]).most_common()),
        "byTreatmentLevel": dict(Counter(row["treatment_level"] for row in rows if row["treatment_level"]).most_common()),
        "largestPlants": [
            {
                "id": int(row["plant_id"]),
                "name": row["name"] or None,
                "country": row["country"] or None,
                "populationServed": int(float(row["population_served"])) if row["population_served"] else None,
                "effluentM3PerDay": float(row["wastewater_discharge_m3_d"]) if row["wastewater_discharge_m3_d"] else None,
                "dilutionFactor": float(row["dilution_factor"]) if row["dilution_factor"] else None,
                "outfall": [float(row["outfall_longitude"]), float(row["outfall_latitude"])]
                           if row["outfall_longitude"] else None,
                "system": row["system_id"],
            }
            for row in rows[:15]
        ],
        "outputs": {
            "csv": str(TABLE.relative_to(ROOT)).replace("\\", "/"),
            "geojson": str(GEOJSON.relative_to(ROOT)).replace("\\", "/"),
            "reachLinkCSV": str(REACH_LINKS.relative_to(ROOT)).replace("\\", "/"),
            "basinLinkCSV": str(BASIN_LINKS.relative_to(ROOT)).replace("\\", "/"),
        },
        "qualityNotes": [
            "Every plant in this selection comes from HydroWASTE source 12, 'remaining "
            "countries'. None was supplied by a national register: the plant is inferred "
            "from urban population, its discharge and treatment level are modelled, and no "
            "record carries a name. reported_by_register is 0 on every row for that reason. "
            "Treat this as a modelled pressure surface, not an inventory of real plants.",
            "The outfall is an estimated location, not a surveyed one. It is what carries "
            "the reach association, so a misplaced outfall moves the plant to the wrong "
            "reach and with it the dilution factor.",
            "The dilution factor uses long-term average natural discharge. In a basin this "
            "heavily abstracted the water actually present in an irrigation season is far "
            "less than the natural average, so these values are optimistic - the real "
            "dilution downstream of a city in August is worse than the number here.",
            "A plant with no dilution factor discharges to an endorheic sink or a large "
            "lake, where the ratio is undefined rather than missing.",
        ],
    }
    write_json(MANIFEST, manifest, indent=1)

    print(f"  {len(rows):,} plants | {int(served):,} people served | {effluent:,.0f} m3/d effluent")
    print(f"  links: {len(reach_links):,} reach, {len(basin_links):,} basin "
          f"over {manifest['counts']['distinctBasins']:,} basins")
    if dilutions:
        print(f"  dilution factor: min {dilutions[0]:,.1f} | median "
              f"{manifest['dilutionFactor']['median']:,.1f} | {manifest['dilutionFactor']['below10']} below 10")
    for entry in manifest["largestPlants"][:6]:
        print(f"    {str(entry['country'])[:12]:12} {entry['populationServed'] or 0:>9,} served  "
              f"DF {entry['dilutionFactor'] or 0:>9,.1f}  at {entry['outfall']}")
    print(f"  wrote {TABLE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
