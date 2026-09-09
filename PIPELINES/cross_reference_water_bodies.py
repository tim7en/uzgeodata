"""Audit dam–lake links with native IDs, local distances and separate properties.

Nearness is a review candidate, never permission to rename a lake. Outputs are
derived; source GDW and HydroLAKES records stay unchanged.
"""
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from difflib import SequenceMatcher
from pyproj import CRS,Transformer
from shapely.geometry import Point,shape,mapping
from shapely.ops import transform

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'PUBLISHED/data/hydroclimate'


def load_csv(path):
    with path.open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))


def number(value):
    try:return float(value) if value not in ['',None] else None
    except (ValueError,TypeError):return None


def identifier(value):
    value=number(value)
    return str(int(value)) if value and value>0 else None


def normalise_name(value):
    text=unicodedata.normalize('NFKD',value or '').casefold()
    return re.sub(r'[^\w]','',text)


def name_check(dam,lake):
    a=normalise_name(dam.get('reservoir_name') or dam.get('dam_name'));b=normalise_name(lake.get('name'))
    if not a or not b:return 'name_missing',None
    ratio=SequenceMatcher(None,a,b).ratio()
    return ('same_normalised_name' if a==b else 'similar_spelling' if ratio>=.72 else 'different_names'),round(ratio,3)


def relation(dam,lake,distance):
    if identifier(dam.get('hylak_id'))==identifier(lake.get('water_body_id')) and identifier(dam.get('hylak_id')):
        return 'native_hydrolakes_id'
    if identifier(dam.get('grand_id'))==identifier(lake.get('grand_id')) and identifier(dam.get('grand_id')):
        return 'native_grand_id'
    return 'nearby_candidate' if distance<=2000 else None


def compare(dam,lake,distance,method):
    status,similarity=name_check(dam,lake)
    da,la=number(dam.get('reservoir_area_km2')),number(lake.get('area_km2'))
    capacity,storage=number(dam.get('capacity_mcm')),number(lake.get('storage_volume_mcm'))
    return {'dam_id':int(dam['dam_id']),'water_body_id':int(lake['water_body_id']),'link_method':method,
        'distance_to_polygon_m':round(distance,1),'spatial_check':'within_2km' if distance<=2000 else 'spatial_disagreement',
        'dam_name':dam.get('dam_name',''),'reservoir_name':dam.get('reservoir_name',''),'lake_name':lake.get('name',''),
        'name_check':status,'name_similarity':similarity,'dam_country':dam.get('country',''),'lake_country':lake.get('country',''),
        'country_check':'same' if dam.get('country')==lake.get('country') else 'different_or_missing',
        'lake_type':lake.get('water_body_type'),'dam_area_km2':da,'lake_area_km2':la,
        'area_difference_percent':round(100*(da-la)/la,2) if da is not None and la and la>0 else None,
        'dam_capacity_mcm':capacity,'lake_storage_mcm':storage,
        'storage_difference_percent':round(100*(capacity-storage)/storage,2) if capacity is not None and storage and storage>0 else None,
        'dam_position_source':dam.get('position_source'),'dam_level12':dam.get('hybas_id_level12'),'lake_level12':lake.get('hybas_id_level12'),
        'interpretation':'Native catalogue association; differences retained for review.' if method.startswith('native') else 'Proximity only; identity unconfirmed. No name transferred.'}


