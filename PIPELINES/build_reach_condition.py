"""Publish what each Amu and Syr reach *is* and how far it is still connected.

Two global companions to HydroRIVERS, read over the same 46,976 reaches the
project already publishes:

  GloRiC  a hydrologic, physio-climatic and geomorphic type for every reach,
          plus the combined reach type and a k-means grouping.
  FFR     the Connectivity Status Index and the six pressures behind it —
          fragmentation, flow regulation, sediment trapping, water consumption,
          urbanisation and roads.

Neither uses the column name HYRIV_ID. GloRiC calls it Reach_ID and FFR calls it
REACH_ID, and neither technical document states that these are the same
identifier — GloRiC was built on an unpublished beta of RiverATLAS, so the
correspondence was plausible but unproven. This build therefore verifies it
instead of assuming it: it counts how many of the published reaches each source
resolves and refuses to write a partial table. Both currently match all 46,976.

    python PIPELINES/build_reach_condition.py
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

import pyogrio

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hydrosheds_sources  # noqa: E402  (path set above)

ROOT = Path(__file__).resolve().parent.parent
PUBLISHED_DIR = ROOT / "PUBLISHED/data/hydroclimate"
REACHES = ROOT / "PUBLISHED/data/hydrography/rivers-unified.csv"

CLASSIFICATION = PUBLISHED_DIR / "reach-classification.csv"
CONNECTIVITY = PUBLISHED_DIR / "reach-connectivity.csv"
MANIFEST = PUBLISHED_DIR / "reach-condition.manifest.json"

SOURCE_ID = "hydrosheds-associated-2026"
GLORIC = "GloRiC_v10/GloRiC_v10_shapefile/GloRiC_v10.shp"
FFR = "FFR_v1/Mapping the worlds free-flowing rivers_Data_Geodatabase/FFR_river_network.gdb"
FFR_LAYER = "FFR_river_network_v1"

# The two systems sit well inside this box; reading by bounding box keeps an
# 8.5-million-reach global layer down to about 130,000 rows.
BBOX = (58.0, 34.0, 79.0, 48.0)

# Below this share of reaches the identifier correspondence is not what the
# source claims and the table would be silently partial, so the build stops.
MATCH_THRESHOLD = 0.99

GLORIC_COLUMNS = ["Reach_ID", "Log_Q_avg", "Log_Q_var", "Class_hydr", "Temp_min",
                  "CMI_indx", "Log_elev", "Class_phys", "Lake_wet", "Stream_pow",
                  "Class_geom", "Reach_type", "Kmeans_30"]
FFR_COLUMNS = ["REACH_ID", "COUNTRY", "BAS_NAME", "RIV_ORD", "DIS_AV_CMS",
               "DOF", "DOR", "SED", "USE", "URB", "RDD", "FLD", "CSI",
               "CSI_FF1", "CSI_FF2", "BB_ID", "BB_NAME", "BB_LEN_KM"]

CLASSIFICATION_FIELDS = [
    "hyriv_id", "system_id", "in_national_extraction", "hybas_id_level12",
    "hydrologic_class", "physio_climatic_class", "geomorphic_class",
    "reach_type", "kmeans_group", "log_mean_discharge", "log_discharge_variance",
    "min_temperature_c", "climate_moisture_index", "log_elevation",
    "lake_wetland_class", "stream_power", "source_asset", "retrieved_at",
]
CONNECTIVITY_FIELDS = [
    "hyriv_id", "system_id", "in_national_extraction", "hybas_id_level12",
    "connectivity_status_index", "free_flowing_class", "free_flowing_class_3",
    "degree_of_fragmentation", "degree_of_regulation", "sediment_trapping",
    "water_consumption", "urbanisation", "road_density", "floodplain_index",
    "river_order", "average_discharge_cms", "basin_name", "backbone_river",
    "backbone_length_km", "source_asset", "retrieved_at",
]

# FFR's own three-way reading of CSI, kept as words so the table is legible
# without the technical documentation open beside it.
FREE_FLOWING = {1: "free-flowing", 2: "good connectivity", 3: "impacted"}


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
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if result != result else result


def decimal(value, places: int) -> str:
    result = number(value)
    return "" if result is None else f"{result:.{places}f}"


def integer(value) -> str:
    result = number(value)
    return "" if result is None else str(int(result))


def text(value) -> str:
    cleaned = str(value).strip() if value is not None else ""
    return "" if cleaned in {"", "None", "nan", "NULL", "<Null>"} else cleaned


def read_reaches() -> dict[int, dict]:
    with REACHES.open(encoding="utf-8", newline="") as handle:
        return {int(row["HYRIV_ID"]): row for row in csv.DictReader(handle)}


def check_match(name: str, matched: int, total: int) -> float:
    """Verify a source's identifier really is HYRIV_ID before trusting its rows."""
    share = matched / total if total else 0.0
    print(f"  {name}: {matched:,} of {total:,} published reaches resolved ({share:.1%})")
    if share < MATCH_THRESHOLD:
        raise SystemExit(
            f"{name} resolved only {share:.1%} of the published reaches. Its identifier "
            f"column is not HYRIV_ID after all, so the table would be silently partial. "
            f"Nothing was written."
        )
    return share


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    gloric = hydrosheds_sources.require(
        GLORIC, hint="GloRiC v1.0 shapefile; free at https://www.hydrosheds.org/products/gloric.",
        source_id=SOURCE_ID)
    ffr = hydrosheds_sources.require(
        FFR, hint="Free-Flowing Rivers v1.0; free at https://doi.org/10.6084/m9.figshare.7688801.",
        source_id=SOURCE_ID)

    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    reaches = read_reaches()
    print(f"Reach condition | {len(reaches):,} published reaches in the Amu and Syr systems")

    frame = pyogrio.read_dataframe(str(gloric), bbox=BBOX, columns=GLORIC_COLUMNS, read_geometry=False)
    print(f"  GloRiC: {len(frame):,} reaches in the bounding box")
    classification = []
    for record in frame.itertuples(index=False):
        reach_id = int(record.Reach_ID)
        reach = reaches.get(reach_id)
        if reach is None:
            continue
        classification.append({
            "hyriv_id": reach_id,
            "system_id": reach["system_id"],
            "in_national_extraction": reach["in_national_extraction"],
            "hybas_id_level12": reach["HYBAS_L12"],
            "hydrologic_class": integer(record.Class_hydr),
            "physio_climatic_class": integer(record.Class_phys),
            "geomorphic_class": integer(record.Class_geom),
            "reach_type": integer(record.Reach_type),
            "kmeans_group": integer(record.Kmeans_30),
            "log_mean_discharge": decimal(record.Log_Q_avg, 4),
            "log_discharge_variance": decimal(record.Log_Q_var, 4),
            "min_temperature_c": decimal(record.Temp_min, 2),
            "climate_moisture_index": decimal(record.CMI_indx, 4),
            "log_elevation": decimal(record.Log_elev, 4),
            "lake_wetland_class": integer(record.Lake_wet),
            "stream_power": decimal(record.Stream_pow, 4),
            "source_asset": "GloRiC v1.0",
            "retrieved_at": retrieved,
        })
    gloric_share = check_match("GloRiC Reach_ID", len(classification), len(reaches))

    frame = pyogrio.read_dataframe(str(ffr), layer=FFR_LAYER, bbox=BBOX,
                                   columns=FFR_COLUMNS, read_geometry=False)
    print(f"  FFR: {len(frame):,} reaches in the bounding box")
    connectivity = []
    for record in frame.itertuples(index=False):
        reach_id = int(record.REACH_ID)
        reach = reaches.get(reach_id)
        if reach is None:
            continue
        class3 = number(record.CSI_FF2)
        connectivity.append({
            "hyriv_id": reach_id,
            "system_id": reach["system_id"],
            "in_national_extraction": reach["in_national_extraction"],
            "hybas_id_level12": reach["HYBAS_L12"],
            "connectivity_status_index": decimal(record.CSI, 2),
            "free_flowing_class": integer(record.CSI_FF1),
            "free_flowing_class_3": FREE_FLOWING.get(int(class3), "") if class3 is not None else "",
            "degree_of_fragmentation": decimal(record.DOF, 2),
            "degree_of_regulation": decimal(record.DOR, 2),
            "sediment_trapping": decimal(record.SED, 2),
            "water_consumption": decimal(record.USE, 2),
            "urbanisation": decimal(record.URB, 2),
            "road_density": decimal(record.RDD, 2),
            "floodplain_index": decimal(record.FLD, 2),
            "river_order": integer(record.RIV_ORD),
            "average_discharge_cms": decimal(record.DIS_AV_CMS, 4),
            "basin_name": text(record.BAS_NAME),
            "backbone_river": text(record.BB_NAME),
            "backbone_length_km": decimal(record.BB_LEN_KM, 2),
            "source_asset": "Free-Flowing Rivers v1.0",
            "retrieved_at": retrieved,
        })
    ffr_share = check_match("FFR REACH_ID", len(connectivity), len(reaches))

    classification.sort(key=lambda row: row["hyriv_id"])
    connectivity.sort(key=lambda row: row["hyriv_id"])
    write_csv(CLASSIFICATION, CLASSIFICATION_FIELDS, classification)
    write_csv(CONNECTIVITY, CONNECTIVITY_FIELDS, connectivity)

    csi = [float(row["connectivity_status_index"]) for row in connectivity
           if row["connectivity_status_index"]]
    national = [row for row in connectivity if row["in_national_extraction"] == "1"]
    national_csi = [float(row["connectivity_status_index"]) for row in national
                    if row["connectivity_status_index"]]
    manifest = {
        "version": "1.0",
        "generatedAt": retrieved,
        "observationClass": "classification",
        "spatialScope": "full_basin",
        "sources": [
            {"asset": "GloRiC v1.0",
             "container": str(gloric.relative_to(ROOT)).replace("\\", "/"),
             "identifierColumn": "Reach_ID", "matchedShare": round(gloric_share, 4),
             "license": "hydrosheds-license-agreement"},
            {"asset": "Free-Flowing Rivers v1.0",
             "container": str(ffr.relative_to(ROOT)).replace("\\", "/"),
             "identifierColumn": "REACH_ID", "matchedShare": round(ffr_share, 4),
             "license": "hydrosheds-license-agreement"},
        ],
        "counts": {
            "publishedReaches": len(reaches),
            "classifiedReaches": len(classification),
            "connectivityReaches": len(connectivity),
            "nationalReaches": len(national),
        },
        "connectivityStatusIndex": {
            "meanAllReaches": round(sum(csi) / len(csi), 2) if csi else None,
            "meanNationalReaches": round(sum(national_csi) / len(national_csi), 2) if national_csi else None,
            "min": round(min(csi), 2) if csi else None,
        },
        "freeFlowing": dict(Counter(row["free_flowing_class_3"] for row in connectivity
                                    if row["free_flowing_class_3"]).most_common()),
        "reachTypes": len({row["reach_type"] for row in classification if row["reach_type"]}),
        "outputs": {
            "classificationCSV": str(CLASSIFICATION.relative_to(ROOT)).replace("\\", "/"),
            "connectivityCSV": str(CONNECTIVITY.relative_to(ROOT)).replace("\\", "/"),
        },
        "qualityNotes": [
            "GloRiC's Reach_ID and FFR's REACH_ID are not documented as equal to "
            "HydroRIVERS HYRIV_ID, and GloRiC v1.0 was built on an unpublished beta of "
            "RiverATLAS. The correspondence is therefore verified at build time rather "
            "than assumed: this build refuses to write a table when a source resolves "
            f"less than {MATCH_THRESHOLD:.0%} of the published reaches.",
            "The Connectivity Status Index is a modelled multi-criteria score, not a "
            "measurement. Its threshold of 95 per cent for 'free-flowing' is the "
            "convention of Grill et al. 2019 and is carried through unchanged.",
            "FFR was published in 2019 and GloRiC in 2018. Neither reflects a barrier "
            "built since. Rogun in particular has continued to rise, so the regulation "
            "pressure on the Vakhsh is understated here.",
            "GloRiC class numbers are legend codes, not magnitudes: class 7 is not "
            "greater than class 3. Their names live in GloRiC_ClassNames_v10.xlsx beside "
            "the shapefile.",
        ],
    }
    write_json(MANIFEST, manifest, indent=1)

    print(f"  CSI: mean {manifest['connectivityStatusIndex']['meanAllReaches']} over the two systems, "
          f"{manifest['connectivityStatusIndex']['meanNationalReaches']} over the national extraction")
    print(f"  free-flowing: {manifest['freeFlowing']}")
    print(f"  {manifest['reachTypes']} distinct GloRiC reach types")
    print(f"  wrote {CLASSIFICATION.relative_to(ROOT)} and {CONNECTIVITY.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
