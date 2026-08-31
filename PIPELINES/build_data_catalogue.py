"""Assemble the dataset catalogue the portal's inventory page reads.

The stored graph already knows what every dataset is, what it measures and where
it came from, but it holds that as 3,692 separate assertions. Reading it as a
catalogue means pivoting those onto the datasets they describe, which is what
this does.

The part worth being careful about is availability. A distribution's ``url``
records where a file is *meant* to be served from, not whether it is there: most
of the atlas derivatives live in WORKSPACE/, which is deliberately not in version
control, so in a fresh checkout their URLs resolve to the SPA fallback — HTML,
with a 200, which a client parsing JSON will not notice. Availability is
therefore decided by looking on disk, never by trusting the field, and every
dataset lands in one of four states:

    published    the file is in PUBLISHED/ and the portal really serves it
    repository   a source delivery under GEODATA/, present but not web-facing
    workspace    declared, but absent here — it lives in the untracked workspace
    offline      only ever seen on an external drive, and recorded from a profile

Nothing is dropped for being unavailable. A dataset that exists only as a path on
someone's desktop is still part of the scope, and the catalogue is more useful for
saying so than for hiding it.
"""

from __future__ import annotations

import collections
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTANCES = ROOT / "ONTOLOGY" / "instances"
VOCAB = ROOT / "ONTOLOGY" / "vocab"
PUBLISHED = ROOT / "PUBLISHED"
OUTPUT = PUBLISHED / "data" / "data-catalogue.json"

# Roles that describe a file held somewhere other than this repository. They are
# what the external inventories profiled, and they stay in the catalogue as
# scope even though nothing here can open them.
EXTERNAL_ROLES = {"external-table", "external-vector", "external-archive", "external-document"}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf8"))


def concepts(name: str) -> dict:
    """A vocabulary keyed by concept id."""
    document = load(VOCAB / f"{name}.json")
    return {entry["id"]: entry for entry in document["concepts"]}


