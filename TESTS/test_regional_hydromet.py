"""Identity, calendar, physical QC and descriptive statistics guardrails."""
import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'PIPELINES'))
import build_regional_climate_observations as climate
from build_hydromet_station_network import coordinate_flag
from build_regional_glacier_inventories import dms_to_decimal
from hydromet.statistics import monthly_anomalies, regression
from lib_cyrillic import clean_text


def test_nonfinite_is_not_observed_or_a_name():
    for value in [float('nan'), float('inf'), 'NaN', 'inf', 'ND', None]:
        assert climate.number(value) is None
    assert clean_text(float('nan')) == ''
    assert coordinate_flag(float('nan'), 40) == 'missing'


def test_fuzzy_identity_is_not_a_join():
    row = {'entity_id': 'station:test'}
    assert climate.match_station('Tashkent', {'tashkent': row}) == (row, 'exact')
    assert climate.match_station('Tashkents', {'tashkent': row}) == (None, 'fuzzy_candidate_requires_review')


def test_ending_year_mapping():
    assert climate.WATER_YEAR_MONTHS['October'] == (10, -1)
    assert climate.WATER_YEAR_MONTHS['January'] == (1, 0)
    assert climate.WATER_YEAR_MONTHS['September'] == (9, 0)


def test_dms_rejects_invalid_components():
    assert dms_to_decimal('39° 30\' 0" N') == 39.5
    assert dms_to_decimal('39° 60\' 0" N') is None
    assert dms_to_decimal('91° 0\' 0" N') is None
    assert dms_to_decimal('39° 0\' 60" N') is None


def test_anomalies_keep_station_and_calendar_month_separate():
    rows = [{'station_id': station, 'period': f'{year}-01', 'value': offset+year-2000}
            for station,offset in [('a', 0), ('b', 50)] for year in range(2000,2003)]
    result = monthly_anomalies(rows, ['value'])
    assert [r['value_anomaly'] for r in result] == [-1,0,1,-1,0,1]
    assert monthly_anomalies(rows[:2], ['value'])[0]['value_anomaly'] is None


def test_regression_handles_constant_missing_and_block_support():
    assert regression([], 'x', 'y')['slope'] is None
    assert regression([{'x':1,'y':i} for i in range(5)], 'x', 'y')['r'] is None
    rows = [{'x':i, 'y':2*i+1, 'block':i} for i in range(8)]
    result = regression(rows, 'x', 'y', 'block')
    assert result['slope'] == pytest.approx(2)
    assert result['r2'] == pytest.approx(1)
    assert result['slope_interval'] == pytest.approx([2,2])
    assert regression(rows[:4], 'x', 'y', 'block')['slope_interval'] is None


def test_published_network_ids_are_unique():
    with (ROOT/'PUBLISHED/data/hydroclimate/hydromet-meteo-network.csv').open(encoding='utf8') as handle:
        rows = list(csv.DictReader(handle))
    assert len({r['entity_id'] for r in rows}) == len(rows)
    assert all(r['entity_id'] != 'uz:station/meteo-0' for r in rows)


def test_source_cells_and_quarantine_survive_publication():
    path = ROOT/'PUBLISHED/data/hydroclimate'
    with (path/'regional-climate-monthly.csv').open(encoding='utf8') as handle:
        rows = list(csv.DictReader(handle))
    data = json.loads((path/'regional-climate-monthly.json').read_text(encoding='utf8'))
    for row in rows:
        assert row['source_cell']
        assert row['block_swap_corrected'] == 'no'
        if row['entity_id'] and row['quality_flag'] != 'ok':
            values = data['stations'][row['entity_id']]['variables'][row['variable']]['years'][row['calendar_year']]
            assert values[int(row['month'])-1] is None


def test_regional_study_has_soil_context_and_no_fabricated_snow_gradient():
    d = json.loads((ROOT/'PUBLISHED/data/case-studies/regional-station-study.json').read_text(encoding='utf8'))
    assert d['soil_groups']
    assert any(s.get('soil_texture_0cm') in range(1,13) for s in d['stations'])
    assert all('first' not in s for s in d['stations'])
    assert len({(r['station_id'],r['period']) for r in d['monthly']}) == len(d['monthly'])
    snow = d['relationships']['elevation_m:snow_occurrence']
    if snow['n'] < 3:
        assert snow['slope'] is None
    for r in d['monthly']:
        if r['station_air_c'] is not None:
            assert r['station_id'] in climate.DATE_CHECKED_STATIONS
