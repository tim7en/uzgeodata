"""Specification integrity; no scientific computation is claimed by the publisher."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("atlas_roadmap", ROOT / "PIPELINES/build_atlas_roadmap.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_complete_catalogue_and_reproducible_publication():
    first = module.assemble()
    assert first == module.assemble()
    assert len(first["attributes"]) == 281
    assert len(first["functions"]) == 56
    assert first["counts"]["reproduced"] == 0
    assert first["years"] == list(range(2000, 2027))
    assert sum(a["status"] == "implemented" for a in first["attributes"]) == 34
    assert first["counts"]["implemented"] == 34
    assert all(a["status"] in {"specified", "implemented"} for a in first["attributes"])


def test_temporal_and_semantic_traps_remain_explicit():
    data = module.assemble()
    attributes = {a["column"]: a for a in data["attributes"]}
    assert attributes["pre_mm_syr"]["time_kind"] == "climatology"
    assert attributes["glc_pc_s12"]["time_kind"] == "source_epoch"
    assert attributes["hft_ix_s09"]["dimension_label"] == "2009"
    assert attributes["ele_mt_sav"]["annual_policy"] == "reference_only"
    assert attributes["dis_m3_pyr"]["spatial_support"] == "p"
    functions = {f["variable"]: f for f in data["functions"]}
    assert "MYD10CM" in functions["snw"]["steps"] and "MYD10A1" in functions["snw"]["steps"]
    assert "0-5 cm" in functions["soc"]["steps"]
    assert "1000 percent" in functions["dor"]["steps"]
    assert "-9999" in functions["wet-cl"]["steps"]


def test_news_is_republished_and_missing_recipe_fails(tmp_path):
    import json
    import shutil
    shutil.copytree(ROOT / "ATLAS_MODULES", tmp_path / "ATLAS_MODULES")
    dictionary = tmp_path / "PUBLISHED/data/hydrography"
    dictionary.mkdir(parents=True)
    shutil.copy(ROOT / "PUBLISHED/data/hydrography/attribute-dictionary.json", dictionary)
    library = json.loads((ROOT / "ATLAS_MODULES/hydrosheds/recipes.json").read_text(encoding="utf-8"))
    for attribute in library["attributes"]:
        if attribute["status"] == "implemented":
            for key in ("entrypoint", "tests", "comparison_report"):
                relative = attribute["implementation"][key]
                destination = tmp_path / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / relative, destination)
    before = module.assemble(tmp_path)
    news_path = tmp_path / "ATLAS_MODULES/updates.json"
    news = json.loads(news_path.read_text())
    news["updates"].append({"id": "test-news", "date": "2026-09-10", "phase": "specification", "source": "test", "title": "Test update"})
    news_path.write_text(json.dumps(news))
    after = module.assemble(tmp_path)
    assert after["revision"] != before["revision"]
    assert after["updates"][0]["id"] == "test-news"
    path = tmp_path / "ATLAS_MODULES/hydrosheds/recipes.json"
    library = json.loads(path.read_text(encoding="utf-8"))
    library["attributes"].pop()
    path.write_text(json.dumps(library))
    import pytest
    with pytest.raises(AssertionError, match="coverage"):
        module.assemble(tmp_path)
