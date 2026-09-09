"""Download daily ERA5 forcing and exact thesis-threshold terrain/glacier areas.

Uses the existing provisional catchment, never relocates the gauge. Restartable
annual caches; no temporal disaggregation of monthly weather.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone

from shapely.geometry import shape, mapping
from shapely.ops import unary_union

from build_chirchik_case_studies import ROOT, DATA, OUT, write_csv, write_json
from extract_chirchik_remote import cached, context

ASSET = 'ECMWF/ERA5_LAND/DAILY_AGGR'
DEM = 'COPERNICUS/DEM/GLO30_2024_1'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--end', type=int, default=2017)
    args = parser.parse_args()
    import ee
    ee.Initialize(project='ee-sabitovty')
    region, digest = context(ee)
    source = ee.ImageCollection(ASSET)
    native = source.first().select('temperature_2m').projection().getInfo()
    output = []
    for year in range(2000, args.end + 1):
        def reduce_image(image):
            area = ee.Image.pixelArea()
            channels = []
            fields = [('temperature_2m', 'temperature_c', 1, -273.15),
                      ('total_precipitation_sum', 'precipitation_mm', 1000, 0),
                      ('potential_evaporation_sum', 'potential_et_mm', -1000, 0),
                      ('surface_solar_radiation_downwards_sum', 'solar_down_wm2', 1/86400, 0)]
            for band, name, factor, offset in fields:
                value = image.select(band).multiply(factor).add(offset)
                channels += [value.multiply(area).rename(name), area.updateMask(value.mask()).rename(name+'_area')]
            sums = ee.Image.cat(channels).reduceRegion(ee.Reducer.sum(), region,
                crs=native['crs'], crsTransform=native['transform'], maxPixels=10000000)
            values = {name: ee.Number(sums.get(name)).divide(ee.Number(sums.get(name+'_area'))) for _, name, _, _ in fields}
            return ee.Feature(None, values).set({'date':image.date().format('YYYY-MM-dd'), 'source_image':image.get('system:index')})
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d') if year >= datetime.now(timezone.utc).year else 'complete'
        info = cached(f'sabitov-daily-{digest}-{year}-{stamp}-v1', lambda: source.filterDate(f'{year}-01-01', f'{year+1}-01-01').map(reduce_image).getInfo())
        output.extend(f['properties'] for f in info['features'])
        print(f'Daily ERA5 {year}: {len(info["features"])} days', flush=True)
    output.sort(key=lambda r: r['date'])
    write_csv(OUT/'sabitov-daily-forcing.csv', output, list(output[0]))

    basin_doc = json.loads((OUT/'pskem-candidate-catchment.geojson').read_text(encoding='utf-8'))
    basin = unary_union([shape(f['geometry']) for f in basin_doc['features']])
    # The existing upper-Syr headwater export does not cover Pskem. Query this
    # catchment explicitly; absence from a regional export is not zero ice.
    from build_glacier_inventory import outline_selection, rock_selection
    from shapely import make_valid
    outlines = cached(f'sabitov-glims-{digest}-20230607', lambda: outline_selection('GLIMS/20230607',region).getInfo())
    rocks = cached(f'sabitov-glims-rock-{digest}-20230607', lambda: rock_selection('GLIMS/20230607',region).getInfo())
    selected = []
    for f in outlines['features']:
        rock = [make_valid(shape(r['geometry'])) for r in rocks['features'] if r['properties']['glac_id']==f['properties']['glac_id']]
        net = make_valid(shape(f['geometry'])).difference(unary_union(rock)).intersection(basin)
        if net.is_empty:continue
        selected.append({'type':'Feature','geometry':mapping(net),'properties':f['properties']})
    if not selected:raise ValueError('No GLIMS outlines; a missing inventory must not be interpreted as zero glacier area')
    glacier_file = OUT/'pskem-glims-outlines.geojson'
    write_json(glacier_file,{'type':'FeatureCollection','features':selected})
    glaciers = unary_union([shape(f['geometry']) for f in selected])
    glacier_hash = hashlib.sha256(glacier_file.read_bytes()).hexdigest()
    terrain = ee.ImageCollection(DEM).filterBounds(region)
    dem = terrain.mosaic().select('DEM').setDefaultProjection(terrain.first().select('DEM').projection())
    # Open-ended outer zones retain terrain below 1251 m and above 4300 m.
    zone = dem.gte(2300).add(dem.gte(3300)).rename('zone').int()
    area = ee.Image.pixelArea().divide(1e6).rename('area_km2')
    ice_mask = ee.Image.constant(1).clip(ee.Geometry(mapping(glaciers))).unmask(0)
    channels = area.addBands(dem.multiply(area).rename('z_area')).addBands(area.multiply(ice_mask).rename('glacier_area')).addBands(zone)
    info = cached(f'sabitov-zones-{digest}-{glacier_hash[:12]}-v1', lambda: channels.reduceRegion(
        ee.Reducer.sum().repeat(3).group(3,'zone'), region, scale=30, crs='EPSG:32642', maxPixels=100000000, tileScale=4).getInfo())
    zones = []
    for g in sorted(info['groups'], key=lambda g:g['zone']):
        a, z, ice = g['sum']
        zones.append({'zone':g['zone'], 'label':['Below 2300 m','2300–3300 m','Above 3300 m'][g['zone']],
            'area_km2':a, 'mean_elevation_m':z/a, 'glacier_area_km2':ice, 'glacier_fraction':ice/a})
    write_json(OUT/'sabitov-inputs.manifest.json', {'daily_asset':ASSET, 'projection':native, 'start':output[0]['date'], 'end':output[-1]['date'],
        'rows':len(output), 'dem_asset':DEM, 'zones':zones, 'glacier_source':'GLIMS/20230607 queried directly for Pskem; latest src_date per glac_id; matching internal rock removed',
        'glacier_outline_dates':sorted({f['properties']['src_date'][:10] for f in selected}), 'glacier_features':len(selected),
        'glacier_sha256':glacier_hash, 'catchment_digest':digest, 'retrieved_at':datetime.now(timezone.utc).isoformat(),
        'temperature_method':'Basin daily ERA5 mean redistributed around DEM area-weighted mean elevation with thesis seasonal lapse rates. Preserves basin mean; does not correct ERA5 model orography or replace observed station temperature.',
        'precipitation_method':'Uniform basin daily ERA5 depth in all zones; no unsupported precipitation-elevation gradient.',
        'glacier_note':'Fixed dated outline scenario, not a glacier area time series. Rasterized at 30 m; overlaps unioned before area calculation.'})


if __name__ == '__main__':
    main()
