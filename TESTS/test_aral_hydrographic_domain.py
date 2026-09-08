import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
GEOJSON = ROOT / "PUBLISHED/data/hydroclimate/aral-hydrographic-context.geojson"
TABLE = ROOT / "PUBLISHED/data/hydroclimate/aral-hydrographic-context.csv"
MANIFEST = ROOT / "PUBLISHED/data/hydroclimate/aral-hydrographic-context.manifest.json"


def load_rows():
    with TABLE.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_context_separates_non_contributing_desert_from_aral_receptors():
    rows = load_rows()
    desert = [row for row in rows if row["domain_role"] == "non_contributing_internal_drainage"]
    receptors = [row for row in rows if row["domain_role"] == "terminal_receiving_waterbody"]

    assert len(desert) == 70
    assert {row["label"] for row in receptors} == {"Large Aral Sea", "Small Aral Sea"}
    assert all(row["contributes_to_amu_syr"] == "False" for row in rows)
    assert all(row["natural_connection"] == "local_closed_sink" for row in desert)
    assert all(row["runoff_treatment"] == "terminal_water_balance" for row in receptors)


def test_desert_context_keeps_independent_hydroatlas_topology():
    rows = load_rows()
    desert = [row for row in rows if row["entity_type"] == "basin"]
    natural_main_basins = {4070050220, 4070050240}

    assert len({row["hybas_id"] for row in desert}) == len(desert)
    assert not ({int(row["main_basin"]) for row in desert} & natural_main_basins)
    assert all(row["source_asset"] == "WWF/HydroATLAS/v1/Basins/level07" for row in desert)


def test_manifest_records_domain_semantics_and_source_coverage():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert manifest["spatialScope"] == "aral_hydrographic_domain"
    assert manifest["counts"]["internalDrainageUnits"] == 70
    assert manifest["counts"]["independentInternalDrainageSystems"] == 46
    assert manifest["counts"]["terminalReceivingWaterBodies"] == 2
    assert manifest["areasKm2"]["principalInteriorGap"] > 165_000
    assert manifest["areasKm2"]["selectedHydroAtlasUnits"] > 164_000
    assert "Earth Engine" in manifest["sources"]["internalDrainage"]


def test_context_geometry_matches_table_entities():
    document = json.loads(GEOJSON.read_text(encoding="utf-8"))
    rows = load_rows()

    assert document["type"] == "FeatureCollection"
    assert len(document["features"]) == len(rows) == 72
    assert {feature["properties"]["entity_id"] for feature in document["features"]} == {
        row["entity_id"] for row in rows
    }
