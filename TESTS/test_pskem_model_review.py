"""Guard against model storytelling, holdout leakage and mismatched charts."""
import json
import hashlib
import sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'PIPELINES'))
from build_pskem_model_review import class_summary
DATA=ROOT/'PUBLISHED/data/case-studies'


def test_season_thresholds_do_not_use_validation_outcomes():
    rows=[{'observedMcm':v,'simulatedMcm':v,'period':'calibration'} for v in [80,100,120]]
    a=class_summary(rows+[{'observedMcm':100,'simulatedMcm':100,'period':'validation'}])
    b=class_summary(rows+[{'observedMcm':10000,'simulatedMcm':100,'period':'validation'}])
    assert a['mean_mcm']==b['mean_mcm']==100
    assert a['std_mcm']==b['std_mcm']
    with pytest.raises(ValueError):
        class_summary([{'observedMcm':100,'period':'calibration'}]*3)


def test_review_matches_candidate_and_reference_is_preserved():
    review=json.loads((DATA/'model-review.json').read_text(encoding='utf8'))
    trial=json.loads((DATA/'model-audit/chronological-20260909/pskem-daily-model.json').read_text(encoding='utf8'))
    old=json.loads((DATA/'pskem-daily-model.json').read_text(encoding='utf8'))
    assert trial['model']['calibration']['split']=='chronological'
    assert old['model']['calibration']['split']=='stratified'
    assert max(review['train_years'])<min(review['test_years'])
    assert review['candidate']['monthly']==trial['monthlySkill']['validation']
    assert review['candidate']['seasonal']==trial['seasonalValidationScores']
    for name,digest in review['inputs'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest
    assert review['benchmark']['daily']['n']==review['candidate']['daily']['n']
    assert review['benchmark']['monthly']['n']==review['candidate']['monthly']['n']
    assert review['benchmark']['seasonal']['n']==review['candidate']['seasonal']['n']


def test_headlines_remove_unsupported_improvement_and_leaky_class_claims():
    payload=json.loads((DATA/'case-study-highlights.json').read_text(encoding='utf8'))
    records={r['id']:r for r in payload['findings']}
    assert '60%' not in records['elevation-band-forcing']['detail']
    assert records['elevation-band-forcing']['kind']=='limitation'
    assert records['water-year-class']['classThresholds']['source']=='calibration_only'
    assert 'figure' not in records['water-year-class']
    assert '2004, 2006, 2007' in records['daily-process-model']['detail']


def test_directory_foregrounds_the_new_chronological_result():
    directory=json.loads((DATA/'study-directory.json').read_text(encoding='utf8'))
    review=json.loads((DATA/'model-review.json').read_text(encoding='utf8'))
    card=next(c for c in directory['studies'] if c['id']=='chirchik')
    assert card['metric']==review['candidate']['monthly']['nse']
    assert 'chronological' in card['metric_label']
