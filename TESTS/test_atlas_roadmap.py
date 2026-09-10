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


def test_two_atlas_plan_preserves_evidence_and_temporal_prerequisites():
    import json
    plan = module.assemble()['implementation_plan']
    assert [s['number'] for s in plan['stages']] == [1, 2, 3, 4, 5, 6]
    assert 'Stage 5' in plan['stages'][1]['gate']
    assert plan['stages'][2]['status'] == 'planned'
    for stage in plan['stages']:
        assert stage['gate'] and stage['deliverables']
        assert all((ROOT / p).is_file() for p in stage['evidence'])
    science = json.loads((ROOT / plan['runtime']['evidence']).read_text(encoding='utf-8'))
    runtime, projection, grids = plan['runtime'], science['scale_projection'], science['domain']['grids']
    assert runtime['domain_basins'] == science['domain']['basins']
    assert runtime['systems'] == science['domain']['systems']
    assert sum(runtime['systems'].values()) == runtime['domain_basins']
    assert runtime['evidence_run_id'] == science['run_id']
    # Every figure the plan page presents as measured has to come from the run,
    # or a re-run leaves stale numbers labelled "measured" on a published page.
    assert runtime['pilot_basins'] == science['pilot']['basins']
    assert runtime['pilot_warm_seconds'] == science['pilot']['wall_seconds']
    assert runtime['pilot_cold_seconds'] == science['pilot']['cold_cache_wall_seconds']
    assert runtime['regional_acquisition_hours_extrapolated'] == projection['acquisition_hours_linear']
    assert runtime['regional_current_reduction_hours_extrapolated'] == projection['reduction_hours_current_kernel']
    assert runtime['regional_grouped_kernel_minutes'] == projection['reduction_minutes_bincount']
    assert runtime['raster_storage_15arcsec_gb'] == projection['raster_gigabytes_15arcsec']
    for key, grid in (('fine_grid_multiplier_3arcsec', '3_arcsec'), ('fine_grid_multiplier_1arcsec', '1_arcsec')):
        assert runtime[key] == round((grids['15_arcsec']['arcsec'] / grids[grid]['arcsec']) ** 2)
    fields = ' '.join(plan['storage_contract']['time_fields'])
    assert all(k in fields for k in ['period_end_exclusive', 'climatology', 'retrieved_at', 'supersedes_observation_id'])


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
