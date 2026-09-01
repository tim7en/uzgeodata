"""Refresh Earth Engine sources inside an already-built ontology graph.

The full ontology builder is authoritative and now projects these sources as
part of every rebuild. This compatibility command exists for checkouts where
the private WORKSPACE source registry is intentionally absent: it updates only
the declared Earth Engine slice, registers its local tables, and regenerates the
two public graph projections without dropping unrelated catalogue records.

    python PIPELINES/project_earth_engine_sources.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "PIPELINES" / "ontology"))

from build_ontology import AGENT_EE_REGISTRY, GraphBuilder, read_json  # noqa: E402


def main() -> None:
    entities_path = ROOT / "ONTOLOGY" / "instances" / "entities.json"
    assertions_path = ROOT / "ONTOLOGY" / "instances" / "assertions.json"
    if not entities_path.exists() or not assertions_path.exists():
        raise SystemExit(
            "No built ontology instance exists. Run PIPELINES/ontology/build_ontology.py "
            "on a checkout containing WORKSPACE/datasets.json first."
        )

    builder = GraphBuilder(ROOT)
    builder.entities = {e["id"]: e for e in read_json(entities_path)["entities"]}
    builder.assertions = {a["id"]: a for a in read_json(assertions_path)["assertions"]}
    builder.earth_engine_sources = read_json(
        ROOT / "ONTOLOGY" / "vocab" / "earth-engine-sources.json", {"sources": []}
    )
    builder.relationship_tables = read_json(
        ROOT / "ONTOLOGY" / "vocab" / "relationship-tables.json", {"tables": []}
    )
    builder.hydrography = read_json(ROOT / "ONTOLOGY" / "instances" / "hydrography.json", {})
    builder.relationship_counts = {
        "hydrography": (builder.hydrography or {}).get("counts", {}),
        "atlasBasinLinks": (read_json(
            ROOT / "ONTOLOGY" / "instances" / "atlas-basin-links.json", {}
        ) or {}).get("counts", {}),
        "basinZonalStats": (read_json(
            ROOT / "ONTOLOGY" / "instances" / "basin-zonal-stats.json", {}
        ) or {}).get("counts", {}),
        "adminBasinLinks": (read_json(
            ROOT / "ONTOLOGY" / "instances" / "admin-basin-links.json", {}
        ) or {}).get("counts", {}),
    }

    registry = builder.earth_engine_sources["sources"]
    replaced = {AGENT_EE_REGISTRY, "uz:dist/cams-basin-daily"}
    for source in registry:
        replaced.update({
            source["agent"],
            f"uz:ds/{source['slug']}",
            f"uz:dist/{source['slug']}-earth-engine-source",
        })
        for product in source.get("derivedProducts", []):
            replaced.update({f"uz:ds/{product['slug']}", f"uz:dist/{product['slug']}"})

    builder.entities = {key: value for key, value in builder.entities.items()
                        if key not in replaced}
    builder.assertions = {
        key: value for key, value in builder.assertions.items()
        if value["subject"] not in replaced
        and value.get("object") not in replaced
        and not (value.get("evidence") or {}).get("source", "").endswith(
            "earth-engine-sources.json"
        )
    }

    builder.log("Refreshing Earth Engine ontology slice...")
    builder.build_earth_engine_sources()
    builder.build_relationship_tables()
    graph = builder.save()
    builder.log(
        f"  saved {len(registry)} sources; portal now contains "
        f"{graph['counts']['datasets']:,} datasets and "
        f"{graph['counts']['relationshipTables']:,} relationship tables"
    )
    if builder.warnings:
        builder.log(f"  {len(builder.warnings)} warnings (missing optional tables are not invented)")


if __name__ == "__main__":
    main()
