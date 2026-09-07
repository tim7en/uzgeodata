"""Refresh rule-generated semantics without rebuilding private source records.

The full ontology build remains authoritative.  This scoped projection is safe
for a checkout without ``WORKSPACE/datasets.json``: it starts from the existing
graph, replaces only unreviewed lexical-rule assertions, preserves every source,
pipeline, model and curator assertion, and regenerates the public graph files.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "PIPELINES" / "ontology"))

from build_ontology import AGENT_RULES, GraphBuilder, read_json  # noqa: E402


def main() -> None:
    entities_path = ROOT / "ONTOLOGY" / "instances" / "entities.json"
    assertions_path = ROOT / "ONTOLOGY" / "instances" / "assertions.json"
    if not entities_path.exists() or not assertions_path.exists():
        raise SystemExit("No built ontology instance exists; run ontology:build first.")

    builder = GraphBuilder(ROOT)
    builder.entities = {entity["id"]: entity for entity in read_json(entities_path)["entities"]}
    builder.hydrography = read_json(ROOT / "ONTOLOGY" / "instances" / "hydrography.json", {})
    previous = read_json(assertions_path)["assertions"]
    builder.assertions = {
        assertion["id"]: assertion
        for assertion in previous
        if assertion.get("assertedBy") != AGENT_RULES or assertion.get("reviewedBy")
    }

    removed = len(previous) - len(builder.assertions)
    builder.log(f"Refreshing ontology semantics ({removed:,} unreviewed rule facts replaced)...")
    builder.seed_semantics()
    graph = builder.save()
    builder.log(
        f"  saved {graph['counts']['publishedAssertions']:,} published facts and "
        f"{graph['counts']['proposedAssertions']:,} proposals"
    )


if __name__ == "__main__":
    main()
