"""The audit must describe actual acquisitions, preserve gaps and retain source dates."""
import json
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIPELINES.build_dynamic_atlas import build_inventory, ee_date, period_used


@pytest.fixture(scope='module')
def inventory():
    def read(path):
        return json.loads(path.read_text(encoding='utf-8'))
    batch = read(ROOT / 'PUBLISHED/data/atlas/batch-latest.json')
    lock = read(ROOT / 'PUBLISHED/data/atlas/runs' / batch['run_id'] / 'source-lock.json')
    return batch, build_inventory(batch, lock, read(ROOT / 'ONTOLOGY/vocab/hydroatlas-attributes.json'))


def test_all_attributes_accounted_for_once(inventory):
    batch, families = inventory
    columns = [c for f in families for c in f['columns']]
    assert len(columns) == len(set(columns)) == batch['attribute_count']
    assert sum(f['candidates'] for f in families) == batch['candidate_attributes']
    assert sum(f['surrogates'] for f in families) == batch['surrogate_attributes']
    assert sum(f['missing'] for f in families) == batch['attributes_without_any_estimate']
    assert len({f['category'] for f in families}) == 6


def test_actual_source_lock_overrides_registry_plan(inventory):
    _, families = inventory
    by_id = {f['family']: f for f in families}
    assert by_id['snw']['used_period'] == '2003-01-01 ≤ date < 2023-01-01 (climatology)'
    assert by_id['pop']['assets'] == ['CIESIN/GPWv411/GPW_Population_Density']
    assert by_id['pre']['assets'] == ['WORLDCLIM/V1/MONTHLY']
    assert by_id['ele']['acquisition'] == 'Local/provider archive'
    assert by_id['lka']['acquisition'] == 'Local/provider archive'
    assert all(f['acquisition'] == 'Not fetched' for f in families if not f['candidates'] and not f['surrogates'])


def test_pre_epoch_dates_on_windows():
    assert ee_date(-315619200000).startswith('1960-01-01')
    assert ee_date(None) is None
    assert period_used({'epoch': '2015'}, '2026') == '2015'


def test_fresh_and_offline_are_incompatible():
    from PIPELINES.update_pskem_atlas import run
    with pytest.raises(ValueError, match='cannot be combined'):
        run(offline=True, refresh_sources=True)
