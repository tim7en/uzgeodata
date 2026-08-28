"""Tests for the ontology: vocabularies, the built graph, and the guard rails.

The guard-rail tests matter most. They are what makes it safe to let a model
write into the graph: each one injects a bad assertion and asserts that the
validator refuses it.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "ontology"))

import validate_ontology  # noqa: E402
from build_ontology import PROMOTE_THRESHOLD, GraphBuilder, slugify, term_matches  # noqa: E402


def load(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def entities():
    return {e["id"]: e for e in load(ROOT / "ontology" / "instances" / "entities.json")["entities"]}


@pytest.fixture(scope="module")
def assertions():
    return load(ROOT / "ontology" / "instances" / "assertions.json")["assertions"]


@pytest.fixture(scope="module")
def concepts():
    result = {}
    for name in ("themes", "properties", "analysis", "usecases", "places"):
        payload = load(ROOT / "ontology" / "vocab" / f"{name}.json")
        for concept in payload["concepts"]:
            result[concept["id"]] = dict(concept, scheme=payload["scheme"])
    return result


# --------------------------------------------------------------------- vocabularies


@pytest.mark.parametrize(
    "filename,schema_name",
    [
        ("themes.json", "concept.schema.json"),
        ("properties.json", "concept.schema.json"),
        ("analysis.json", "concept.schema.json"),
        ("usecases.json", "concept.schema.json"),
        ("places.json", "concept.schema.json"),
        ("predicates.json", "predicate.schema.json"),
    ],
)
def test_vocabulary_matches_schema(filename, schema_name):
    payload = load(ROOT / "ontology" / "vocab" / filename)
    schema = load(ROOT / "ontology" / "schema" / schema_name)
    errors = list(Draft202012Validator(schema).iter_errors(payload))
    assert not errors, [e.message for e in errors]


def test_theme_vocabulary_covers_every_catalogue_category():
    """The drift that put a stray 'Forests' category outside the seven domains."""
    labels = set()
    for concept in load(ROOT / "ontology" / "vocab" / "themes.json")["concepts"]:
        labels.add(concept["prefLabel"].lower())
        labels.update(alt.lower() for alt in concept.get("altLabels", []))
    categories = {
        (record.get("category") or "").lower()
        for record in load(ROOT / "public" / "data" / "archive-catalog.json")
    }
    assert categories <= labels


def test_concept_ids_are_unique_across_schemes(concepts):
    assert len(concepts) == len(set(concepts))


# --------------------------------------------------------------------- built graph


def test_built_graph_validates_cleanly():
    report = validate_ontology.validate(ROOT)
    assert report.errors == []


def test_every_public_catalogue_record_is_in_the_graph(entities):
    catalogue = {record["id"] for record in load(ROOT / "public" / "data" / "archive-catalog.json")}
    covered = {e.get("catalogId") for e in entities.values() if e["type"] == "Dataset"}
    assert catalogue <= covered


def test_identity_survives_a_rebuild():
    """IDs are minted from the immutable source filename, not from sort order."""
    before = load(ROOT / "ontology" / "instances" / "identity-map.json")["ids"]
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "ontology" / "build_ontology.py"), "--quiet"],
        cwd=ROOT, check=True,
    )
    after = load(ROOT / "ontology" / "instances" / "identity-map.json")["ids"]
    assert before == {k: v for k, v in after.items() if k in before}


def test_duplicate_atlas_numbers_get_distinct_ids(entities):
    """Ten PDSI packages share three atlas numbers; identity must still be unique."""
    pdsi = [e for e in entities.values()
            if e["type"] == "Dataset" and "palmer" in e["id"]]
    assert len(pdsi) == 10
    assert len({e["id"] for e in pdsi}) == 10


def test_hazard_beats_year_range(assertions, entities):
    """Regression: 'Earthquakes, 1990-2024' used to be filed as a change series."""
    earthquake = next(e for e in entities.values()
                      if e["type"] == "Dataset" and e["id"].startswith("uz:ds/a205"))
    concept = next(a["object"] for a in assertions
                   if a["subject"] == earthquake["id"] and a["predicate"] == "uz:hasAnalysisConcept")
    assert concept == "uz:analysis/risk-exposure"


def test_regional_extent_is_flagged(assertions):
    """The seismic catalogue reaches beyond Uzbekistan; the graph has to say so."""
    flags = {a["subject"] for a in assertions
             if a["predicate"] == "uz:qualityFlag" and a.get("value") == "extent-exceeds-uzbekistan"}
    assert "uz:layer/earthquakes" in flags


def test_derived_layers_record_their_provenance(assertions, entities):
    derived = [a for a in assertions if a["predicate"] == "uz:derivedFrom"]
    assert derived
    for assertion in derived:
        assert entities[assertion["subject"]]["type"] == "Distribution"
        assert entities[assertion["object"]]["role"] in {"source-package", "source-document"}


def test_curator_decisions_survive_a_rebuild(assertions):
    """A human correction must not be overwritten by the next rule run."""
    reviewed = [a for a in assertions if a.get("reviewedBy")]
    assert reviewed, "expected the curated review round to be present"
    corrected = [a for a in reviewed
                 if a["subject"].startswith("uz:ds/a118")
                 and a["predicate"] == "uz:hasAnalysisConcept"]
    assert {a["object"]: a["status"] for a in corrected} == {
        "uz:analysis/change-over-time": "rejected",
        "uz:analysis/state-observation": "asserted",
    }


def test_published_facts_carry_provenance(assertions, entities):
    for assertion in assertions:
        agent = entities.get(assertion["assertedBy"])
        assert agent is not None and agent["type"] == "Agent"
        if agent.get("trustTier") in {"heuristic", "predicted"}:
            assert assertion.get("evidence"), assertion["id"]


def test_portal_projection_publishes_only_asserted_facts():
    graph = load(ROOT / "public" / "data" / "ontology-graph.json")
    assert graph["counts"]["datasets"] == len(graph["datasets"])
    assert graph["promoteThreshold"] == PROMOTE_THRESHOLD
    for dataset in graph["datasets"]:
        for observed in dataset["observes"]:
            assert observed["confidence"] >= PROMOTE_THRESHOLD or observed["reviewed"]


# --------------------------------------------------------------------- guard rails


def _validate_with(tmp_path: Path, mutate) -> validate_ontology.Report:
    """Copy the ontology into a temp root, mutate the assertions, validate."""
    for relative in ("ontology/schema", "ontology/vocab", "ontology/instances"):
        source = ROOT / relative
        target = tmp_path / relative
        target.mkdir(parents=True, exist_ok=True)
        for item in source.glob("*.json"):
            target.joinpath(item.name).write_text(item.read_text(encoding="utf-8"), encoding="utf-8")
    for relative in ("public/data/archive-catalog.json", "storage/datasets.json"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((ROOT / relative).read_text(encoding="utf-8"), encoding="utf-8")

    path = tmp_path / "ontology" / "instances" / "assertions.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document["assertions"])
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return validate_ontology.validate(tmp_path)


def _template(assertions, predicate="uz:observes"):
    return copy.deepcopy(next(a for a in assertions if a["predicate"] == predicate))


def test_validator_rejects_a_dangling_reference(tmp_path, assertions):
    def mutate(records):
        bad = _template(records)
        bad["id"] = "uz:a/deadbeefdeadbeef"
        bad["object"] = "uz:prop/does-not-exist"
        records.append(bad)

    report = _validate_with(tmp_path, mutate)
    assert any("does not exist" in error for error in report.errors)


def test_validator_rejects_a_wrong_range(tmp_path, assertions):
    def mutate(records):
        bad = _template(records)
        bad["id"] = "uz:a/deadbeefdeadbee1"
        bad["object"] = "uz:theme/water"  # a theme where a property is required
        records.append(bad)

    report = _validate_with(tmp_path, mutate)
    assert any("expects a property concept" in error for error in report.errors)


def test_validator_rejects_two_values_for_a_single_valued_predicate(tmp_path):
    def mutate(records):
        original = next(a for a in records
                        if a["predicate"] == "uz:belongsToTheme" and a["status"] == "asserted")
        bad = copy.deepcopy(original)
        bad["id"] = "uz:a/deadbeefdeadbee2"
        bad["object"] = "uz:theme/climate" if original["object"] != "uz:theme/climate" else "uz:theme/water"
        records.append(bad)

    report = _validate_with(tmp_path, mutate)
    assert any("single-valued" in error for error in report.errors)


def test_model_cannot_write_a_structural_predicate(tmp_path, assertions):
    """uz:hasDistribution is not mlProposable; a model must never invent one."""

    def mutate(records):
        bad = _template(records, "uz:hasDistribution")
        bad["id"] = "uz:a/deadbeefdeadbee3"
        bad["assertedBy"] = "uz:agent/model-tfidf-knn-v1"
        bad["evidence"] = {"score": 0.9}
        records.append(bad)

    report = _validate_with(tmp_path, mutate)
    assert any("not mlProposable" in error for error in report.errors)


def test_model_cannot_publish_below_the_threshold_without_review(tmp_path, assertions):
    def mutate(records):
        bad = _template(records)
        bad["id"] = "uz:a/deadbeefdeadbee4"
        bad["assertedBy"] = "uz:agent/model-tfidf-knn-v1"
        bad["status"] = "asserted"
        bad["confidence"] = 0.31
        bad["reviewedBy"] = None
        bad["evidence"] = {"score": 0.31}
        records.append(bad)

    report = _validate_with(tmp_path, mutate)
    assert any("below the promote threshold" in error for error in report.errors)


def test_heuristic_assertions_must_show_their_evidence(tmp_path, assertions):
    def mutate(records):
        bad = _template(records)
        bad["id"] = "uz:a/deadbeefdeadbee5"
        bad["assertedBy"] = "uz:agent/rule-lexical-v1"
        bad.pop("evidence", None)
        records.append(bad)

    report = _validate_with(tmp_path, mutate)
    assert any("carries no evidence" in error for error in report.errors)


def test_rejection_requires_a_reviewer(tmp_path, assertions):
    def mutate(records):
        bad = _template(records)
        bad["id"] = "uz:a/deadbeefdeadbee6"
        bad["status"] = "rejected"
        bad["reviewedBy"] = None
        records.append(bad)

    report = _validate_with(tmp_path, mutate)
    assert any("rejected without a reviewer" in error for error in report.errors)


# --------------------------------------------------------------------- helpers


def test_term_matching_tolerates_inflection():
    assert term_matches(" climate types ", "climate type")
    assert term_matches(" ландшафты региона ", "ландшафт")
    assert not term_matches(" groundwater depth ", "water stress")


def test_slug_is_stable_and_ascii():
    assert slugify("Average maximum NDVI, 2004-2024") == "average-maximum-ndvi-2004-2024"
    assert slugify("Динамика засоления почв")


def test_builder_promotes_only_above_the_threshold(tmp_path):
    builder = GraphBuilder(ROOT, quiet=True)
    builder.entities["uz:ds/test"] = {"id": "uz:ds/test", "type": "Dataset", "label": "t",
                                      "sourceKey": "t"}
    high = builder.add("uz:ds/test", "uz:observes", "uz:prop/ndvi",
                       agent="uz:agent/rule-lexical-v1", confidence=0.9,
                       evidence={"source": "test"})
    low = builder.add("uz:ds/test", "uz:observes", "uz:prop/evi",
                      agent="uz:agent/rule-lexical-v1", confidence=0.4,
                      evidence={"source": "test"})
    assert builder.assertions[high]["status"] == "asserted"
    assert builder.assertions[low]["status"] == "proposed"
