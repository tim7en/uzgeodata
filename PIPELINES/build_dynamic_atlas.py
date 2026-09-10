"""Publish the dynamic-atlas inventory; --probe checks live EE metadata and pilot pixels.

Offline publication joins the immutable batch, source lock and catalogue. A probe
does not recompute atlas attributes. Its dated evidence is retained separately.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'PUBLISHED/data/atlas'
CATALOG = 'https://developers.google.com/earth-engine/datasets/catalog/'

# Source cadence and proposed operating policy are distinct from saved-run periods.
POLICIES = {
    'terraclimate': ('Monthly', 'Monthly check; append complete months after QA. Recompute normals only as a separate version.'),
    'era5_runoff': ('Monthly aggregates of hourly reanalysis', 'Monthly check; revise recent provisional months. Runoff-derived discharge needs routing and gauge validation.'),
    'modis_snow': ('Daily', 'Monthly publication of cloud-screened daily observations; retain valid-day counts.'),
    'worldclim': ('12 climatological calendar months', 'Frozen baseline; use ERA5-Land or TerraClimate for dated observations.'),
    'copernicus_lc': ('Annual maps, 2015–2019', 'Archive series; evaluate Dynamic World for current land cover, with a new class crosswalk.'),
    'gpw': ('Five-year epochs, 2000–2020', 'Refresh only when a new observed epoch/release is available.'),
    'ghsl': ('Five-year epochs, including interpolated/extrapolated epochs', 'Release check; distinguish observed, interpolated and projected epochs.'),
    'dmsp_lights': ('Annual historical composites', 'Archive series; evaluate VIIRS with a new unit and sensor-specific method.'),
    'glims': ('Irregular inventory revisions; mixed outline dates', 'Quarterly release check; retain each outline date and inventory snapshot.'),
    'wdpa': ('Monthly database releases; mixed designation dates', 'Monthly release check; version boundaries and source rights.'),
    'surface_water': ('1984–2021 multi-year summary', 'Frozen summary; evaluate monthly water history or a newer release separately.'),
}

PROPOSALS = [
    {'asset': 'GOOGLE/DYNAMICWORLD/V1', 'name': 'Dynamic World', 'families': 'glc, for, crp, pst, urb', 'native': '10 m', 'cadence': 'Per Sentinel-2 acquisition', 'policy': 'Monthly/annual composites with probability thresholds, cloud coverage and a reviewed nine-class crosswalk.'},
    {'asset': 'UCSB-CHG/CHIRPS/DAILY', 'name': 'CHIRPS daily precipitation', 'families': 'pre', 'native': '0.05° (~5.6 km)', 'cadence': 'Daily', 'policy': 'Monthly totals; check mountain precipitation against gauges. Does not reproduce WorldClim normals.'},
    {'asset': 'NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG', 'name': 'VIIRS night lights', 'families': 'nli', 'native': '~500 m', 'cadence': 'Monthly', 'policy': 'Cloud-screened radiance; cannot directly replace the DMSP/atlas index.'},
    {'asset': 'JRC/GSW1_4/MonthlyHistory', 'name': 'JRC monthly water history', 'families': 'inu', 'native': '30 m', 'cadence': 'Monthly historical maps, 1984–2021', 'policy': 'Historical change analysis only; this release cannot supply present-day updates.'},
]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2, ensure_ascii=False) + '\n'
    if path.exists() and path.read_text(encoding='utf-8') == content:
        return  # Frozen basin views need no rewrite, including while the server reads them.
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(content, encoding='utf-8')
    temp.replace(path)


def period_used(record, fallback):
    period = record.get('climatology') or record.get('period')
    if isinstance(period, list) and len(period) == 2:
        return f'{period[0]} ≤ date < {period[1]} (climatology)'
    return record.get('epoch') or period or record.get('note') or fallback


def ee_date(milliseconds):
    # Windows fromtimestamp rejects pre-1970 dates (ERA5-Land/TerraClimate).
    return (datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=milliseconds)).isoformat() if milliseconds is not None else None


def resolution_opportunities(family, resolution):
    """Research flags, not claims that a published value has improved resolution."""
    temporal = ''
    if family in {'tmp', 'pre', 'aet', 'pet', 'ari', 'cmi', 'swc', 'run', 'dis'}:
        temporal = 'Dated monthly observations instead of fixed normals; method and completeness review required.'
    elif family == 'snw':
        temporal = 'Daily snow flags and monthly summaries with valid-day counts instead of a climatology.'
    elif family in {'glc-cl', 'glc-pc', 'for', 'crp', 'pst', 'urb', 'inu', 'nli'}:
        temporal = 'Evaluate dated imagery/composites with a new sensor/class crosswalk; not yet extracted for this atlas.'
    elif family in {'gla', 'pac', 'pop', 'ppd'}:
        temporal = 'Store successive dated inventory releases/epochs, not interpolated monthly observations.'
    spatial = ''
    if family in {'glc-cl', 'glc-pc', 'for', 'crp', 'pst', 'urb'}:
        spatial = 'Evaluate 10 m Dynamic World and native class-area reduction; class equivalence and accuracy require validation.'
    elif family in {'gla', 'pac'}:
        spatial = 'Evaluate native vector intersections instead of 30 m painting and 15 arc-second aggregation.'
    elif (resolution.get('native_arcsec') and resolution['native_arcsec'] < 15) or (resolution.get('native_scale_m') and resolution['native_scale_m'] < 450):
        spatial = 'Evaluate reduction at the source native grid before basin aggregation; no claim of higher accuracy.'
    return {'spatial': spatial, 'temporal': temporal,
            'status': 'future_method_review', 'meaning': 'Opportunity, not an achieved improvement or a finer basin geometry.'}


def build_inventory(batch, lock, vocabulary):
    definitions = {c['id'].split('/')[-1]: c for c in vocabulary['concepts']}
    families = []
    for key, plan in batch['surrogate_families'].items():
        attrs = [a for a in batch['attributes'] if a['surrogate_family'] == key]
        builder = plan.get('builder')
        record = lock.get('surrogate_sources', {}).get(builder, {})
        if not record:
            record = lock.get('candidate_sources', {}).get(builder, {})
        assets = record.get('assets') or [record.get('asset') or plan['surrogate']['asset']]
        fetched = any(a.get('surrogate_values') or a.get('candidate_values') for a in attrs)
        via_ee = fetched and builder not in ('elevation', 'dem_terrain', 'hydrolakes')
        definition = definitions.get(key, {}).get('definition', '')
        native = re.search(r'Native format: (.+)', definition)
        cadence, policy = POLICIES.get(builder, ('Static / release-specific', 'Retain as a versioned baseline; review on provider release, not every month.'))
        families.append({
            'family': key, 'label': definitions.get(key, {}).get('prefLabel', attrs[0]['label']),
            'category': attrs[0]['category'], 'attributes': len(attrs),
            'candidates': sum(bool(a.get('candidate_values')) for a in attrs),
            'surrogates': sum(bool(a.get('surrogate_values')) for a in attrs),
            'missing': sum(not a.get('candidate_values') and not a.get('surrogate_values') for a in attrs),
            'original': plan['original'], 'original_native': native.group(1).rstrip('.') if native else 'Unresolved in local catalogue',
            'source': plan['surrogate'], 'assets': assets, 'acquisition': 'Earth Engine' if via_ee else 'Local/provider archive' if fetched else 'Not fetched',
            'used_period': period_used(record, plan['surrogate']['period']) if fetched else 'Not fetched',
            'retrieved_at': record.get('retrieved_at'), 'sha256': record.get('sha256'),
            'resolution': plan['resolution'], 'cadence': cadence, 'refresh_policy': policy,
            'fidelity': plan['fidelity'], 'units': plan['units'], 'notes': plan['divergence'],
            'pending': plan.get('pending_reason') or plan.get('pending_dimensions'),
            'columns': [a['column'] for a in attrs],
            'opportunities': resolution_opportunities(key, plan['resolution']),
        })
    return families


def publish_basin_views(batch, families, destination=OUT):
    """Publish a compact exact-ID view; never transfer pilot values to parent basins."""
    by_family = {f['family']: f for f in families}
    definitions = []
    for a in batch['attributes']:
        f = by_family[a['surrogate_family']]
        definitions.append({'column': a['column'], 'label': a['label'], 'category': a['category'],
                            'support': a['spatial_support'], 'family': f['family'],
                            'candidate_available': bool(a.get('candidate_values')),
                            'pending_reason': a.get('surrogate_pending_reason') or 'No substitute produced in this run.'})
    base = f"/data/atlas/substitutes/{batch['run_id']}/"
    directory = destination / 'substitutes' / batch['run_id']
    write(directory / 'definitions.json', {'run_id': batch['run_id'], 'attributes': definitions,
                                           'families': by_family, 'download_base': batch['download_base']})
    for bid in batch['basin_ids']:
        values = {}
        for a in batch['attributes']:
            s = (a.get('surrogate_values') or {}).get(bid) or {}
            values[a['column']] = {'value': s.get('raw_value'), 'coverage': s.get('coverage_fraction'),
                                   'reference_raw': a['reference_values'].get(bid)}
        write(directory / f'{bid}.json', {'run_id': batch['run_id'], 'hybas_id': bid, 'basin_level': 12, 'values': values})
    write(destination / 'substitutes-index.json', {'schema_version': 1, 'run_id': batch['run_id'],
          'basin_level': 12, 'basin_ids': batch['basin_ids'], 'base_url': base,
          'scope': batch['scope_note'], 'status': 'Pilot estimates; independent reproduction pending',
          'colour_rule': 'Light green means a non-null substitute exists for this exact basin and run. It does not mean newer observation, improved accuracy or validated reproduction.'})


def probe_assets(assets, project, bounds):
    """Inspect each asset and sample valid pixels in the pilot; no global downloads."""
    import ee
    ee.Initialize(project=project)
    ee.data.setDeadline(60000)
    region = ee.Geometry.Rectangle(bounds, None, False)
    rows = []
    for asset in sorted(assets):
        row = {'asset': asset, 'checked_at': datetime.now(timezone.utc).isoformat()}
        try:
            metadata = ee.data.getAsset(asset)
            kind = metadata['type']
            row['type'] = kind
            if kind == 'IMAGE_COLLECTION':
                collection = ee.ImageCollection(asset).filterBounds(region)
                dated = collection.filter(ee.Filter.notNull(['system:time_start']))
                times = dated.aggregate_stats('system:time_start').getInfo()
                row['first_image_date'] = ee_date(times.get('min'))
                row['latest_image_date'] = ee_date(times.get('max'))
                image = ee.Image(collection.sort('system:time_start', False).first())
            elif kind == 'IMAGE':
                image = ee.Image(asset)
            elif kind in ('TABLE', 'FEATURE_COLLECTION'):
                row['pilot_feature_count'] = ee.FeatureCollection(asset).filterBounds(region).size().getInfo()
                row['status'] = 'accessible' if row['pilot_feature_count'] else 'empty_pilot'
                rows.append(row)
                print(f"{asset}: {row['status']}", flush=True)
                continue
            else:
                raise ValueError(f'Unsupported asset type: {kind}')
            row['bands'] = image.bandNames().getInfo()
            row['sample_band'] = row['bands'][0]
            row['nominal_scale_m'] = image.select(0).projection().nominalScale().getInfo()
            # Coarse presence check, explicitly not a full-resolution completeness audit.
            row['probe_scale_m'] = max(1000, row['nominal_scale_m'])
            counts = image.select(0).reduceRegion(ee.Reducer.count(), region, row['probe_scale_m'], maxPixels=1000000).getInfo()
            row['valid_sample_pixels'] = counts.get(row['sample_band'], 0)
            row['status'] = 'accessible' if row['valid_sample_pixels'] else 'empty_sample'
        except Exception as error:
            row.update(status='error', error=f'{type(error).__name__}: {error}')
        rows.append(row)
        print(f"{asset}: {row['status']}", flush=True)
    return rows


def publish(probe=False, project='ee-sabitovty'):
    batch = read(OUT / 'batch-latest.json')
    run = OUT / 'runs' / batch['run_id']
    lock = read(run / 'source-lock.json')
    families = build_inventory(batch, lock, read(ROOT / 'ONTOLOGY/vocab/hydroatlas-attributes.json'))
    if probe:
        assets = {asset for f in families if f['acquisition'] == 'Earth Engine' for asset in f['assets']}
        assets.update(p['asset'] for p in PROPOSALS)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'batch_run_id': batch['run_id'],
                  'scope': 'Pilot bounding box; latest image first-band presence at >=1 km. Not full-period coverage, required-band QA or an attribute extraction.',
                  'sources': probe_assets(assets, project, lock['surrogate_grid']['bounds'])}
        write(OUT / 'availability' / f'{stamp}.json', report)
        write(OUT / 'availability-latest.json', report)
    availability = read(OUT / 'availability-latest.json') if (OUT / 'availability-latest.json').exists() else None
    summary = {k: batch[k] for k in ('basin_count', 'attribute_count', 'candidate_attributes', 'surrogate_attributes', 'attributes_without_any_estimate', 'reference_records', 'reference_nonmissing', 'independently_reproduced')}
    summary['earth_engine_attributes'] = sum(f['candidates'] + f['surrogates'] for f in families if f['acquisition'] == 'Earth Engine')
    with (run / 'observations.csv').open(encoding='utf-8', newline='') as stream:
        observations = list(csv.DictReader(stream))
    summary['surrogate_nonmissing'] = sum(r['surrogate_physical'] != '' for r in observations)
    themes = []
    for category in sorted({f['category'] for f in families}):
        group = [f for f in families if f['category'] == category]
        themes.append({'category': category, **{k: sum(f[k] for f in group) for k in ('attributes', 'candidates', 'surrogates', 'missing')}})
    result = {'generated_at': datetime.now(timezone.utc).isoformat(), 'run_id': batch['run_id'],
              'download_base': batch['download_base'], 'scope': batch['scope_note'], 'summary': summary,
              'themes': themes, 'families': families, 'availability': availability,
              'proposals': [{**p, 'url': CATALOG + p['asset'].replace('/', '_'), 'status': 'Proposed adapter; not extracted by this atlas batch'} for p in PROPOSALS]}
    write(OUT / 'dynamic-atlas.json', result)
    publish_basin_views(batch, families)
    with (OUT / 'dynamic-atlas-crosswalk.csv').open('w', encoding='utf-8', newline='') as stream:
        fields = ['family', 'category', 'attributes', 'candidates', 'surrogates', 'missing', 'acquisition', 'assets', 'original_dataset', 'original_native', 'original_period', 'used_period', 'native_scale_m', 'native_arcsec', 'native_grid', 'processing_grid_arcsec', 'resampling', 'cadence', 'refresh_policy', 'retrieved_at', 'sha256', 'spatial_opportunity', 'temporal_opportunity']
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for f in families:
            row = {**f, 'original_dataset': f['original']['dataset'], 'original_period': f['original']['period'],
                   'spatial_opportunity': f['opportunities']['spatial'], 'temporal_opportunity': f['opportunities']['temporal'],
                   **f['resolution'], 'native_grid': f['resolution']['grid']}
            writer.writerow({k: ' | '.join(row[k]) if isinstance(row[k], list) else row[k] for k in fields})
    print(json.dumps(summary, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', action='store_true')
    parser.add_argument('--project', default='ee-sabitovty')
    args = parser.parse_args()
    publish(args.probe, args.project)
