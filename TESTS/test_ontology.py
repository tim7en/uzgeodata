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
sys.path.insert(0, str(ROOT / "PIPELINES" / "ontology"))

import validate_ontology  # noqa: E402
from build_ontology import PROMOTE_THRESHOLD, GraphBuilder, slugify, term_matches  # noqa: E402


def load(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def entities():
    return {e["id"]: e for e in load(ROOT / "ONTOLOGY" / "instances" / "entities.json")["entities"]}


@pytest.fixture(scope="module")
def assertions():
    return load(ROOT / "ONTOLOGY" / "instances" / "assertions.json")["assertions"]


@pytest.fixture(scope="module")
def concepts():
    result = {}
    for name in ("themes", "properties", "analysis", "usecases", "places"):
        payload = load(ROOT / "ONTOLOGY" / "vocab" / f"{name}.json")
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
        ("relationship-tables.json", "relationship-table.schema.json"),
    ],
)
def test_vocabulary_matches_schema(filename, schema_name):
    payload = load(ROOT / "ONTOLOGY" / "vocab" / filename)
    schema = load(ROOT / "ONTOLOGY" / "schema" / schema_name)
    errors = list(Draft202012Validator(schema).iter_errors(payload))
    assert not errors, [e.message for e in errors]


def test_theme_vocabulary_covers_every_catalogue_category():
    """The drift that put a stray 'Forests' category outside the seven domains."""
    labels = set()
    for concept in load(ROOT / "ONTOLOGY" / "vocab" / "themes.json")["concepts"]:
        labels.add(concept["prefLabel"].lower())
        labels.update(alt.lower() for alt in concept.get("altLabels", []))
    categories = {
        (record.get("category") or "").lower()
        for record in load(ROOT / "PUBLISHED" / "data" / "archive-catalog.json")
    }
    assert categories <= labels


def test_concept_ids_are_unique_across_schemes(concepts):
    assert len(concepts) == len(set(concepts))


# --------------------------------------------------------------------- built graph


def test_built_graph_validates_cleanly():
    report = validate_ontology.validate(ROOT)
    assert report.errors == []


def test_every_public_catalogue_record_is_in_the_graph(entities):
    catalogue = {record["id"] for record in load(ROOT / "PUBLISHED" / "data" / "archive-catalog.json")}
    covered = {e.get("catalogId") for e in entities.values() if e["type"] == "Dataset"}
    assert catalogue <= covered


def test_identity_survives_a_rebuild(tmp_path):
    """IDs are minted from the immutable source filename, not from sort order."""
    _copy_ontology(tmp_path)
    before = load(tmp_path / "ONTOLOGY" / "instances" / "identity-map.json")["ids"]
    subprocess.run(
        [sys.executable, str(ROOT / "PIPELINES" / "ontology" / "build_ontology.py"), "--quiet"],
        cwd=tmp_path, check=True,
    )
    after = load(tmp_path / "ONTOLOGY" / "instances" / "identity-map.json")["ids"]
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
    """Lineage links distributions, and every chain ends at something original.

    Derivation is not always one hop: a HydroSHEDS layer goes source -> relationship
    database -> web layer. What must hold is that following the chain terminates at
    a source or referenced-in-place original, and never loops.
    """
    derived = [a for a in assertions if a["predicate"] == "uz:derivedFrom"]
    assert derived
    parents = {}
    for assertion in derived:
        assert entities[assertion["subject"]]["type"] == "Distribution"
        assert entities[assertion["object"]]["type"] == "Distribution"
        parents.setdefault(assertion["subject"], []).append(assertion["object"])

    roots = {"source-package", "source-document", "external-vector", "external-table",
             "external-document", "external-archive"}
    for start in parents:
        seen, current = {start}, start
        while current in parents:
            current = parents[current][0]
            assert current not in seen, f"derivation cycle at {current}"
            seen.add(current)
        assert entities[current]["role"] in roots, entities[current]["role"]


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


