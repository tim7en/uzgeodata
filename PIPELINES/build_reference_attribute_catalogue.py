"""Give every atlas attribute its provenance, and bind it to the reference basins.

The 281 columns on the level-12 reference basins are not one dataset. They are 53
variables drawn from separate global products — population grids, land cover
mosaics, climate surfaces, soil and geology maps — each with its own source,
citation, licence and native grid. Publishing a number without that is publishing
an anonymous number.

The catalogue text was already parsed out of `BasinATLAS_Catalog_v10.pdf` into the
ontology vocabulary, so this joins three things that already exist rather than
re-deriving any of them:

* `ONTOLOGY/vocab/hydroatlas-attributes.json` — source, citation, licence and
  native format per variable;
* `PUBLISHED/data/hydrography/attribute-dictionary.json` — the 281 columns, their
  units, spatial extent and dimension;
* `PUBLISHED/data/hydroclimate/reference-basin-attributes.csv` — the values, one
  row per level-12 basin.

The result is addressable both ways: a column resolves to its source, and a
variable resolves to the columns and basins that carry it.

    python PIPELINES/build_reference_attribute_catalogue.py
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLISHED_DIR = ROOT / "PUBLISHED/data/hydroclimate"
DICTIONARY = ROOT / "PUBLISHED/data/hydrography/attribute-dictionary.json"
VOCABULARY = ROOT / "ONTOLOGY/vocab/hydroatlas-attributes.json"
ENTITIES = ROOT / "ONTOLOGY/instances/entities.json"
GROUPS = PUBLISHED_DIR / "reference-attribute-groups.json"
VALUES = PUBLISHED_DIR / "reference-basin-attributes.csv"
OUTPUT = PUBLISHED_DIR / "reference-attribute-catalogue.json"
MANIFEST = PUBLISHED_DIR / "reference-attribute-catalogue.manifest.json"
DATASET_ID = "uz:ds/hydrosheds-basinatlas-global"
WEBSITE = "https://www.hydrosheds.org/hydroatlas"
EXTENT_GROUPS = {"s": "basin_specific", "u": "basin_accumulation", "p": "basin_accumulation"}


def write_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temporary, path)


def parse_definition(text: str) -> dict:
    """The catalogue writes one sentence per fact; keep them as separate fields."""
    parts = {}
    source = re.search(r"Source:\s*(.+?)\.\s*(?:Units:|Native format:|$)", text or "")
    units = re.search(r"Units:\s*(.+?)\.\s*(?:Native format:|$)", text or "")
    native = re.search(r"Native format:\s*(.+?)\.?\s*$", text or "")
    if source:
        parts["source"] = source.group(1).strip()
    if units:
        parts["units"] = units.group(1).strip()
    if native:
        parts["nativeFormat"] = native.group(1).strip()
    lead = (text or "").split(". Source:")[0].strip()
    parts["description"] = lead
    return parts


def parse_note(text: str) -> dict:
    parts = {}
    catalogue = re.search(r"Catalogue\s+(\S+)\s+\((.+?)\)", text or "")
    citation = re.search(r"Citation:\s*(.+?)\.\s*(?:Licence:|Suffixes|$)", text or "")
    licence = re.search(r"Licence:\s*(.+?)\.\s*(?:Suffixes|$)", text or "")
    if catalogue:
        parts["catalogueId"] = catalogue.group(1).rstrip(".")
        parts["category"] = catalogue.group(2).strip()
    if citation:
        parts["citation"] = citation.group(1).strip()
    if licence:
        parts["licence"] = licence.group(1).strip()
    return parts


def concept_for(variable: str, unit_code: str, concepts: dict) -> dict | None:
    """`glc`, `pnv` and `wet` split into class and percent variants in the scheme."""
    for key in (f"{variable}-{unit_code}", variable):
        if key in concepts:
            return concepts[key]
    return None


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()

    dictionary = json.loads(DICTIONARY.read_text(encoding="utf-8"))
    columns = dictionary["columns"]
    vocabulary = json.loads(VOCABULARY.read_text(encoding="utf-8"))
    concepts = {entry["id"].split("/")[-1]: entry for entry in vocabulary["concepts"]}
    entities = {entry["id"]: entry for entry in json.loads(ENTITIES.read_text(encoding="utf-8"))["entities"]}
    dataset = entities.get(DATASET_ID, {})
    groups = json.loads(GROUPS.read_text(encoding="utf-8"))
    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    with VALUES.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        basin_count = sum(1 for _ in reader)

    by_variable: dict[str, list] = defaultdict(list)
    unresolved = []
    column_index = {}
    for column, meta in sorted(columns.items()):
        concept = concept_for(meta["variable"], meta["unitCode"], concepts)
        if concept is None:
            unresolved.append(column)
            continue
        code = concept["id"].split("/")[-1]
        entry = {
            "column": column,
            "label": meta["label"],
            "units": meta.get("units"),
            "spatialExtent": meta["spatialExtent"],
            "spatialExtentLabel": meta["spatialExtentLabel"],
            "dimension": meta.get("dimension"),
            "dimensionLabel": meta.get("dimensionLabel"),
            "aggregation": meta.get("aggregation"),
            "group": EXTENT_GROUPS.get(meta["spatialExtent"], "basin_specific"),
        }
        by_variable[code].append(entry)
        column_index[column] = {"variable": code, "group": entry["group"]}
    if unresolved:
        raise SystemExit(f"{len(unresolved)} columns have no catalogue entry: {unresolved[:6]}")

    variables = []
    for code, entries in sorted(by_variable.items()):
        concept = concepts[code]
        definition = parse_definition(concept.get("definition", ""))
        note = parse_note(concept.get("note", ""))
        variables.append({
            "code": code,
            "conceptId": concept["id"],
            "label": concept["prefLabel"],
            "description": definition.get("description"),
            "source": definition.get("source"),
            "nativeFormat": definition.get("nativeFormat"),
            "units": concept.get("unit") or definition.get("units"),
            "citation": note.get("citation"),
            "licence": note.get("licence"),
            "catalogueId": note.get("catalogueId"),
            "category": note.get("category"),
            "relatedProperties": concept.get("related", []),
            "columnCount": len(entries),
            "columns": sorted(entries, key=lambda item: item["column"]),
            "groups": sorted({entry["group"] for entry in entries}),
        })

    payload = {
        "version": "1.0",
        "generatedAt": retrieved,
        "scheme": {
            "title": vocabulary["title"],
            "description": vocabulary["description"],
            "reference": vocabulary["reference"],
            "catalogueSource": dictionary.get("catalogSource"),
            "website": WEBSITE,
            "dataset": {
                "id": DATASET_ID,
                "label": dataset.get("label"),
                "description": dataset.get("description"),
                "sourceKey": dataset.get("sourceKey"),
            },
            "boundTo": {
                "spatialUnit": "HydroBASINS level-12 sub-basin",
                "joinKey": "hybas_id",
                "basins": basin_count,
                "values": str(VALUES.relative_to(ROOT)).replace("\\", "/"),
                "reachJoin": ("HydroRIVERS reaches carry HYBAS_L12, so every reach inherits the "
                              "attributes of the basin it runs through"),
            },
        },
        "groups": [
            {"id": group["id"], "label": group["label"], "attributeCount": group["attributeCount"]}
            for group in groups["groups"]
        ],
        "counts": {
            "variables": len(variables),
            "columns": len(column_index),
            "basins": basin_count,
            "withCitation": sum(1 for entry in variables if entry["citation"]),
            "withLicence": sum(1 for entry in variables if entry["licence"]),
            "withSource": sum(1 for entry in variables if entry["source"]),
        },
        "categories": sorted({entry["category"] for entry in variables if entry["category"]}),
        "variables": variables,
        "columnIndex": column_index,
        "qualityNotes": [
            "Every column names the global product it came from; the atlas is a compilation, "
            "not a single measurement campaign.",
            "Licences differ between source products and are recorded per variable, not per file.",
            "Values describe a fixed reference epoch and are not a time series.",
        ],
    }
    write_json(OUTPUT, payload)
    write_json(MANIFEST, {
        "version": "1.0",
        "generatedAt": retrieved,
        "observationClass": "reference",
        "source": {
            "vocabulary": str(VOCABULARY.relative_to(ROOT)).replace("\\", "/"),
            "dictionary": str(DICTIONARY.relative_to(ROOT)).replace("\\", "/"),
            "values": str(VALUES.relative_to(ROOT)).replace("\\", "/"),
        },
        "counts": payload["counts"],
        "outputs": {"catalogue": str(OUTPUT.relative_to(ROOT)).replace("\\", "/")},
        "qualityNotes": payload["qualityNotes"],
    })
    print(f"Attribute catalogue | {len(variables)} variables over {len(column_index)} columns "
          f"on {basin_count:,} basins")
    print(f"  citation {payload['counts']['withCitation']}/{len(variables)} · "
          f"licence {payload['counts']['withLicence']}/{len(variables)} · "
          f"source {payload['counts']['withSource']}/{len(variables)}")
    print(f"  categories: {', '.join(payload['categories'])}")
    print(f"  -> {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
