"""Build a bounded, source-audited water accounting dataset; never infer country outflows."""
from __future__ import annotations
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core.runtime import utc_now, write_json
FLOW = ROOT / 'PUBLISHED/data/water-flow'
OUT = FLOW / 'regional-water-flow.json'
YEARS = (2022, 2023, 2024)
COUNTRIES = ('tajikistan', 'turkmenistan', 'uzbekistan')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_figures(path=FLOW / 'regional-withdrawals.csv'):
    with Path(path).open(encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))
    if len({r['figure_id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate figure identity')
    for row in rows:
        row['value'] = float(row['value']); row['year'] = int(row['year'])
        if not math.isfinite(row['value']) or row['value'] < 0:
            raise ValueError('Invalid reported volume')
        if row['period_kind'] != 'calendar_year' or row['unit'] != 'km3/year':
            raise ValueError('Incompatible time or unit')
        if not row['source_id'] or not row['source_locator'] or not row['source_url']:
            raise ValueError('Missing source evidence')
    return rows


def select(rows, year, scope, component, entity):
    found = [r for r in rows if (r['year'], r['scope'], r['component'], r['entity']) == (year, scope, component, entity)]
    if len(found) != 1:
        raise ValueError(f'Expected one figure for {(year, scope, component, entity)}')
    return found[0]


def build(out=OUT):
    figures = read_figures()
    sources = json.loads((FLOW / 'sources.json').read_text())
    source_ids = {s['source_id'] for s in sources['sources']}
    if any(r['source_id'] not in source_ids for r in figures):
        raise ValueError('Unresolved source')
    countries, environment, reservoirs, totals = [], [], [], []
    for year in YEARS:
        get = lambda scope, kind, entity: select(figures, year, scope, kind, entity)
        annual = []
        for country in COUNTRIES:
            actual = get('amu_darya', 'withdrawal', country)
            limit = get('amu_darya', 'allocation_limit', country)
            row = dict(year=year, country=country, withdrawal_km3=actual['value'], limit_km3=limit['value'],
                       limit_utilisation_percent=100*actual['value']/limit['value'],
                       figure_ids=[actual['figure_id'],limit['figure_id']],
                       cross_border_inflow_km3=None, cross_border_outflow_km3=None)
            annual.append(row); countries.append(row)
        total = get('amu_darya', 'withdrawal', 'reported_total')
        error = sum(r['withdrawal_km3'] for r in annual)-total['value']
        if abs(error) > .015:
            raise ValueError(f'Country withdrawals do not reconcile in {year}: {error}')
        totals.append(dict(year=year, amu_withdrawal_km3=total['value'],
                           syr_above_shardara_km3=get('syr_above_shardara','withdrawal','reported_total')['value'],
                           country_sum_error_km3=round(error,8)))
        for scope,kind,entity in [('northern_aral','terminal_inflow','syr_darya'),
                                   ('amu_delta','mixed_delivery','river_canals_drains'),
                                   ('large_aral','terminal_inflow','south_karakalpak_drain')]:
            r=get(scope,kind,entity)
            environment.append(dict(year=year, scope=scope, volume_km3=r['value'], figure_id=r['figure_id'],
                                    route=entity, note=r['note']))
        for name in ('nurek','tuyamuyun','toktogul'):
            inflow=get(name,'reservoir_inflow','reservoir'); release=get(name,'reservoir_release','reservoir')
            reservoirs.append(dict(year=year,reservoir=name,inflow_km3=inflow['value'],release_km3=release['value'],
                                   inflow_minus_release_km3=round(inflow['value']-release['value'],3),
                                   figure_ids=[inflow['figure_id'],release['figure_id']],
                                   interpretation='Residual before evaporation, precipitation, seepage, other exchanges and reporting error; not a complete storage balance.'))
    report=dict(schema_version=2,generated_at=utc_now(),reviewed_at=sources['reviewed_at'],
                title='Water withdrawals and downstream deliveries', status='Source-audited descriptive case study; not a validated discharge model',
                years=list(YEARS),time_basis='Calendar years, January–December',unit='km3/year',
                country_withdrawals=countries,reported_totals=totals,environmental_deliveries=environment,
                reservoir_accounts=reservoirs,figures=figures,sources=sources['sources'],reuse=sources['reuse'],
                unavailable_country_accounts=[dict(country=c,inflow_km3=None,outflow_km3=None,
                    reason='No matched cross-border inflow/outflow series assembled for this accounting exercise.')
                    for c in ('afghanistan','kazakhstan','kyrgyzstan','tajikistan','turkmenistan','uzbekistan')],
                exclusions=['Country withdrawal is not consumption, national water use or border inflow.',
                            'Syr Darya reporting boundary ends at Shardara; downstream abstractions are outside that total.',
                            'Afghanistan is an Amu Darya riparian; omission from these ICWC country figures is not zero use.',
                            'Environmental deliveries are separate observations, not shares subtracted from country withdrawals.',
                            'No country allocation of national sector shares or regional wastewater inventory is made.',
                            'Modelled P minus AET is not routed available water and is not netted against withdrawals.'],
                input_hashes={'regional-withdrawals.csv':digest(FLOW/'regional-withdrawals.csv'), 'sources.json':digest(FLOW/'sources.json')})
    write_json(out,report)
    return report


if __name__ == '__main__':
    r=build();print(f"Built audited accounts: {len(r['figures'])} figures, {len(r['years'])} calendar years")


def study_card():
    data=json.loads(OUT.read_text())
    image='/data/water-flow/regional-water-flow-map.svg'
    return dict(id='water-flow',href='/water-flow.html',title='Water withdrawals and downstream deliveries',
       region='AMU DARYA & SYR DARYA',aim='Locate the rivers, compare reported country withdrawals and trace reservoir and Aral delivery records to their sources.',
       image=image,image_alt='Geographic overview of the Amu Darya and Syr Darya basin systems with the river network and selected dams.',
       image_revision=digest(ROOT/'PUBLISHED'/image.lstrip('/'))[:12],
       evidence_date=data['generated_at'],metric=len(data['years']),metric_label='Calendar years of reported accounts',
       detail='2022–2024 · model diagnostics kept separate · no inferred country outflows',status='Source-audited water accounting')