def test_triple_table_carries_every_fact_with_its_provenance(assertions):
    """The review table is the one projection that must NOT filter by status.

    The portal shows facts; this file is for the backlog, so a proposal or a
    rejection going missing here is the failure mode that matters.
    """
    table = load(ROOT / "PUBLISHED" / "data" / "ontology-triples.json")
    assert table["counts"]["total"] == len(assertions)
    by_status = {}
    for assertion in assertions:
        by_status[assertion["status"]] = by_status.get(assertion["status"], 0) + 1
    for status, count in by_status.items():
        assert table["counts"][status] == count, status
    assert table["counts"]["proposed"] > 0 and table["counts"]["rejected"] > 0

    rows = {row["id"]: row for row in table["triples"]}
    assert len(rows) == len(assertions)
    for assertion in assertions:
        row = rows[assertion["id"]]
        assert row["s"] == assertion["subject"]
        assert row["p"] == assertion["predicate"]
        assert row["st"] == assertion["status"]
        assert row["a"] == assertion["assertedBy"]
        assert row["r"] == assertion.get("reviewedBy")
        assert (row["o"] is not None) or (row["v"] is not None)

    # Every id the table renders must have a label, or the browser shows a URI.
    for row in table["triples"]:
        assert row["s"] in table["labels"], row["s"]
        if row["o"]:
            assert row["o"] in table["labels"], row["o"]

    registered = {p["id"] for p in table["predicates"]}
    assert {row["p"] for row in table["triples"]} <= registered
    agents = {a["id"] for a in table["agents"]}
    assert {row["a"] for row in table["triples"]} <= agents


def test_portal_projection_publishes_only_asserted_facts():
    graph = load(ROOT / "PUBLISHED" / "data" / "ontology-graph.json")
    assert graph["counts"]["datasets"] == len(graph["datasets"])
    assert graph["promoteThreshold"] == PROMOTE_THRESHOLD
    for dataset in graph["datasets"]:
        for observed in dataset["observes"]:
            assert observed["confidence"] >= PROMOTE_THRESHOLD or observed["reviewed"]


# --------------------------------------------------------------------- guard rails


def _copy_ontology(tmp_path: Path) -> None:
    for relative in ("ONTOLOGY/schema", "ONTOLOGY/vocab", "ONTOLOGY/instances"):
        source = ROOT / relative
        target = tmp_path / relative
        target.mkdir(parents=True, exist_ok=True)
        for item in source.glob("*.json"):
            target.joinpath(item.name).write_text(item.read_text(encoding="utf-8"), encoding="utf-8")
    for relative in ("PUBLISHED/data/archive-catalog.json", "WORKSPACE/datasets.json"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        source = ROOT / relative
        target.write_text(source.read_text(encoding="utf-8") if source.exists() else "[]\n",
                          encoding="utf-8")


def _mutate_json(tmp_path: Path, relative: str, key: str, mutate) -> None:
    path = tmp_path / relative
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document[key])
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")


def _validate_with(tmp_path: Path, mutate) -> validate_ontology.Report:
    """Copy the ontology into a temp root, mutate the assertions, validate."""
    _copy_ontology(tmp_path)
    _mutate_json(tmp_path, "ONTOLOGY/instances/assertions.json", "assertions", mutate)
    return validate_ontology.validate(tmp_path)


def _validate_with_entities(tmp_path: Path, mutate) -> validate_ontology.Report:
    _copy_ontology(tmp_path)
    _mutate_json(tmp_path, "ONTOLOGY/instances/entities.json", "entities", mutate)
    return validate_ontology.validate(tmp_path)


def _validate_with_predicates(tmp_path: Path, mutate) -> validate_ontology.Report:
    _copy_ontology(tmp_path)
    _mutate_json(tmp_path, "ONTOLOGY/vocab/predicates.json", "predicates", mutate)
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


# --------------------------------------------------------------------- external deliveries


@pytest.fixture(scope="module")
def details():
    return load(ROOT / "ONTOLOGY" / "instances" / "external" / "details.json")


def test_external_datasets_carry_licence_and_attribution(assertions, entities):
    """ODbL and restricted sources both oblige us to state terms and credit."""
    licensed = {a["subject"] for a in assertions if a["predicate"] == "uz:license"}
    attributed = {a["subject"] for a in assertions if a["predicate"] == "uz:attributedTo"}
    osm = {e["id"] for e in entities.values()
           if e["type"] == "Dataset" and e["id"].startswith("uz:ds/osm-")}
    assert osm, "expected the OpenStreetMap datasets to be catalogued"
    assert osm <= licensed and osm <= attributed
    odbl = {a["subject"] for a in assertions
            if a["predicate"] == "uz:license" and a.get("value") == "ODbL-1.0"}
    assert osm <= odbl


