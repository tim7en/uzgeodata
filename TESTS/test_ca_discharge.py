import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_integrated_ca_discharge_summary_is_source_accurate_and_safe():
    summary = json.loads((ROOT / 'PUBLISHED/data/research/ca-discharge-summary.json').read_text())
    assert summary['status'] == 'integrated'
    assert summary['source']['doi'] == '10.5281/zenodo.8147591'
    assert summary['source']['license'] == 'cc-by-4.0'
    assert summary['source']['gpkg_md5'] == 'e0ba6664aaec3e0b27138abdfd4ba263'
    assert summary['counts'] == {
        'gauge_rows': 297, 'gauge_points_published': 297,
        'gauges_with_time_series': 136, 'discharge_observations': 244632,
    }
    assert set(summary['excluded_attributes']) == {'gl_dmdt_km3a', 'gl_dmdtda_mma'}


def test_pskem_is_crosswalked_but_not_claimed_as_independent_validation():
    summary = json.loads((ROOT / 'PUBLISHED/data/research/ca-discharge-summary.json').read_text())
    crosswalk = summary['crosswalks'][0]
    assert crosswalk['ca_code'] == '16290'
    assert crosswalk['uzgeodata_station'] == 'uz:station/gauge-16290'
    assert crosswalk['coordinate_separation_km'] < 5
    check = summary['pskem_consistency']
    assert check['paired_dekads'] == 555
    assert check['pearson_r'] > .99
    assert 'not independent validation' in check['interpretation'].lower()


def test_public_station_layer_contains_only_points_and_omits_warned_fields():
    raw = (ROOT / 'PUBLISHED/data/research/ca-discharge-stations.geojson').read_text()
    collection = json.loads(raw)
    assert len(collection['features']) == 297
    assert all(feature['geometry']['type'] == 'Point' for feature in collection['features'])
    assert 'gl_dmdt_km3a' not in raw
    assert 'gl_dmdtda_mma' not in raw
