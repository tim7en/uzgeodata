"""Native-grid point extraction with QA counts and content-keyed EE caches."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'WORKSPACE/derived/regional-station-cache'
ASSETS = {
    'terrain': 'USGS/SRTMGL1_003',
    'soil': 'OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02',
    'landcover': 'MODIS/061/MCD12Q1',
    'ndvi': 'MODIS/061/MOD13Q1',
    'lst': 'MODIS/061/MOD11A2',
    'snow': 'MODIS/061/MOD10A1',
    'era5': 'ECMWF/ERA5_LAND/MONTHLY_AGGR',
}


def cached_extract(stations, start, end):
    """Rebuild analysis without credentials; fail if any required cache is absent."""
    signature = hashlib.sha256(json.dumps([(s['entity_id'], s['longitude'], s['latitude']) for s in stations]).encode()).hexdigest()[:16]
    provenance, static, monthly = [], {s['entity_id']: {} for s in stations}, {}
    def read(key):
        path = CACHE / f'v1-{signature}-{key}.json'
        if not path.exists():
            raise FileNotFoundError(f'Offline extraction requires {path.name}; run online first.')
        payload = json.loads(path.read_text(encoding='utf8'))
        provenance.append({'cache': path.name, 'retrieved_at': payload['retrieved_at'],
                           'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        return [f['properties'] for f in payload['features']]
    for product in ['terrain', 'soil', 'landcover']:
        for r in read(f'{product}-{start}-{end}'):
            if product == 'soil' and 'first' in r:
                r['soil_texture_0cm'] = r.pop('first')
            static[r.pop('station_id')].update(r)
    for product in ['ndvi', 'lst', 'snow', 'era5']:
        for year in range(start, end+1):
            for r in read(f'{product}-{year}'):
                key = (r['station_id'], r['period'])
                row = monthly.setdefault(key, {'station_id': key[0], 'period': key[1]})
                row.update({k:v for k,v in r.items() if k not in ['source_images','source_count']})
                row[product+'_source_images'] = r['source_images']
                row[product+'_source_count'] = r['source_count']
    return static, list(monthly.values()), provenance


def extract(stations, start, end, project, refresh=False, offline=False):
    if offline:
        if refresh:
            raise ValueError('--offline and --refresh cannot be combined.')
        return cached_extract(stations, start, end)
    import ee
    ee.Initialize(project=project)
    ee.data.setDeadline(120000)
    signature = hashlib.sha256(json.dumps([(s['entity_id'], s['longitude'], s['latitude']) for s in stations]).encode()).hexdigest()[:16]
    points = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([float(s['longitude']), float(s['latitude'])]),
              {'station_id': s['entity_id']}) for s in stations])
    provenance = []

    def retrieve(key, collection):
        path = CACHE / f'v1-{signature}-{key}.json'
        if path.exists() and not refresh:
            payload = json.loads(path.read_text(encoding='utf-8'))
        else:
            payload = {'retrieved_at': datetime.now(timezone.utc).isoformat(),
                       'features': collection.getInfo()['features']}
            CACHE.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps(payload, allow_nan=False), encoding='utf-8')
            temp.replace(path)
        provenance.append({'cache': path.name, 'retrieved_at': payload['retrieved_at'],
                           'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        return [f['properties'] for f in payload['features']]

    def sample(image, projection):
        return image.reduceRegions(collection=points, reducer=ee.Reducer.first(),
                    crs=projection['crs'], crsTransform=projection['transform']).map(lambda f: f.setGeometry(None))

    static = {s['entity_id']: {} for s in stations}
    for product in ['terrain', 'soil', 'landcover']:
        if product == 'terrain':
            image = ee.Image(ASSETS[product])
            image = image.rename('elevation_m').addBands(ee.Terrain.slope(image).rename('slope_deg'))
        elif product == 'soil':
            image = ee.Image(ASSETS[product]).select('b0').rename('soil_texture_0cm')
        else:
            collection = ee.ImageCollection(ASSETS[product])
            image = ee.Image(collection.filterDate(f'{start}-01-01', f'{start+1}-01-01').first()).select('LC_Type1').rename('landcover_start')
            image = image.addBands(ee.Image(collection.filterDate(f'{end}-01-01', f'{end+1}-01-01').first()).select('LC_Type1').rename('landcover_end'))
        projection = image.select(0).projection().getInfo()
        for r in retrieve(f'{product}-{start}-{end}', sample(image, projection)):
            # Single-band reduceRegions names its property after the reducer.
            if product == 'soil' and 'first' in r:
                r['soil_texture_0cm'] = r.pop('first')
            static[r.pop('station_id')].update(r)
        print(f'Regional context: {product}', flush=True)

    monthly = {}
    for product in ['ndvi', 'lst', 'snow', 'era5']:
        collection = ee.ImageCollection(ASSETS[product])
        projection = collection.first().select(0).projection().getInfo()

        def transform(image):
            if product == 'ndvi':
                return image.select('NDVI').multiply(.0001).rename('ndvi').updateMask(image.select('SummaryQA').eq(0))
            if product == 'lst':
                qc = image.select('QC_Day')
                return image.select('LST_Day_1km').multiply(.02).subtract(273.15).rename('lst_day_c').updateMask(qc.bitwiseAnd(3).eq(0).And(qc.rightShift(6).bitwiseAnd(3).lte(1)))
            if product == 'snow':
                snow = image.select('NDSI_Snow_Cover')
                return snow.gte(40).rename('snow_occurrence').updateMask(snow.gte(0).And(snow.lte(100)).And(image.select('NDSI_Snow_Cover_Basic_QA').lte(1)))
            return image.select('temperature_2m').subtract(273.15).rename('era5_air_c').addBands(image.select('total_precipitation_sum').multiply(1000).rename('era5_precip_mm'))

        for year in range(start, end+1):
            def month_reduce(month):
                date = ee.Date.fromYMD(year, month, 1)
                source = collection.filterDate(date, date.advance(1, 'month'))
                values = source.map(transform)
                mean = values.mean()
                count = values.count().rename(mean.bandNames().map(lambda name: ee.String(name).cat('_valid')))
                return sample(mean.addBands(count), projection).map(lambda f: f.set({
                    'period': date.format('YYYY-MM'), 'source_images': source.aggregate_array('system:index'),
                    'source_count': source.size()}))
            features = ee.FeatureCollection(ee.List.sequence(1, 12).map(month_reduce)).flatten()
            for r in retrieve(f'{product}-{year}', features):
                key = (r['station_id'], r['period'])
                row = monthly.setdefault(key, {'station_id': key[0], 'period': key[1]})
                row.update({k: v for k, v in r.items() if k not in ['source_images', 'source_count']})
                row[product + '_source_count'] = r['source_count']
                row[product + '_source_images'] = r['source_images']
            print(f'Regional monthly: {product} {year}', flush=True)
    return static, list(monthly.values()), provenance