def test_curator_mapping_outranks_the_lexical_rules(assertions):
    """Regression: the rule pass used to overwrite curator-asserted facts."""
    labels = [a for a in assertions
              if a["subject"] == "uz:ds/landcover-training-samples"
              and a["predicate"] == "uz:observes"
              and a["object"] == "uz:prop/annotation-labels"]
    assert len(labels) == 1
    assert labels[0]["assertedBy"] == "uz:agent/curator"
    assert labels[0]["status"] == "asserted"


def test_external_distributions_are_referenced_not_copied(assertions, entities):
    external = [e for e in entities.values()
                if e["type"] == "Distribution" and str(e.get("role", "")).startswith("external-")]
    assert external
    located = {a["subject"] for a in assertions if a["predicate"] == "uz:externalLocation"}
    for distribution in external:
        assert distribution["id"] in located
        assert distribution.get("storedName") is None
        assert distribution.get("url") is None


def test_stations_resolve_and_sit_inside_the_region(entities, assertions):
    stations = [e for e in entities.values() if e["type"] == "MonitoringStation"]
    assert len(stations) >= 190
    for station in stations:
        assert 55.0 <= station["longitude"] <= 74.0, station["id"]
        assert 36.0 <= station["latitude"] <= 46.0, station["id"]
        assert station["network"] in {"uzhydromet-meteo", "uzhydromet-gauge"}
    operated = {a["object"] for a in assertions if a["predicate"] == "uz:operatesStation"}
    assert operated == {s["id"] for s in stations}


def test_station_shapefile_crs_is_flagged(assertions):
    """The station shapefile is Pulkovo 1942, not WGS 84; that has to be visible."""
    flags = [a for a in assertions
             if a["subject"] == "uz:ds/meteorological-station-network"
             and a["predicate"] == "uz:qualityFlag"]
    values = {a["value"] for a in flags}
    assert "crs-not-wgs84" in values
    assert "attribute-encoding-cp1251" in values


def test_training_class_labels_match_the_measurement(assertions, details):
    measured = details["classLabels"]["landcover-training-samples"]
    asserted = {a["value"]: a["evidence"]["featureCount"] for a in assertions
                if a["subject"] == "uz:ds/landcover-training-samples"
                and a["predicate"] == "uz:hasClassLabel"}
    assert asserted == measured["classes"]
    assert sum(asserted.values()) == measured["total"]
    flags = {a["value"] for a in assertions
             if a["subject"] == "uz:ds/landcover-training-samples"
             and a["predicate"] == "uz:qualityFlag"}
    assert "severe-class-imbalance" in flags


def test_the_missing_atlas_package_is_now_accounted_for(assertions, entities):
    """atlas 92 had no distribution until the 1 GB package turned up in the drop."""
    distributions = [a["object"] for a in assertions
                     if a["subject"] == "uz:ds/a92-land-cover"
                     and a["predicate"] == "uz:hasDistribution"]
    assert distributions
    assert any(entities[d]["role"] == "source-package" for d in distributions)


def test_inventories_are_complete(entities):
    """Every referenced external file was actually profiled, in some delivery.

    Guards two ways of losing data silently: the profiler's depth limit dropping
    files, and a curator mapping pointing at a path nothing ever measured.
    """
    external = ROOT / "ONTOLOGY" / "instances" / "external"
    inventories = [load(path) for path in sorted(external.glob("*.json"))
                   if "files" in load(path)]
    assert inventories, "expected at least one profiled delivery"

    profiled = set()
    for inventory in inventories:
        assert inventory.get("skippedTooDeep", []) == [], inventory["name"]
        root = inventory["source"].replace("\\", "/").rstrip("/")
        profiled |= {f"{root}/{record['path']}" for record in inventory["files"]}

    roots = [inventory["source"].replace("\\", "/").rstrip("/")
             for inventory in inventories]
    referenced = {entity["externalPath"].replace("\\", "/")
                  for entity in entities.values()
                  if entity["type"] == "Distribution" and entity.get("externalPath")}
    # Only paths inside a profiled delivery are in scope here. References that
    # predate profiling are reported by the validator instead, as a warning.
    in_scope = {path for path in referenced if any(path.startswith(root) for root in roots)}
    assert in_scope, "expected external distributions from a profiled delivery"
    missing = in_scope - profiled
    assert not missing, sorted(missing)[:5]


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


