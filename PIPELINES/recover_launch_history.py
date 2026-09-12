"""Recover an interrupted six-variable launch publication from completed checkpoints.

Does not read or write observation partitions, and never starts an extraction.
Requires a previously exported basin as a provenance anchor. Every existing basin
must agree exactly with the checkpoints before the completed index is published.
This is a recovery tool for the initial preview, not the routine history updater.
"""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core.runtime import utc_now
from ATLAS_MODULES.hydrosheds.functions.dated_monthly import SOURCES

OUT = ROOT / 'PUBLISHED/data/atlas/history'
STORE = ROOT / 'PUBLISHED/data/atlas/observations'
YEARS = range(2003, 2023)


def write(path, payload):
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False,
                                    separators=(',', ':')), encoding='utf-8')
    temporary.replace(path)


def recover():
    reference = json.loads((OUT / '4120050220.json').read_text(encoding='utf-8'))
    names = sorted(reference['series'])
    if names != ['aet_mm_s', 'pet_mm_s', 'pre_mm_s', 'run_mm_s', 'snw_pc_s', 'soil_mm_s']:
        raise ValueError('Recovery expects the frozen six-variable launch snapshot')
    metadata = {name: {key: value for key, value in entry.items()
                       if key not in ('values', 'observed_months', 'missing_months')}
                for name, entry in reference['series'].items()}
    roots = {}
    for source in ('snow', 'terraclimate', 'era5_runoff'):
        ledger = json.loads((STORE / f'regional-{source}-ledger.json').read_text(encoding='utf-8'))
        if not ledger['complete']:
            raise ValueError(f'Unfinished source: {source}')
        for meta in metadata.values():
            if meta['source'] == source:
                assert meta['run_id'] == ledger['run_id']
                assert meta['geometry_version'] == ledger['geometry_version']
        roots[source] = ROOT / 'WORKSPACE/atlas_runs' / (
            'regional_snow' if source == 'snow' else f'regional_monthly/{source}')
    expected = set(json.loads((OUT.parent / 'basins/index.json').read_text())['by_basin'])
    counts, verified = {}, 0

    def publish(item):
        basin, series = item
        payload = {**reference, 'basin_id': basin, 'series': {
            name: {**metadata[name], 'values': values,
                   'observed_months': sum(value is not None for value in values),
                   'missing_months': sum(value is None for value in values)}
            for name, values in series.items()}}
        target = OUT / f'{basin}.json'
        existed = target.exists()
        if existed:
            held = json.loads(target.read_text(encoding='utf-8'))
            if held != payload:
                raise ValueError(f'Checkpoint disagrees with store projection: {basin}')
        else:
            write(target, payload)
        return basin, {name: entry['observed_months'] for name, entry in payload['series'].items()}, existed

    with ThreadPoolExecutor(max_workers=8) as pool:
        for batch in sorted(roots['snow'].glob('batch-*')):
            values, seen = {}, set()
            for source, directory in roots.items():
                for year in YEARS:
                    checkpoint = directory / batch.name / f'year-{year}.json'
                    for row in json.loads(checkpoint.read_text(encoding='utf-8')):
                        basin = str(row['hybas_id'])
                        name = 'snw_pc_s' if source == 'snow' else SOURCES[source]['bands'][row['band']]['attribute'].split('.')[-1]
                        assert row['year'] == year and 1 <= row['month'] <= 12
                        key = (basin, name, year, row['month'])
                        if key in seen:
                            raise ValueError(f'Duplicate checkpoint slot: {key}')
                        seen.add(key)
                        series = values.setdefault(basin, {name: [None] * 240 for name in names})
                        series[name][(year - 2003) * 12 + row['month'] - 1] = (
                            None if row['value'] is None else round(row['value'], 4))
            if len(seen) != len(values) * 240 * len(names):
                raise ValueError(f'Incomplete checkpoint batch: {batch.name}')
            for basin, observed, existed in pool.map(publish, values.items()):
                if basin in counts:
                    raise ValueError(f'Basin in multiple batches: {basin}')
                counts[basin] = observed
                verified += existed
            print(f'{batch.name}: {len(counts)} basins ready', flush=True)
    if set(counts) != expected:
        raise ValueError('Checkpoint basin frame does not match the public atlas')
    write(OUT / 'index.json', {
        'generated_at': utc_now(), 'basins': len(counts), 'years': [2003, 2022], 'months': 240,
        'base_url': '/data/atlas/history/', 'series': metadata, 'observed_months': counts,
        'reading': 'Monthly open-data estimates from completed runs. Periods may differ from '
                   'climatologies. Snow is withdrawn from trend use.',
        'publication_basis': 'Completed-run checkpoints; existing store projections checked for exact agreement',
        'existing_basins_verified': verified,
    })
    print(f'Complete: {len(counts)} basins; {verified} existing store exports verified exactly')


if __name__ == '__main__':
    recover()