def main() -> None:
    entities = load(INSTANCES / "entities.json")["entities"]
    assertions = load(INSTANCES / "assertions.json")["assertions"]

    by_id = {entity["id"]: entity for entity in entities}
    datasets = [entity for entity in entities if entity["type"] == "Dataset"]
    layers = [entity for entity in entities if entity["type"] == "MapLayer"]
    stations = [entity for entity in entities if entity["type"] == "MonitoringStation"]

    themes = concepts("themes")
    properties = concepts("properties")
    places = concepts("places")
    usecases = concepts("usecases")
    analysis = concepts("analysis")

    # Pivot the assertions onto their subject once, rather than scanning the list
    # again for every dataset.
    facts: dict[str, dict[str, list]] = collections.defaultdict(lambda: collections.defaultdict(list))
    for assertion in assertions:
        target = assertion.get("object") if assertion.get("object") is not None else assertion.get("value")
        facts[assertion["subject"]][assertion["predicate"]].append(target)

    external_paths = {
        subject: values[0]
        for subject, predicates in facts.items()
        for predicate, values in predicates.items()
        if predicate == "uz:externalLocation" and values
    }

    # Which external inventory a path came from, so a missing file can be traced
    # back to the drive it was profiled on.
    inventories = []
    path_origin: dict[str, str] = {}
    for name in ("maps-drop", "earth-engine"):
        document = load(INSTANCES / "external" / f"{name}.json")
        inventories.append({
            "id": document["name"],
            "source": document["source"],
            "profiledAt": document["profiledAt"],
            "files": document["counts"]["files"],
            "bytes": document["counts"]["bytes"],
            "byKind": {kind: len(items) if isinstance(items, list) else items
                       for kind, items in document["byKind"].items()},
        })
        root = document["source"].replace("\\", "/").rstrip("/")
        path_origin[root] = document["name"]

    def origin_of(path: str | None) -> str | None:
        if not path:
            return None
        normalised = str(path).replace("\\", "/")
        for root, name in path_origin.items():
            if normalised.lower().startswith(root.lower()):
                return name
        return None

    def describe_distribution(dist_id: str) -> dict | None:
        entity = by_id.get(dist_id)
        if entity is None:
            return None
        url = entity.get("url")
        external = external_paths.get(dist_id)
        # Presence is a filesystem question. A URL under /data/ maps into
        # PUBLISHED/; anything else is only a claim until something is found.
        present = False
        if url and url.startswith("/"):
            present = (PUBLISHED / url.lstrip("/")).exists()
        if entity.get("role") in EXTERNAL_ROLES:
            state = "offline"
        elif present:
            state = "published"
        elif url:
            state = "workspace"
        elif external:
            state = "offline"
        else:
            state = "workspace"
        return {
            "id": dist_id,
            "label": entity.get("label"),
            "role": entity.get("role"),
            "format": entity.get("format"),
            "bytes": entity.get("byteSize"),
            "url": url,
            "accessPolicy": entity.get("accessPolicy"),
            "externalPath": external,
            "inventory": origin_of(external),
            "availability": state,
        }

    # A dataset is as available as its best distribution: if anything about it is
    # actually served, that is what a reader can reach today.
    RANK = {"published": 0, "repository": 1, "workspace": 2, "offline": 3}

    def label_of(vocabulary: dict, concept_id: str) -> dict:
        entry = vocabulary.get(concept_id)
        return {"id": concept_id, "label": entry["prefLabel"] if entry else concept_id}

    catalogue = []
    for dataset in datasets:
        own = facts.get(dataset["id"], {})
        distributions = [d for d in (describe_distribution(i) for i in own.get("uz:hasDistribution", [])) if d]
        # Deduplicate: the graph can assert the same distribution twice.
        seen = set()
        unique = []
        for entry in distributions:
            if entry["id"] in seen:
                continue
            seen.add(entry["id"])
            unique.append(entry)
        distributions = unique

        availability = min((d["availability"] for d in distributions), key=lambda s: RANK[s], default="workspace")
        temporal = own.get("uz:temporalCoverage", [None])[0]
        extent = own.get("uz:spatialExtent", [None])[0]

        catalogue.append({
            "id": dataset["id"],
            "label": dataset.get("label"),
            "labels": dataset.get("labels"),
            "description": dataset.get("description"),
            "atlasNumber": dataset.get("atlasNumber"),
            "catalogId": dataset.get("catalogId"),
            "theme": (label_of(themes, own["uz:belongsToTheme"][0]) if own.get("uz:belongsToTheme") else None),
            "analysis": (label_of(analysis, own["uz:hasAnalysisConcept"][0]) if own.get("uz:hasAnalysisConcept") else None),
            "observes": [label_of(properties, p) for p in own.get("uz:observes", [])],
            "places": [label_of(places, p) for p in own.get("uz:coversPlace", [])],
            "useCases": [label_of(usecases, u) for u in own.get("uz:supportsUseCase", [])],
            "temporal": temporal,
            "spatialExtent": extent,
            "quality": own.get("uz:qualityFlag", []),
            "license": (own.get("uz:license") or [None])[0],
            "attribution": (own.get("uz:attributedTo") or [None])[0],
            "availability": availability,
            "distributions": distributions,
            "bytes": sum(d["bytes"] or 0 for d in distributions),
        })

    catalogue.sort(key=lambda row: (RANK[row["availability"]], row["label"] or ""))

    # Map layers the portal actually renders, checked the same way.
    layer_rows = []
    for layer in layers:
        url = layer.get("url")
        layer_rows.append({
            "id": layer["id"],
            "label": layer.get("label"),
            "geometryType": layer.get("geometryType"),
            "featureCount": layer.get("featureCount"),
            "url": url,
            "available": bool(url and (PUBLISHED / url.lstrip("/")).exists()),
        })

    # Gaps, computed rather than guessed: a concept nothing observes is a hole in
    # the coverage, and it is only visible by subtracting what is used from what
    # the vocabulary defines.
    observed = {p for row in catalogue for p in (c["id"] for c in row["observes"])}
    covered_places = {p for row in catalogue for p in (c["id"] for c in row["places"])}
    served_usecases = {u for row in catalogue for u in (c["id"] for c in row["useCases"])}

    availability_counts = collections.Counter(row["availability"] for row in catalogue)
    theme_counts = collections.Counter(row["theme"]["label"] for row in catalogue if row["theme"])

    gaps = {
        "datasetsWithoutTheme": [r["id"] for r in catalogue if not r["theme"]],
        "datasetsWithoutObservedProperty": [r["id"] for r in catalogue if not r["observes"]],
        "datasetsWithoutDistribution": [r["id"] for r in catalogue if not r["distributions"]],
        "datasetsWithoutTemporalCoverage": [r["id"] for r in catalogue if not r["temporal"]],
        "datasetsWithoutLicense": [r["id"] for r in catalogue if not r["license"]],
        "propertiesWithoutData": [{"id": i, "label": e["prefLabel"], "theme": e.get("broader")}
                                  for i, e in properties.items() if i not in observed],
        "placesWithoutData": [{"id": i, "label": e["prefLabel"]} for i, e in places.items() if i not in covered_places],
        "useCasesWithoutData": [{"id": i, "label": e["prefLabel"]} for i, e in usecases.items() if i not in served_usecases],
        "qualityFlags": dict(collections.Counter(flag for r in catalogue for flag in r["quality"])),
    }

    document = {
        "version": "1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": {
            "datasets": len(catalogue),
            "distributions": sum(len(r["distributions"]) for r in catalogue),
            "stations": len(stations),
            "mapLayers": len(layer_rows),
            "availability": dict(availability_counts),
            "byTheme": dict(theme_counts.most_common()),
            "offlineBytes": sum(d["bytes"] or 0 for r in catalogue for d in r["distributions"]
                                if d["availability"] == "offline"),
            "vocabulary": {
                "themes": len(themes), "properties": len(properties), "places": len(places),
                "useCases": len(usecases), "analysisConcepts": len(analysis),
            },
        },
        "themes": [{"id": i, "label": e["prefLabel"], "definition": e.get("definition"),
                    "datasets": theme_counts.get(e["prefLabel"], 0)} for i, e in themes.items()],
        "inventories": inventories,
        "datasets": catalogue,
        "layers": layer_rows,
        "gaps": gaps,
    }

    OUTPUT.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")), encoding="utf8")

    print(f"{len(catalogue):,} datasets, {document['summary']['distributions']:,} distributions "
          f"-> {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size / 1024:,.0f} KB)")
    print("  availability: " + ", ".join(f"{k} {v}" for k, v in availability_counts.most_common()))
    print(f"  offline volume: {document['summary']['offlineBytes'] / 1e9:.2f} GB across "
          f"{len(inventories)} profiled drives")
    print(f"  gaps: {len(gaps['propertiesWithoutData'])} properties and "
          f"{len(gaps['placesWithoutData'])} places with no dataset")


if __name__ == "__main__":
    main()