# --------------------------------------------------------------- feature topology

TOPOLOGY_PREDICATES = {
    "uz:flowsInto", "uz:drainsToBasin", "uz:withinBasin", "uz:subBasinOf",
}


@pytest.fixture(scope="module")
def relationship_tables():
    return load(ROOT / "ONTOLOGY" / "vocab" / "relationship-tables.json")["tables"]


@pytest.fixture(scope="module")
def predicates():
    return {p["id"]: p for p in load(ROOT / "ONTOLOGY" / "vocab" / "predicates.json")["predicates"]}


def test_topology_predicates_are_measured_not_proposed(predicates):
    """A model can guess what a dataset observes. It cannot measure where water goes."""
    for name in TOPOLOGY_PREDICATES:
        predicate = predicates[name]
        assert predicate["viaRelationshipTable"] is True, name
        assert predicate["mlProposable"] is False, name
        assert predicate["range"]["kind"] == "entity", name
        assert set(predicate["domain"]) <= {"Basin", "RiverReach", "WaterBody"}, name
        assert set(predicate["range"]["entityTypes"]) <= {"Basin", "RiverReach", "WaterBody"}, name


def test_topology_stays_out_of_the_assertion_graph(assertions):
    """The whole point: 126,000 links declared, not expanded.

    One assertion per link would bury the curated facts under measurements no
    curator will ever review, and would need a feature entity for every endpoint.
    """
    expanded = [a for a in assertions if a["predicate"] in TOPOLOGY_PREDICATES]
    assert not expanded, f"{len(expanded)} topology links leaked into assertions.json"
    features = [e for e in load(ROOT / "ONTOLOGY" / "instances" / "entities.json")["entities"]
                if e["type"] in {"Basin", "RiverReach", "WaterBody"}]
    assert not features, f"{len(features)} feature entities were minted"


def test_every_declared_relationship_table_reaches_the_graph(relationship_tables, entities,
                                                             assertions):
    registered = {e["id"]: e for e in entities.values() if e.get("role") == "relationship-table"}
    assert len(registered) == len(relationship_tables)

    owner = {a["object"]: a["subject"] for a in assertions
             if a["predicate"] == "uz:hasDistribution"}
    # Several tables share one GeoPackage, so the container alone does not
    # identify a table; the declared table name separates them.
    for table in relationship_tables:
        match = registered.get(f"uz:dist/{table['id']}") or next(
            (e for e in registered.values()
             if e.get("container") == table["container"]
             and e.get("containerTable") == table.get("containerTable")), None)
        assert match is not None, table["id"]
        assert match["predicate"] == table["predicate"]
        assert match["subjectType"] == table["subjectType"]
        assert match["objectType"] == table["objectType"]
        if table.get("subjectFixed"):
            assert match["subjectFixed"] == table["subjectFixed"]
            assert "subjectColumn" not in match
        else:
            assert match["subjectColumn"] == table["subjectColumn"]
        assert match["objectColumn"] == table["objectColumn"]
        assert match["identifierScheme"] == table["identifierScheme"]
        assert match["rowCount"] > 0
        assert owner.get(match["id"]) == f"uz:ds/{table['dataset']}", table["id"]


def test_relationship_tables_say_where_to_read_them_exactly_once(entities):
    """Referenced in place or held in the repo, never recorded as both."""
    for entity in entities.values():
        if entity.get("role") != "relationship-table":
            continue
        stored = entity.get("storedName")
        referenced = entity.get("externalPath")
        assert stored or referenced, entity["id"]
        assert not (stored and referenced), entity["id"]
        assert entity.get("url") is None, entity["id"]


