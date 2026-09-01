"""Mint the Earth Engine datasets into the graph as entities and assertions.

Registering a relationship table names a dataset; it does not put it in the
ontology. Seven Earth Engine sources were being read, reduced and stored while
the graph knew nothing about them — no theme, no measured property, no licence,
no agent. Their tables hung off a slug that resolved to nothing, so a question
like "what do we hold that observes precipitation" could not reach CHIRPS, and
the catalogue could not list any of them.

This closes that. It reads ONTOLOGY/vocab/earth-engine-sources.json and writes,
for each source, a Dataset entity, an Agent for whoever produces it, and the
assertions that place it: theme, observed properties, coverage, licence,
attribution, temporal extent and any quality flag.

It is additive and idempotent. Anything it previously wrote is replaced, and
everything else in the graph is left alone — the atlas records are not this
script's to touch, and it must be safe to run after a full ontology build rather
than only before one.

    python PIPELINES/project_earth_engine_sources.py
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "ONTOLOGY" / "vocab" / "earth-engine-sources.json"
ENTITIES = ROOT / "ONTOLOGY" / "instances" / "entities.json"
ASSERTIONS = ROOT / "ONTOLOGY" / "instances" / "assertions.json"
TABLES = ROOT / "ONTOLOGY" / "vocab" / "relationship-tables.json"

AGENT = "uz:agent/earth-engine-registry"
MARK = "earth-engine-sources.json"


def assertion_id(subject: str, predicate: str, target) -> str:
    seed = f"{subject}|{predicate}|{json.dumps(target, sort_keys=True, ensure_ascii=False)}"
    return "uz:a/" + hashlib.sha256(seed.encode("utf8")).hexdigest()[:16]


def main() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf8"))["sources"]
    entity_doc = json.loads(ENTITIES.read_text(encoding="utf8"))
    assertion_doc = json.loads(ASSERTIONS.read_text(encoding="utf8"))
    tables = json.loads(TABLES.read_text(encoding="utf8"))["tables"]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    minted_ids = {f"uz:ds/{s['slug']}" for s in registry}
    minted_ids |= {s["agent"] for s in registry}
    minted_ids.add(AGENT)

    # Drop anything a previous run left, so this is a replace rather than a pile-up.
    entity_doc["entities"] = [e for e in entity_doc["entities"] if e["id"] not in minted_ids]
    assertion_doc["assertions"] = [a for a in assertion_doc["assertions"]
                                   if not (a.get("evidence") or {}).get("source", "").endswith(MARK)]

    entities, assertions = [], []

    entities.append({
        "id": AGENT, "type": "Agent",
        "label": "Earth Engine source registry",
        # "rule" in this vocabulary means a stated procedure rather than a person
        # or an organisation, which is what a hand-written registry is.
        "agentKind": "rule", "agentVersion": "1.0", "trustTier": "curated",
        "description": ("Facts written down in ONTOLOGY/vocab/earth-engine-sources.json rather "
                        "than measured from an archive: a remote collection has no bytes on disk "
                        "to profile, so its licence, producer and meaning have to be asserted."),
    })

    seen_agents = set()
    for source in registry:
        dataset = f"uz:ds/{source['slug']}"
        if source["agent"] not in seen_agents:
            seen_agents.add(source["agent"])
            entities.append({
                "id": source["agent"], "type": "Agent", "label": source["agentLabel"],
                "agentKind": "organisation", "agentVersion": None, "trustTier": "authoritative",
                "description": f"Producer of {source['label']}.",
            })

        entities.append({
            "id": dataset, "type": "Dataset", "label": source["label"],
            "labels": {"en": source["label"]},
            "sourceKey": f"earth-engine/{source['asset']}",
            "atlasNumber": None, "catalogId": None, "repositoryId": None,
            "description": source["note"],
        })

        def add(predicate, *, obj=None, value=None):
            target = obj if obj is not None else value
            record = {
                "id": assertion_id(dataset, predicate, target),
                "subject": dataset, "predicate": predicate,
                "status": "asserted", "confidence": 1.0,
                "assertedBy": AGENT, "method": "declaration",
                "generatedAt": now, "reviewedBy": None, "reviewedAt": None,
                "evidence": {"source": MARK, "note": f"Earth Engine asset {source['asset']}"},
            }
            if obj is not None:
                record["object"] = obj
            else:
                record["value"] = value
            assertions.append(record)

        add("uz:belongsToTheme", obj=source["theme"])
        add("uz:hasAnalysisConcept", obj=source["analysis"])
        for prop in source["observes"]:
            add("uz:observes", obj=prop)
        for place in source["places"]:
            add("uz:coversPlace", obj=place)
        add("uz:license", value=source["licence"])
        add("uz:attributedTo", value=source["attribution"])
        add("uz:temporalCoverage", value=source["temporal"])
        add("uz:externalLocation", value=f"earth-engine://{source['asset']}")
        for flag in source.get("qualityFlags", []):
            add("uz:qualityFlag", value=flag)
        # Tie the dataset to the tables built from it, so the graph can be walked
        # from a measurement back to what produced it and forward to where it sits.
        for table in tables:
            if table["dataset"] == source["slug"]:
                add("uz:relatedTo", obj=f"uz:dist/{table['id']}")

    entity_doc["entities"].extend(entities)
    assertion_doc["assertions"].extend(assertions)
    entity_doc["generatedAt"] = now
    assertion_doc["generatedAt"] = now

    ENTITIES.write_text(json.dumps(entity_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    ASSERTIONS.write_text(json.dumps(assertion_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf8")

    print(f"{len(registry)} Earth Engine sources projected into the graph")
    print(f"  entities   +{len(entities):>4}  -> {len(entity_doc['entities']):,} total")
    print(f"  assertions +{len(assertions):>4}  -> {len(assertion_doc['assertions']):,} total")


if __name__ == "__main__":
    main()