def build():
    lake_features=json.loads((OUT/'water-bodies-transboundary.geojson').read_text(encoding='utf-8'))['features']
    lake_rows={identifier(r['water_body_id']):r for r in load_csv(OUT/'water-bodies-transboundary.csv')}
    dams=load_csv(OUT/'dams-transboundary.csv');geometries=[shape(f['geometry']) for f in lake_features];pairs=[]
    for dam in dams:
        lon,lat=number(dam['longitude']),number(dam['latitude'])
        if lon is None or lat is None:continue
        local=CRS.from_proj4(f'+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m')
        project=Transformer.from_crs(4326,local,always_xy=True).transform;point=Point(0,0)
        for f,g in zip(lake_features,geometries):
            lake=lake_rows[identifier(f['properties']['water_body_id'])];native=relation(dam,lake,float('inf'))
            west,south,east,north=g.bounds
            if not native and (west>lon+.08 or east<lon-.08 or south>lat+.04 or north<lat-.04):continue
            distance=point.distance(transform(project,g));method=native or relation(dam,lake,distance)
            if method:pairs.append(compare(dam,lake,distance,method))
    linked={int(r['water_body_id']):[] for r in pairs}
    for pair in pairs:linked[pair['water_body_id']].append(pair)
    features=[]
    for feature,g in zip(lake_features,geometries):
        raw=lake_rows[identifier(feature['properties']['water_body_id'])];props={**feature['properties'],**raw}
        matches=linked.get(int(raw['water_body_id']),[]);native=[r for r in matches if r['link_method'].startswith('native')]
        usable=[r for r in native if r['spatial_check']=='within_2km'];aliases=sorted({r['reservoir_name'] or r['dam_name'] for r in usable if r['reservoir_name'] or r['dam_name']})
        props.update(source_name=raw['name'],display_name=raw['name'] or (aliases[0] if len(aliases)==1 else f"Unnamed {raw['water_body_type'].replace('_',' ')} · {raw['water_body_id']}"),
            display_name_source='HydroLAKES' if raw['name'] else 'GDW linked dam/reservoir name' if len(aliases)==1 else 'catalogue identifier',
            reservoir_aliases=aliases,dam_links=matches)
        point=g.representative_point();props['symbol_longitude']=point.x;props['symbol_latitude']=point.y
        features.append({'type':'Feature','geometry':mapping(g.simplify(.001,preserve_topology=True)),'properties':props})
    def write(name,data):
        dest=OUT/name;temp=dest.with_suffix(dest.suffix+'.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n',encoding='utf-8');temp.replace(dest)
    write('water-bodies-reviewed.geojson',{'type':'FeatureCollection','features':features})
    count=Counter(r['link_method'] for r in pairs);summary={'dams':len(dams),'water_bodies':len(features),'pairs':len(pairs),'link_methods':dict(count),
        'native_spatial_disagreements':sum(r['spatial_check']=='spatial_disagreement' for r in pairs if r['link_method'].startswith('native')),
        'different_native_names':sum(r['name_check']=='different_names' for r in pairs if r['link_method'].startswith('native')),
        'filled_display_names':sum(f['properties']['display_name_source']=='GDW linked dam/reservoir name' for f in features),
        'unmatched_dams':len({int(r['dam_id']) for r in dams}-{r['dam_id'] for r in pairs})}
    write('dam-lake-review.json',{'summary':summary,'pairs':pairs,'method':'Native HydroLAKES/GRanD IDs first; all additional polygons within 2000 m retained as unconfirmed candidates. Distances use dam-centred azimuthal equidistant projection.',
        'limits':'Distance is to mapped polygon, not centroid. Shoreline epochs, snapped dam positions, transliteration and cross-border country labels can differ. Numeric differences are not automatically source errors. No source name/property was overwritten.',
        'generated_at':datetime.now(timezone.utc).isoformat(),'inputs':[{'file':name,'sha256':hashlib.sha256((OUT/name).read_bytes()).hexdigest()} for name in ['dams-transboundary.csv','water-bodies-transboundary.csv','water-bodies-transboundary.geojson']]})
    with (OUT/'dam-lake-review.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(pairs[0]));writer.writeheader();writer.writerows(pairs)
    lines=['# Reservoir and lake cross-reference','',json.dumps(summary,indent=2),'',
        'Native identifiers take precedence over proximity. Additional polygons within 2 km are candidates only. Source names remain intact; missing display names can use a unique spatially consistent native-linked GDW reservoir name, explicitly attributed.','',
        '| Dam | Reservoir name | HydroLAKES name / ID | Association | Distance (m) | Name check | Area difference (%) |',
        '| --- | --- | --- | --- | ---: | --- | ---: |']
    for r in pairs:lines.append(f"| {r['dam_name'] or r['dam_id']} | {r['reservoir_name']} | {r['lake_name'] or 'Unnamed'} / {r['water_body_id']} | {r['link_method']} | {r['distance_to_polygon_m']} | {r['name_check']} | {r['area_difference_percent'] if r['area_difference_percent'] is not None else '—'} |")
    lines+=['','Source: existing Global Dam Watch v1.0 and HydroLAKES v1.0 deliveries. Nominal capacity, catalogue volume and current storage are different quantities. Nearness and spelling similarity do not establish identity. See JSON/CSV for both source values, IDs, countries and position provenance.']
    (OUT/'dam-lake-review.md').write_text('\n'.join(lines)+'\n',encoding='utf-8');print(json.dumps(summary,indent=2))


if __name__=='__main__':build()
