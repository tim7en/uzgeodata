"""Landing projections must use current source data and strict JSON."""
import csv
import hashlib
import json
import sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'PIPELINES'))
from build_study_landing import monthly_rows, safe_json
DATA=ROOT/'PUBLISHED/data/case-studies'


def strict(path):
    def invalid(value):
        raise ValueError(value)
    return json.loads(path.read_text(encoding='utf8'),parse_constant=invalid)


def test_nonfinite_scores_are_null():
    assert safe_json({'score':float('nan'),'rows':[float('inf'),2]})=={'score':None,'rows':[None,2]}


def test_month_support_and_unused_periods():
    rows=[{'date':f'2020-01-{day:02d}','observed_mm':'1','simulated_mm':'2','period':'validation'} for day in range(1,21)]
    assert monthly_rows(rows)[0]['valid_days']==20
    assert monthly_rows(rows)[0]['observed']==1
    assert monthly_rows(rows[:19])[0]['observed'] is None
    assert monthly_rows([dict(r,period='unused') for r in rows])[0]['observed'] is None


def test_current_metrics_and_hashes_match_sources():
    current=strict(DATA/'current-model.json')
    source=strict(DATA/'pskem-daily-model.json')
    assert current['daily']==source['skill']['validation']
    assert current['monthly']==source['monthlySkill']['validation']
    assert current['seasonal']==source['seasonalValidationScores']
    for name,digest in current['source_hashes'].items():
        assert hashlib.sha256((DATA/name).read_bytes()).hexdigest()==digest
    assert len([r for r in current['monthly_rows'] if r['split']=='validation' and r['observed'] is not None])==current['monthly']['n']


def test_figures_are_regenerated_for_current_sources():
    manifest=strict(DATA/'pskem-daily-model-figures.manifest.json')
    for name,digest in manifest['inputHashes'].items():
        assert hashlib.sha256((DATA/name).read_bytes()).hexdigest()==digest


def test_cards_have_real_images_and_distinct_destinations():
    directory=strict(DATA/'study-directory.json')
    cards=directory['studies']
    assert {r['href'] for r in cards}=={'#chirchik-study','#regional-study'}
    for card in cards:
        assert card['aim'] and card['image_alt']
        assert (ROOT/'PUBLISHED'/card['image'].lstrip('/')).exists()
