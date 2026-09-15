import json
from pathlib import Path
import pytest
from PIPELINES import build_variable_inventory as inventory
from PIPELINES import run_data_update as update
from ATLAS_MODULES.core import variables


def write(root, name, data):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def test_published_inventory_covers_the_registries_and_all_four_layers():
    root = inventory.ROOT
    report = inventory.read(root, 'PUBLISHED/data/variable-inventory.json')
    rows = report['rows']
    ids = {row['id'] for row in rows}
    assert len(ids) == len(rows)
    catalogue = inventory.read(root, 'PUBLISHED/data/atlas/catalogue.json')
    assert all(f'reference:{code}' in ids for code in catalogue['attributes'])
    assert set(variables.VARIABLES) <= ids
    tables = inventory.read(root, 'ONTOLOGY/vocab/relationship-tables.json')['tables']
    assert all(any(id.startswith(f"table:{table['id']}:") for id in ids) for table in tables)
    assert {row['layer'] for row in rows} == {1, 2, 3, 4}
    groups = {group['id'] for group in report['groups']}
    assert all(not row.get('group_id') or row['group_id'] in groups for row in rows)


def test_a_table_reports_each_variables_own_coverage(tmp_path):
    (tmp_path / 'values.csv').write_text('variable,year,month,value,unit\nrain,2026,8,2,mm\ntemperature,2024,12,3,C\nrain,2025,1,4,mm\n')
    table = {'container': 'values.csv', 'measureColumn': 'value', 'measureUnitColumn': 'unit'}
    result = inventory.table_variables(tmp_path, table)
    assert result['rain']['last'] == '2026-08'
    assert result['temperature']['last'] == '2024-12'
    assert result['rain']['unit'] == 'mm'


def test_snapshot_generation_does_not_invent_an_acquisition_timestamp(tmp_path):
    write(tmp_path, 'PUBLISHED/data/atlas/catalogue.json', {'generated_at': '2026-09-14', 'attributes': ['ele'], 'meta': {'ele': {'label': 'Elevation'}}})
    report = inventory.build(tmp_path)
    row = next(r for r in report['rows'] if r['id'] == 'reference:ele')
    assert row['last_updated'] is None
    assert row['published_at'] == '2026-09-14'


def test_failed_group_does_not_change_the_inventory_or_update_timestamp(tmp_path, monkeypatch):
    write(tmp_path, 'PUBLISHED/data/variable-inventory.json', {'rows': []})
    monkeypatch.setattr(update, 'preflight', lambda *args: None)
    monkeypatch.setattr(update.subprocess, 'run', lambda *args, **kwargs: type('Result', (), {'returncode': 1})())
    group = {'id': 'test', 'kind': 'commands', 'commands': [['failing.py']]}
    with pytest.raises(RuntimeError, match='has not been marked updated'):
        update.execute(group, tmp_path)
    assert inventory.read(tmp_path, 'PUBLISHED/data/variable-inventory.json') == {'rows': []}
    assert not (tmp_path / 'PUBLISHED/data/variable-updates.json').exists()


def test_release_coverage_can_extend_without_changing_source_code():
    measured = {entry['attribute']: [2003, 2026] for entry in variables.VARIABLES.values()}
    through = {entry['attribute']: '2026-08' for entry in variables.VARIABLES.values()}
    result = variables.registry(coverage=measured, observed_through=through)
    assert result['variables']['uz:pre-monthly-v1']['coverage'] == [2003, 2026]
    assert result['variables']['uz:pre-monthly-v1']['observed_through'] == '2026-08'
    assert variables.VARIABLES['uz:pre-monthly-v1']['coverage'] == [2003, 2024]
    with pytest.raises(ValueError, match='missing from the cube'):
        variables.registry(coverage={})


def test_inventory_build_failure_does_not_publish_success(tmp_path, monkeypatch):
    write(tmp_path, 'PUBLISHED/data/variable-inventory.json', {'rows': []})
    write(tmp_path, 'PUBLISHED/data/variable-updates.json', {'old': {'finished_at': '2024-01-01'}})
    monkeypatch.setattr(update, 'preflight', lambda *args: None)
    monkeypatch.setattr(update.subprocess, 'run', lambda *args, **kwargs: type('Result', (), {'returncode': 0})())
    def fail(*args, **kwargs):
        raise RuntimeError('Invalid inventory')
    monkeypatch.setattr(inventory, 'build', fail)
    with pytest.raises(RuntimeError, match='Invalid inventory'):
        update.execute({'id': 'test', 'kind': 'commands', 'commands': [['ok.py']]}, tmp_path)
    assert inventory.read(tmp_path, 'PUBLISHED/data/variable-inventory.json') == {'rows': []}
    assert inventory.read(tmp_path, 'PUBLISHED/data/variable-updates.json') == {'old': {'finished_at': '2024-01-01'}}


def test_successful_group_persists_timestamp_after_build(tmp_path, monkeypatch):
    write(tmp_path, 'PUBLISHED/data/variable-inventory.json', {'rows': []})
    monkeypatch.setattr(update, 'preflight', lambda *args: None)
    monkeypatch.setattr(update.subprocess, 'run', lambda *args, **kwargs: type('Result', (), {'returncode': 0})())
    def build(root, *, updates):
        assert not (root / 'PUBLISHED/data/variable-updates.json').exists()
        return {'rows': [], 'checked_updates': updates}
    monkeypatch.setattr(inventory, 'build', build)
    update.execute({'id': 'test', 'kind': 'commands', 'commands': [['ok.py']]}, tmp_path)
    updates = inventory.read(tmp_path, 'PUBLISHED/data/variable-updates.json')
    assert updates['test']['finished_at']
    assert inventory.read(tmp_path, 'PUBLISHED/data/variable-inventory.json')['checked_updates'] == updates


def test_success_metadata_is_restored_if_second_file_commit_fails(tmp_path, monkeypatch):
    before = {'rows': ['previous']}
    write(tmp_path, 'PUBLISHED/data/variable-inventory.json', before)
    monkeypatch.setattr(update, 'preflight', lambda *args: None)
    monkeypatch.setattr(inventory, 'build', lambda *args, **kwargs: {'rows': ['new']})
    replace = Path.replace
    def fail_timestamp_commit(path, target):
        if path.name == 'variable-updates.tmp':
            raise OSError('Write failed')
        return replace(path, target)
    monkeypatch.setattr(Path, 'replace', fail_timestamp_commit)
    with pytest.raises(OSError, match='Write failed'):
        update.execute({'id': 'test', 'kind': 'commands', 'commands': []}, tmp_path)
    assert inventory.read(tmp_path, 'PUBLISHED/data/variable-inventory.json') == before
    assert not (tmp_path / 'PUBLISHED/data/variable-updates.json').exists()
    assert not list((tmp_path / 'PUBLISHED/data').glob('*.tmp'))