def test_relationship_table_row_counts_are_measured(relationship_tables, entities):
    """Counts come from the file or the build that wrote it, never from the vocabulary."""
    import csv

    by_container = {}
    for entity in entities.values():
        if entity.get("role") == "relationship-table" and not entity.get("containerTable"):
            by_container.setdefault(entity.get("container"), []).append(entity)
    checked = 0
    for table in relationship_tables:
        if table["format"] != "CSV":
            continue
        container = ROOT / table["container"]
        if not container.exists():
            continue
        candidates = by_container[table["container"]]
        entity = next((candidate for candidate in candidates
                       if candidate["id"] == f"uz:dist/{table['id']}"), candidates[0])
        with container.open(encoding="utf-8-sig", newline="") as handle:
            header = next(csv.reader(handle))
            rows = sum(1 for _ in handle)
        if len(candidates) == 1:
            assert entity["rowCount"] == rows, table["id"]
        else:
            assert sum(candidate["rowCount"] for candidate in candidates) == rows, table["container"]
        if table.get("subjectColumn"):
            assert table["subjectColumn"] in header, table["id"]
        else:
            assert table["subjectFixed"] == f"uz:ds/{table['dataset']}", table["id"]
        assert table["objectColumn"] in header, table["id"]
        if table.get("scopeColumn"):
            assert table["scopeColumn"] in header, table["id"]
        checked += 1
    assert checked >= 6, "expected the delivery relationship CSVs to be present"

    # A table inside a GeoPackage shares its path with its siblings, so it is only
    # identifiable if it names itself.
    inside = [e for e in entities.values()
              if e.get("role") == "relationship-table" and e.get("containerTable")]
    assert len({e["containerTable"] for e in inside}) == len(inside)


def test_relationship_table_schema_requires_the_typed_declaration():
    """The role is what binds the extra requirements; dropping a field must fail."""
    schema = load(ROOT / "ONTOLOGY" / "schema" / "entity.schema.json")
    entities = load(ROOT / "ONTOLOGY" / "instances" / "entities.json")
    document = copy.deepcopy(entities)
    table = next(e for e in document["entities"] if e.get("role") == "relationship-table")
    del table["subjectColumn"]
    errors = list(Draft202012Validator(schema).iter_errors(document))
    assert errors

    # The same record without the role carries no such requirement.
    document = copy.deepcopy(entities)
    table = next(e for e in document["entities"] if e.get("role") == "relationship-table")
    del table["subjectColumn"]
    table["role"] = "external-table"
    assert not list(Draft202012Validator(schema).iter_errors(document))


def test_validator_rejects_a_table_whose_subject_the_predicate_forbids(tmp_path):
    def mutate(records):
        table = next(e for e in records if e.get("role") == "relationship-table"
                     and e["predicate"] == "uz:withinBasin")
        table["subjectType"] = "Basin"  # uz:withinBasin applies to a WaterBody

    report = _validate_with_entities(tmp_path, mutate)
    assert any("does not apply to a Basin" in error for error in report.errors)


def test_validator_rejects_a_table_whose_object_the_predicate_forbids(tmp_path):
    def mutate(records):
        table = next(e for e in records if e.get("role") == "relationship-table"
                     and e["predicate"] == "uz:drainsToBasin")
        table["objectType"] = "RiverReach"  # uz:drainsToBasin ranges over Basin

    report = _validate_with_entities(tmp_path, mutate)
    assert any("table declares RiverReach" in error for error in report.errors)


def test_validator_rejects_an_empty_relationship_table(tmp_path):
    def mutate(records):
        table = next(e for e in records if e.get("role") == "relationship-table")
        table["rowCount"] = 0

    report = _validate_with_entities(tmp_path, mutate)
    assert any("declares no rows" in error for error in report.errors)


def test_a_model_may_not_be_let_at_measured_topology(tmp_path):
    """Opening uz:flowsInto to the model has to fail, not quietly widen the surface."""

    def mutate(records):
        predicate = next(p for p in records if p["id"] == "uz:flowsInto")
        predicate["mlProposable"] = True

    report = _validate_with_predicates(tmp_path, mutate)
    assert any("mutually exclusive" in error for error in report.errors)


def test_topology_may_not_be_asserted_one_fact_at_a_time(tmp_path, assertions):
    """A table predicate belongs in a table; a stray assertion using it is an error."""

    def mutate(records):
        bad = copy.deepcopy(next(a for a in records if a["predicate"] == "uz:relatedTo"))
        bad["id"] = "uz:a/deadbeefdeadbee9"
        bad["predicate"] = "uz:flowsInto"
        records.append(bad)

    report = _validate_with(tmp_path, mutate)
    assert any("declared to live in a relationship table" in error for error in report.errors)
