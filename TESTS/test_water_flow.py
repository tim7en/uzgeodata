"""Accounting regressions: scientific boundaries, complete footprints and source identity."""
import json
from pathlib import Path
import duckdb
import pytest
from PIPELINES import build_water_flow_diagram as accounts
from PIPELINES import build_water_flow_sensitivity as models


def records():
    con=duckdb.connect()
    con.execute('CREATE TABLE records (basin_id VARCHAR, variable VARCHAR, year INTEGER, month INTEGER, value DOUBLE, unit VARCHAR)')
    con.executemany('INSERT INTO records VALUES (?,?,?,?,?,?)',
        [(b,'pre',2022,m,1.,'millimetres per month') for b in ['a','b'] for m in range(1,13)])
    return con


def test_volume_conversion_and_complete_domain():
    with records() as con:
        result=models.annual_totals(con,{'a':100.,'b':200.},2022,2022,['pre'])
    assert result[0]['volume_km3']==pytest.approx(.0036)
    assert result[0]['coverage_area_fraction']==1


@pytest.mark.parametrize('mutation',[
    "UPDATE records SET value=NULL WHERE basin_id='b' AND month=7",
    "DELETE FROM records WHERE basin_id='b' AND month=7",
    "DELETE FROM records WHERE basin_id='b'",
])
def test_partial_year_or_domain_is_not_a_regional_total(mutation):
    with records() as con:
        con.execute(mutation)
        row=models.annual_totals(con,{'a':100.,'b':200.},2022,2022,['pre'])[0]
    assert row['volume_km3'] is None
    assert row['complete_basins']==1
    assert row['coverage_area_fraction']==pytest.approx(1/3)


def test_duplicate_month_cannot_replace_missing_month():
    with records() as con:
        con.execute("UPDATE records SET month=1 WHERE basin_id='a' AND month=2")
        with pytest.raises(ValueError,match='Duplicate'):
            models.annual_totals(con,{'a':100.,'b':200.},2022,2022,['pre'])


@pytest.mark.parametrize('mutation,match',[
    ("UPDATE records SET unit='m' WHERE month=1",'unit'),
    ("UPDATE records SET month=13 WHERE month=1",'period'),
    ("UPDATE records SET basin_id='other' WHERE basin_id='a'",'Unknown basin'),
    ("UPDATE records SET value='NaN' WHERE month=1",'value'),
])
def test_invalid_source_records_fail(mutation,match):
    with records() as con:
        con.execute(mutation)
        with pytest.raises(ValueError,match=match):
            models.annual_totals(con,{'a':100.,'b':200.},2022,2022,['pre'])


def test_country_sums_and_reporting_boundaries(tmp_path):
    report=accounts.build(tmp_path/'accounts.json')
    assert all(abs(r['country_sum_error_km3'])<.015 for r in report['reported_totals'])
    assert report['reported_totals'][0]['amu_withdrawal_km3']==44.26
    assert report['reported_totals'][0]['syr_above_shardara_km3']==13.83
    assert all(r['cross_border_outflow_km3'] is None for r in report['country_withdrawals'])
    assert any(r['country']=='afghanistan' for r in report['unavailable_country_accounts'])
    assert all(r['route']=='south_karakalpak_drain' for r in report['environmental_deliveries'] if r['scope']=='large_aral')
    assert all(r['period_kind']=='calendar_year' for r in report['figures'])
    assert len(report['figures'])==54


def test_bad_country_sum_cannot_publish(tmp_path,monkeypatch):
    figures=accounts.read_figures()
    next(r for r in figures if r['figure_id']=='2022-amu_darya-withdrawal-uzbekistan')['value']+=1
    monkeypatch.setattr(accounts,'read_figures',lambda:figures)
    with pytest.raises(ValueError,match='reconcile'):
        accounts.build(tmp_path/'bad.json')
    assert not (tmp_path/'bad.json').exists()


def test_recoverable_returns_change_net_saving_not_gross_withdrawal():
    cases=[models.efficiency_example(recoverable_fraction=r) for r in [0,.5,1]]
    assert cases[0]['gross_withdrawal_reduction_units']==pytest.approx(13.6986301369863)
    assert len({r['gross_withdrawal_reduction_units'] for r in cases})==1
    assert cases[-1]['net_downstream_gain_units']==0
    assert cases[1]['net_downstream_gain_units']==pytest.approx(cases[0]['net_downstream_gain_units']/2)


def test_published_case_study_references_exact_inputs_and_map():
    report=json.loads(models.OUT.read_text())
    assert report['source_cube_index_sha256']==accounts.digest(models.CUBE/'index.json')
    assert report['domain']['geometry_sha256']==accounts.digest(models.GEOMETRY)
    for relative,hash in report['input_hashes'].items():
        assert accounts.digest(models.CUBE/relative)==hash
    complete={r['year'] for r in report['annual_coverage'] if r['status']=='complete'}
    assert set(report['matched_years'])<=complete
    assert 'stress_threshold' not in report
    assert 'observed' not in report
    card=accounts.study_card()
    assert card['image'].endswith('regional-water-flow-map.svg')
    assert card['metric']==3
    assert 'exceeded supply' not in card['detail']
