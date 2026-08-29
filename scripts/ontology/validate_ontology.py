"""Validate the ontology: JSON Schema conformance plus graph integrity.

Schema validation catches malformed records. The integrity checks catch the
things a schema cannot see, and they are the reason a model is allowed to write
into this graph at all: every proposal has to survive typed predicates, resolvable
references, cardinality and provenance rules before it can be published.

Exit code is 1 if any ERROR is found. Warnings never fail the run; they are the
curation backlog.

Usage:
    python scripts/ontology/validate_ontology.py [--root .] [--strict]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.notes: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def note(self, message: str) -> None:
        self.notes.append(message)


def validate(root: Path, strict: bool = False) -> Report:
    report = Report()
    schema_dir = root / "ontology" / "schema"
    vocab_dir = root / "ontology" / "vocab"
    instances = root / "ontology" / "instances"

    concept_schema = read_json(schema_dir / "concept.schema.json")
    predicate_schema = read_json(schema_dir / "predicate.schema.json")
    entity_schema = read_json(schema_dir / "entity.schema.json")
    assertion_schema = read_json(schema_dir / "assertion.schema.json")

    # ---------------------------------------------------------------- schemas
    vocab_files = {
        "themes.json": concept_schema,
        "properties.json": concept_schema,
        "analysis.json": concept_schema,
        "usecases.json": concept_schema,
        "places.json": concept_schema,
        "hydroatlas-attributes.json": concept_schema,
        "predicates.json": predicate_schema,
    }
    concepts: dict[str, dict] = {}
    schemes: dict[str, set[str]] = {}
    for name, schema in vocab_files.items():
        payload = read_json(vocab_dir / name)
        if payload is None:
            report.error(f"missing vocabulary file: {name}")
            continue
        for problem in Draft202012Validator(schema).iter_errors(payload):
            report.error(f"{name}: {'/'.join(str(p) for p in problem.path)}: {problem.message}")
        if "concepts" in payload:
            scheme = payload["scheme"]
            schemes[scheme] = set()
            for concept in payload["concepts"]:
                if concept["id"] in concepts:
                    report.error(f"duplicate concept ID {concept['id']}")
                concepts[concept["id"]] = dict(concept, scheme=scheme)
                schemes[scheme].add(concept["id"])

    predicates = {p["id"]: p for p in (read_json(vocab_dir / "predicates.json") or {}).get("predicates", [])}

    entities_doc = read_json(instances / "entities.json")
    assertions_doc = read_json(instances / "assertions.json")
    if entities_doc is None or assertions_doc is None:
        report.error("no built instance found; run scripts/ontology/build_ontology.py first")
        return report

    for problem in Draft202012Validator(entity_schema).iter_errors(entities_doc):
        report.error(f"entities.json: {'/'.join(str(p) for p in problem.path)}: {problem.message}")
    for problem in Draft202012Validator(assertion_schema).iter_errors(assertions_doc):
        report.error(f"assertions.json: {'/'.join(str(p) for p in problem.path)}: {problem.message}")

    entities = {}
    for entity in entities_doc["entities"]:
        if entity["id"] in entities:
            report.error(f"duplicate entity ID {entity['id']}")
        entities[entity["id"]] = entity

    # ---------------------------------------------------------------- concept graph
    for concept in concepts.values():
        broader = concept.get("broader")
        if broader and broader not in concepts:
            report.error(f"{concept['id']}: broader concept {broader} does not exist")
        for related in concept.get("related", []):
            if related not in concepts:
                report.error(f"{concept['id']}: related concept {related} does not exist")
        if concept.get("replacedBy") and concept["replacedBy"] not in concepts:
            report.error(f"{concept['id']}: replacedBy {concept['replacedBy']} does not exist")

    # ---------------------------------------------------------------- assertions
    assertions = assertions_doc["assertions"]
    seen_ids: set[str] = set()
    single_valued: dict[tuple[str, str], list[str]] = {}
    duplicate_triples: dict[tuple, int] = {}

    for assertion in assertions:
        aid = assertion["id"]
        if aid in seen_ids:
            report.error(f"duplicate assertion ID {aid}")
        seen_ids.add(aid)

        predicate = predicates.get(assertion["predicate"])
        if predicate is None:
            report.error(f"{aid}: unregistered predicate {assertion['predicate']}")
            continue

        subject = assertion["subject"]
        subject_entity = entities.get(subject)
        subject_type = subject_entity["type"] if subject_entity else (
            "Concept" if subject in concepts else None
        )
        if subject_type is None:
            report.error(f"{aid}: subject {subject} does not resolve")
        elif subject_type not in predicate["domain"]:
            report.error(
                f"{aid}: {predicate['id']} does not apply to a {subject_type} "
                f"(allowed: {', '.join(predicate['domain'])})"
            )

        rng = predicate["range"]
        if "object" in assertion:
            obj = assertion["object"]
            if rng["kind"] == "literal":
                report.error(f"{aid}: {predicate['id']} takes a literal value, not an object")
            elif rng["kind"] == "concept":
                concept = concepts.get(obj)
                if concept is None:
                    report.error(f"{aid}: object concept {obj} does not exist")
                elif rng.get("schemes") and concept["scheme"] not in rng["schemes"]:
                    report.error(
                        f"{aid}: {predicate['id']} expects a {'/'.join(rng['schemes'])} concept, "
                        f"got a {concept['scheme']} concept"
                    )
                elif concept.get("deprecated"):
                    report.warn(f"{aid}: object concept {obj} is deprecated")
            else:
                target = entities.get(obj)
                if target is None:
                    report.error(f"{aid}: object entity {obj} does not exist")
                elif rng.get("entityTypes") and target["type"] not in rng["entityTypes"]:
                    report.error(
                        f"{aid}: {predicate['id']} expects {'/'.join(rng['entityTypes'])}, "
                        f"got {target['type']}"
                    )
        else:
            if rng["kind"] != "literal":
                report.error(f"{aid}: {predicate['id']} takes an object reference, not a literal")
            value = assertion.get("value")
            if rng.get("literalType") == "bbox":
                if not (isinstance(value, list) and len(value) == 4):
                    report.error(f"{aid}: bbox must be [west, south, east, north]")
                elif not (value[0] < value[2] and value[1] < value[3]):
                    report.error(f"{aid}: degenerate or inverted bbox {value}")
            if rng.get("literalType") == "interval":
                if not (isinstance(value, dict) and "start" in value and "end" in value):
                    report.error(f"{aid}: interval must be an object with start and end")
                elif value["start"] > value["end"]:
                    report.error(f"{aid}: interval starts after it ends: {value}")

        agent = entities.get(assertion["assertedBy"])
        if agent is None or agent.get("type") != "Agent":
            report.error(f"{aid}: assertedBy {assertion['assertedBy']} is not a registered agent")
        elif agent.get("trustTier") in {"heuristic", "predicted"} and not assertion.get("evidence"):
            report.error(f"{aid}: {agent['trustTier']} assertion carries no evidence")

        if assertion["status"] == "rejected" and not assertion.get("reviewedBy"):
            report.error(f"{aid}: rejected without a reviewer")
        if assertion.get("reviewedBy") and not assertion.get("reviewedAt"):
            report.warn(f"{aid}: reviewed but no review timestamp")

        if assertion["status"] == "asserted" and predicate["cardinality"] == "one":
            single_valued.setdefault((assertion["subject"], predicate["id"]), []).append(aid)

        triple = (assertion["subject"], assertion["predicate"],
                  json.dumps(assertion.get("object", assertion.get("value")), sort_keys=True))
        duplicate_triples[triple] = duplicate_triples.get(triple, 0) + 1

    for (subject, predicate_id), ids in single_valued.items():
        if len(ids) > 1:
            report.error(
                f"{subject}: {predicate_id} is single-valued but has {len(ids)} asserted values"
            )
    for triple, count in duplicate_triples.items():
        if count > 1:
            report.error(f"duplicate triple asserted {count} times: {triple[0]} {triple[1]}")

    # ---------------------------------------------------------------- ML guard rails
    ml_agents = {e["id"] for e in entities.values()
                 if e.get("type") == "Agent" and e.get("agentKind") == "model"}
    for assertion in assertions:
        if assertion["assertedBy"] not in ml_agents:
            continue
        predicate = predicates.get(assertion["predicate"], {})
        if not predicate.get("mlProposable"):
            report.error(
                f"{assertion['id']}: model wrote {assertion['predicate']}, which is not mlProposable"
            )
        if assertion["status"] == "asserted" and not assertion.get("reviewedBy") \
                and assertion["confidence"] < 0.75:
            report.error(
                f"{assertion['id']}: unreviewed model assertion published below the promote threshold"
            )

    # ---------------------------------------------------------------- coverage
    datasets = [e for e in entities.values() if e["type"] == "Dataset"]
    published = [a for a in assertions if a["status"] == "asserted"]
    by_subject: dict[str, dict[str, list]] = {}
    for assertion in published:
        by_subject.setdefault(assertion["subject"], {}).setdefault(assertion["predicate"], []).append(assertion)

    pending: dict[str, dict[str, int]] = {}
    for assertion in assertions:
        if assertion["status"] == "proposed":
            bucket = pending.setdefault(assertion["subject"], {})
            bucket[assertion["predicate"]] = bucket.get(assertion["predicate"], 0) + 1

    gaps = {"uz:belongsToTheme": [], "uz:observes": [], "uz:hasAnalysisConcept": [], "uz:hasDistribution": []}
    awaiting = 0
    for dataset in datasets:
        facts = by_subject.get(dataset["id"], {})
        waiting = pending.get(dataset["id"], {})
        for predicate in gaps:
            if facts.get(predicate):
                continue
            if waiting.get(predicate):
                awaiting += 1  # a candidate exists, it just has not been reviewed
                continue
            gaps[predicate].append(dataset["id"])

    labels = {
        "uz:belongsToTheme": "no theme",
        "uz:observes": "nothing observed, not even a proposal",
        "uz:hasAnalysisConcept": "no analysis concept",
        "uz:hasDistribution": "no distribution",
    }
    for predicate, group in gaps.items():
        for dataset_id in group:
            report.warn(f"{dataset_id}: {labels[predicate]}")
    if awaiting:
        report.note(f"{awaiting} dataset/predicate gaps have an unreviewed candidate waiting")

    # Referenced-in-place assets: a path that no longer resolves is a dead
    # reference, whether the delivery moved or the drive was detached.
    unreachable = []
    for entity in entities.values():
        location = entity.get("externalPath")
        if location and not Path(location).exists():
            unreachable.append((entity["id"], location))
    for entity_id, location in unreachable[:20]:
        report.warn(f"{entity_id}: external location does not resolve: {location}")
    if len(unreachable) > 20:
        report.note(f"{len(unreachable) - 20} further unreachable external locations")

    # Catalogue parity: the ontology must account for every public record.
    catalog = read_json(root / "public" / "data" / "archive-catalog.json", [])
    catalog_ids = {record["id"] for record in catalog}
    covered = {d.get("catalogId") for d in datasets if d.get("catalogId")}
    for missing in sorted(catalog_ids - covered):
        report.error(f"public catalogue record {missing} is absent from the ontology")

    # Vocabulary drift: every category string in use must map to a theme.
    theme_labels = set()
    for concept in concepts.values():
        if concept.get("scheme") == "theme":
            theme_labels.add(concept["prefLabel"].strip().lower())
            theme_labels.update(a.strip().lower() for a in concept.get("altLabels", []))
    for record in catalog:
        if (record.get("category") or "").strip().lower() not in theme_labels:
            report.error(f"catalogue category '{record.get('category')}' has no theme concept")
    for record in read_json(root / "storage" / "datasets.json", []):
        category = (record.get("category") or "").strip().lower()
        if category and category not in theme_labels:
            report.warn(f"repository category '{record.get('category')}' has no theme concept")

    unused = sorted(
        cid for cid, concept in concepts.items()
        if concept["scheme"] == "property"
        and not any(a.get("object") == cid for a in assertions)
    )
    if unused:
        report.note(f"{len(unused)} property concepts are not yet used by any dataset")
        for concept_id in unused[:10]:
            report.note(f"    unused: {concept_id}")

    proposed = [a for a in assertions if a["status"] == "proposed"]
    reviewed = [a for a in assertions if a.get("reviewedBy")]
    report.note(
        f"{len(datasets)} datasets, {len(published)} published facts, "
        f"{len(proposed)} awaiting review, {len(reviewed)} human-reviewed"
    )

    if strict and report.warnings:
        report.errors.extend(f"(strict) {w}" for w in report.warnings)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".")
    parser.add_argument("--strict", action="store_true", help="treat curation warnings as failures")
    args = parser.parse_args(argv)

    report = validate(Path(args.root).resolve(), strict=args.strict)
    for note in report.notes:
        print(f"note    {note}")
    for warning in report.warnings:
        print(f"WARN    {warning}")
    for error in report.errors:
        print(f"ERROR   {error}")
    print(
        f"\n{len(report.errors)} errors, {len(report.warnings)} warnings"
        f" - {'FAILED' if report.errors else 'ok'}"
    )
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
