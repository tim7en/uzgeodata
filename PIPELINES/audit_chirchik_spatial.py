"""Audit the existing gauge coordinate and station terrain without relocating them."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.ops import transform
from pyproj import Transformer

from build_chirchik_case_studies import ROOT, DATA, OUT, read_csv, write_json


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--terrain',action='store_true');args=parser.parse_args()
    links=read_csv(DATA/'pskem-station-basin-links.csv')
    gauge=next(r for r in links if r['station_id']=='uz:station/gauge-16290')
    lon,lat=float(gauge['longitude']),float(gauge['latitude'])
    to_utm=Transformer.from_crs(4326,32642,always_xy=True).transform
    point=transform(to_utm,Point(lon,lat))
    source=ROOT/'PUBLISHED/data/hydrography/rivers-unified.geojson'
    features=json.loads(source.read_text(encoding='utf-8'))['features'];candidates=[]
    for feature in features:
        geometry=shape(feature['geometry']);west,south,east,north=geometry.bounds
        if west>lon+.2 or east<lon-.2 or south>lat+.2 or north<lat-.2:continue
        distance=point.distance(transform(to_utm,geometry))
        if distance<=2000:candidates.append({'distance_m':distance,**feature['properties']})
    candidates.sort(key=lambda r:r['distance_m'])
    write_json(OUT/'gauge-reach-audit.json',{'station_id':gauge['station_id'],'longitude':lon,'latitude':lat,'candidates':candidates,
        'status':'ambiguous_station_coordinate_requires_review','method':'Distances in UTM 42N to held HydroRIVERS geometry; no automatic coordinate change or reach assignment.',
        'source':source.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'interpretation':'Nearest reach is a small tributary. Larger Pskem reaches are nearby. Proximity alone is not a defensible gauge snap; verify original station metadata and river identity.'})
    print('Gauge reach candidates:',[(r['HYRIV_ID'],round(r['distance_m'],1),r['UPLAND_SKM']) for r in candidates[:3]])
    if not args.terrain:return
    import ee
    ee.Initialize(project='ee-sabitovty')
    projection=ee.ImageCollection('ECMWF/ERA5_LAND/MONTHLY_AGGR').first().select(0).projection().getInfo()
    a,b,c,d,e,f=projection['transform'];dem=ee.Image('USGS/SRTMGL1_003');rows=[]
    for r in links:
        if r['station_role']!='meteorological':continue
        lon,lat=float(r['longitude']),float(r['latitude']);p=ee.Geometry.Point([lon,lat])
        ix,iy=math.floor((lon-c)/a),math.floor((lat-f)/e)
        x0,x1=c+a*ix,c+a*(ix+1);y0,y1=f+e*iy,f+e*(iy+1)
        bounds=[min(x0,x1),min(y0,y1),max(x0,x1),max(y0,y1)]
        cell=ee.Geometry.Rectangle(bounds,'EPSG:4326',False)
        props=ee.Dictionary({'station_dem_m':dem.reduceRegion(ee.Reducer.first(),p,scale=30).get('elevation'),
          'era5_cell_dem_mean_m':dem.reduceRegion(ee.Reducer.mean(),cell,scale=90,maxPixels=1000000).get('elevation')}).getInfo()
        rows.append({'station_id':r['station_id'],**props,'cell_bounds':bounds,'source_asset':'USGS/SRTMGL1_003'})
    write_json(OUT/'station-terrain-context.json',{'rows':rows,'interpretation':'SRTM terrain estimates, not surveyed station elevations or ERA5 model orography. Cell elevation difference indicates possible representativeness mismatch but does not prove the cause of bias.'})


if __name__=='__main__':main()
