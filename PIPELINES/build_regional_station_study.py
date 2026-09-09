"""Build the regional station–satellite relationship study (2015–2020 default).

Run after stations:network and stations:climate. Earth Engine is read-only;
cached retrievals are reused unless --refresh is explicitly requested.
"""
import argparse
import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from hydromet.extraction import ASSETS, extract
from hydromet.statistics import monthly_anomalies, regression
from build_regional_climate_observations import write_csv, write_json

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'PUBLISHED/data/hydroclimate'
OUT = ROOT / 'PUBLISHED/data/case-studies'
SOILS = dict(enumerate(['Clay', 'Silty clay', 'Sandy clay', 'Clay loam', 'Silty clay loam',
                       'Sandy clay loam', 'Loam', 'Silt loam', 'Sandy loam', 'Silt', 'Loamy sand', 'Sand'], 1))
FIELDS = ['ndvi', 'lst_day_c', 'snow_occurrence', 'era5_air_c', 'era5_precip_mm', 'soil_temperature_c', 'station_air_c', 'station_precip_mm']


def read_csv(path):
    with path.open(encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', type=int, default=2015)
    parser.add_argument('--end', type=int, default=2020)
    parser.add_argument('--project', default='ee-sabitovty')
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--offline', action='store_true', help='Require and reuse all cached extracts without Earth Engine access.')
    args = parser.parse_args()
    if args.end < args.start or args.end-args.start < 2:
        parser.error('At least three years are required for monthly anomalies.')
    network = read_csv(DATA / 'hydromet-meteo-network.csv')
    stations = [r for r in network if r['coordinate_flag'] == 'ok']
    if len({r['entity_id'] for r in stations}) != len(stations):
        raise ValueError('Station IDs must be unique before extraction.')
    static, raw, provenance = extract(stations, args.start, args.end, args.project, args.refresh, args.offline)
    observations = read_csv(DATA / 'regional-climate-monthly.csv')
    soil = {}
    climate = {}
    for r in observations:
        if (r['variable'] == 'soil_temperature_mean' and r['quality_flag'] == 'ok'
                and r['entity_id'] and r['date_status'] == 'explicit_calendar_year'):
            soil[(r['entity_id'], f"{r['calendar_year']}-{int(r['month']):02d}")] = float(r['value'])
        if r['quality_flag'] == 'ok' and r['date_status'] == 'cross_checked_ending_year':
            climate[(r['entity_id'], f"{r['calendar_year']}-{int(r['month']):02d}", r['variable'])] = float(r['value'])
    screened = []
    for row in raw:
        r = dict(row)
        for field, product, minimum in [('ndvi', 'ndvi', 1), ('lst_day_c', 'lst', 2),
                    ('snow_occurrence', 'snow', 10), ('era5_air_c', 'era5', 1), ('era5_precip_mm', 'era5', 1)]:
            count = r.get(field + '_valid', 0)
            r[field + '_raw'] = r.get(field)
            r[field + '_valid'] = count
            if count < minimum or count < .5 * r[product + '_source_count']:
                r[field] = None
                r[field + '_quality'] = 'insufficient_valid_observations'
            else:
                r.setdefault(field, None)
                r[field + '_quality'] = 'ok' if r[field] is not None else 'missing'
        r['soil_temperature_c'] = soil.get((r['station_id'], r['period']))
        r['station_air_c'] = climate.get((r['station_id'], r['period'], 'air_temperature_mean'))
        r['station_precip_mm'] = climate.get((r['station_id'], r['period'], 'precipitation_total'))
        r['year_block'] = r['period'][:4]
        screened.append(r)
    monthly = monthly_anomalies(screened, FIELDS)
    summaries = []
    station_relationships = {}
    for station in stations:
        sid = station['entity_id']
        rows = [r for r in monthly if r['station_id'] == sid]
        summary = {'station_id': sid, 'label': station['name_latin'],
            'longitude': float(station['longitude']), 'latitude': float(station['latitude']),
            **static[sid]}
        summary['spatial_block'] = f"{int(np.floor(summary['longitude']))}:{int(np.floor(summary['latitude']))}"
        summary['soil_label'] = SOILS.get(summary.get('soil_texture_0cm'), 'Unavailable')
        for field in FIELDS:
            # Equal calendar-month weighting: missing winters cannot create a warm mean.
            calendar_means = []
            for month in range(1, 13):
                values = [r[field] for r in rows if int(r['period'][5:7]) == month and r.get(field) is not None]
                if len(values) >= 3:
                    calendar_means.append(float(np.mean(values)))
            summary[field] = float(np.mean(calendar_means)) if len(calendar_means) == 12 else None
            summary[field + '_months'] = sum(r.get(field) is not None for r in rows)
        summaries.append(summary)
        station_relationships[sid] = {
            'soil_lst_raw': regression(rows, 'soil_temperature_c', 'lst_day_c', 'year_block'),
            'soil_lst_anomaly': regression(rows, 'soil_temperature_c_anomaly', 'lst_day_c_anomaly', 'year_block'),
            'vegetation_lst_anomaly': regression(rows, 'ndvi_anomaly', 'lst_day_c_anomaly', 'year_block'),
            'air_lst_anomaly': regression(rows, 'station_air_c_anomaly', 'lst_day_c_anomaly', 'year_block'),
            'air_lst_raw': regression(rows, 'station_air_c', 'lst_day_c', 'year_block'),
        }
    relationships = {}
    for x, y in [('elevation_m', 'era5_air_c'), ('elevation_m', 'lst_day_c'),
                 ('latitude', 'lst_day_c'), ('longitude', 'ndvi'), ('elevation_m', 'snow_occurrence')]:
        relationships[f'{x}:{y}'] = regression(summaries, x, y, 'spatial_block')
    eligible = [r for r in summaries if r.get('elevation_m') is not None and r.get('era5_air_c') is not None]
    adjusted = {'n': len(eligible), 'elevation_coefficient_c_per_km': None}
    if len(eligible) >= 8:
        design = np.array([[1, r['elevation_m']/1000, r['longitude'], r['latitude']] for r in eligible])
        target = np.array([r['era5_air_c'] for r in eligible])
        if np.linalg.matrix_rank(design) == 4:
            coef = np.linalg.lstsq(design, target, rcond=None)[0]
            adjusted['elevation_coefficient_c_per_km'] = float(coef[1])
    groups = defaultdict(list)
    for r in summaries:
        if r['ndvi'] is not None and r['soil_label'] != 'Unavailable':
            groups[r['soil_label']].append(r['ndvi'])
    soil_groups = [{'soil': key, 'n': len(values), 'median_ndvi': float(np.median(values)),
                    'q25': float(np.quantile(values, .25)), 'q75': float(np.quantile(values, .75))}
                   for key, values in sorted(groups.items())]
    source_paths = [DATA/'hydromet-meteo-network.csv', DATA/'hydromet-gauge-network.csv', DATA/'regional-climate-monthly.csv']
    source_paths += [Path(__file__), ROOT/'PIPELINES/hydromet/extraction.py', ROOT/'PIPELINES/hydromet/statistics.py']
    image_catalogue = {}
    compact_monthly = []
    for row in monthly:
        compact_monthly.append({k:v for k,v in row.items() if not k.endswith('_source_images')})
        for product in ['ndvi', 'lst', 'snow', 'era5']:
            image_catalogue[f"{product}:{row['period']}"] = row[product+'_source_images']
    payload = {
        'version': '1.0', 'generated_at': datetime.now(timezone.utc).isoformat(),
        'period': f'{args.start}–{args.end}', 'status': 'Exploratory historical relationships; not operational validation',
        'stations': summaries, 'monthly': compact_monthly, 'relationships': relationships,
        'source_image_catalogue': image_catalogue,
        'station_relationships': station_relationships, 'soil_groups': soil_groups,
        'location_adjusted_temperature': adjusted,
        'audit': json.loads((DATA/'regional-climate-monthly.manifest.json').read_text(encoding='utf-8')),
        'network': json.loads((DATA/'hydromet-station-network.manifest.json').read_text(encoding='utf-8')),
        'methods': [
            'Native-grid point cells, not station instruments or catchment averages. SRTM terrain height is not surveyed station elevation.',
            'MODIS NDVI: SummaryQA=0; daytime LST: mandatory QA=0 and estimated error <=2 K. Monthly means group composites by start date, not exact day-weighted calendar means.',
            'At least half the source images must pass QA; LST additionally needs two composites. Snow needs ten clear daily observations and half the month.',
            'Snow occurrence is the fraction of valid clear days with NDSI >=40; it is not snow depth, SWE or water storage.',
            'Site climatologies require three values for every calendar month, then weight all twelve months equally. The reference window is six years by default, not a 30-year climate normal.',
            'Anomalies subtract each station and calendar month mean over the selected window, with at least three years. No interpolation or pooled raw-season correlation.',
            'OLS lines are descriptive. 95% slope intervals resample one-degree spatial blocks or whole years (500 draws, fixed seed), requiring five blocks. Spatial dependence beyond one degree and retrieval error remain unquantified.',
            'ERA5-Land is reanalysis, not satellite observation. Elevation coefficient controlling latitude/longitude is a spatial association, not a measured atmospheric lapse rate.',
            'OpenLandMap v02 soil texture at 0 cm is a modelled class, not a field soil survey or soil-temperature measurement. Groups are categorical; no regression on class numbers.',
            'MCD12Q1 endpoint IGBP classes are contextual only. Classification differences are not verified land-cover change.',
            'Regional air/precipitation dates use the ending-year convention cross-checked against independently imported Tashkent/Pskem records; only those two sites enter date-matched comparisons. Elsewhere the convention is inferred. Suspect labels remain quarantined. Soil dates are explicit calendar years; sensor depth remains unknown.',
            'Gauge delivery contains site metadata, not new discharge time series. The regional network does not establish complete transboundary tributary monitoring.',
        ],
        'assets': ASSETS, 'retrievals': provenance,
        'input_hashes': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths},
    }
    write_json(OUT/'regional-station-study.json', payload)
    columns = sorted({k for r in monthly for k in r})
    write_csv(OUT/'regional-station-monthly.csv', columns, [dict(r, **{k: json.dumps(v) for k,v in r.items() if isinstance(v, list)}) for r in monthly])
    write_csv(OUT/'regional-station-context.csv', sorted({k for r in summaries for k in r}), summaries)
    write_json(OUT/'regional-station-study.manifest.json', {k:v for k,v in payload.items() if k not in ['stations','monthly','station_relationships']})
    print(f'Published {len(summaries)} station contexts; {len(monthly)} monthly satellite/reanalysis rows.', flush=True)


if __name__ == '__main__':
    main()
