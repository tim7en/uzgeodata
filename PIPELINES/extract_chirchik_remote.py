"""Retrieve reproducible Pskem climate, Terra/Aqua snow and Charvak water extent.

Yearly cache files allow restart after service interruptions. Remote assets are
read only. Catchment results retain the provisional gauge-boundary designation.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from build_chirchik_case_studies import ROOT, DATA, OUT, read_csv, write_csv, write_json

CACHE = ROOT / "WORKSPACE/derived/chirchik-cache"
BANDS = [("all", 0, 9000), ("below1500", 0, 1500), ("1500to2500", 1500, 2500),
         ("2500to3500", 2500, 3500), ("above3500", 3500, 9000)]


def cached(name, computation):
    path = CACHE / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    for attempt in range(4):
        try:
            value = computation()
            break
        except Exception as error:
            if attempt==3 or not any(term in str(error).lower() for term in ['concurrent aggregations','429','503','timed out']):raise
            time.sleep(3*(attempt+1))
    write_json(path, value)
    return value


def context(ee):
    document = json.loads((OUT / "pskem-candidate-catchment.geojson").read_text(encoding="utf-8"))
    from shapely.geometry import shape, mapping
    from shapely.ops import unary_union
    geometry = mapping(unary_union([shape(f["geometry"]) for f in document["features"]]))
    digest = hashlib.sha256(json.dumps(geometry, sort_keys=True).encode()).hexdigest()[:12]
    return ee.Geometry(geometry), digest


def extract_climate(ee, start, end):
    region, digest = context(ee)
    asset = "ECMWF/ERA5_LAND/MONTHLY_AGGR"
    source = ee.ImageCollection(asset)
    native = source.first().select(0).projection().getInfo()
    variables = [("temperature_2m", "temperature_c", 1, -273.15), ("total_precipitation_sum", "precipitation_mm", 1000, 0),
                 ("snow_depth_water_equivalent", "swe_mm", 1000, 0), ("runoff_sum", "runoff_mm", 1000, 0)]
    output = []
    for year in range(start, end + 1):
        def reduce_image(image):
            area = ee.Image.pixelArea()
            channels = []
            for band, name, factor, offset in variables:
                value = image.select(band).multiply(factor).add(offset)
                channels += [value.multiply(area).rename(name), area.updateMask(value.mask()).rename(name + "_area")]
            sums = ee.Image.cat(channels).reduceRegion(ee.Reducer.sum(), region,
                crs=native['crs'], crsTransform=native['transform'], maxPixels=10000000)
            values = {name: ee.Number(sums.get(name)).divide(ee.Number(sums.get(name + "_area"))) for _, name, _, _ in variables}
            return ee.Feature(None, values).set({"period": image.date().format("YYYY-MM"), "source_image": image.get("system:index")})
        info = cached(f"climate-{digest}-{year}-v1", lambda: source.filterDate(f"{year}-01-01", f"{year+1}-01-01").map(reduce_image).getInfo())
        rows = [f["properties"] for f in info["features"]]
        if len(rows) != 12:
            raise ValueError(f"Incomplete climate year {year}")
        output.extend({**r, "source_asset": asset, "spatial_support": "candidate_gauge_catchment_area_weighted_mean"} for r in rows)
        print(f"Basin climate {year}: {len(rows)} months", flush=True)
    write_csv(OUT / "pskem-basin-climate-monthly.csv", output,
        ["period", "temperature_c", "precipitation_mm", "swe_mm", "runoff_mm", "source_asset", "source_image", "spatial_support"])


def extract_snow(ee, start, end, sensors):
    region, digest = context(ee)
    links = [r for r in read_csv(DATA / "pskem-station-basin-links.csv") if r["station_id"] in ["uz:station/meteo-419704", "uz:station/meteo-422709"]]
    points = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([float(r['longitude']),float(r['latitude'])]),
                    {"station_id":r['station_id']}) for r in links])
    dem = ee.Image("USGS/SRTMGL1_003")
    for sensor in sensors:
        asset = f"MODIS/061/{'MOD' if sensor in ['terra','combined'] else 'MYD'}10A1"
        source = ee.ImageCollection(asset)
        projection = source.first().select(0).projection()
        masks = {name: dem.gte(lo).And(dem.lt(hi)) for name, lo, hi in BANDS}
        areas = cached(f"snow-areas-{digest}-v2", lambda: ee.Image.cat([
            ee.Image.pixelArea().updateMask(masks[name]).rename(name) for name, _, _ in BANDS
        ]).reduceRegion(ee.Reducer.sum(), region, scale=500, crs=projection, maxPixels=10000000).getInfo())
        basin_rows, station_rows = [], []
        for year in range(start, end + 1):
            if sensor == "aqua" and year < 2002:
                continue
            annual = source.filterDate(f"{year}-01-01", f"{year+1}-01-01")

            def classify(image):
                if sensor=='combined':return image.select('ndsi')
                ndsi = image.select("NDSI_Snow_Cover")
                flags = image.select("NDSI_Snow_Cover_Algorithm_Flags_QA")
                valid = ndsi.gte(0).And(ndsi.lte(100)).And(image.select("NDSI_Snow_Cover_Basic_QA").lte(1)).And(flags.bitwiseAnd(129).eq(0))
                return ndsi.updateMask(valid).rename("ndsi")

            if sensor=='combined':
                def clean(image):
                    ndsi=image.select('NDSI_Snow_Cover');flags=image.select('NDSI_Snow_Cover_Algorithm_Flags_QA')
                    valid=ndsi.gte(0).And(ndsi.lte(100)).And(image.select('NDSI_Snow_Cover_Basic_QA').lte(1)).And(flags.bitwiseAnd(129).eq(0))
                    return ndsi.updateMask(valid).rename('ndsi').clip(region.buffer(1000,100)).copyProperties(image,['system:time_start'])
                terra=annual.map(clean)
                aqua=ee.ImageCollection('MODIS/061/MYD10A1').filterDate(f'{year}-01-01',f'{year+1}-01-01').map(clean)
                times=terra.merge(aqua).aggregate_array('system:time_start').distinct().sort()
                empty=ee.Image.constant(0).rename('ndsi').updateMask(ee.Image.constant(0)).setDefaultProjection(projection).clip(region.buffer(1000,100))
                def combine(timestamp):
                    day=ee.Date(timestamp);t=terra.filterDate(day,day.advance(1,'day'));a=aqua.filterDate(day,day.advance(1,'day'))
                    primary=ee.Image(ee.Algorithms.If(t.size(),t.first(),empty))
                    secondary=ee.Image(ee.Algorithms.If(a.size(),a.first(),empty))
                    return primary.unmask(secondary).set({'system:time_start':timestamp,'system:index':day.format('YYYY_MM_dd')})
                annual=ee.ImageCollection.fromImages(times.map(combine))

            def basin_day(image):
                ndsi = classify(image)
                area = ee.Image.pixelArea()
                channels = []
                for name, _, _ in BANDS:
                    a = area.updateMask(masks[name]).updateMask(ndsi.mask())
                    channels += [a.rename(name + "_valid"), a.multiply(ndsi.gt(0)).rename(name + "_snow"),
                                 a.multiply(ndsi.gte(40)).rename(name + "_snow40")]
                reduced = ee.Image.cat(channels).reduceRegion(ee.Reducer.sum(), region, scale=500,
                    crs=projection, maxPixels=10000000, tileScale=2)
                return ee.Feature(None, reduced).set({"date": image.date().format("YYYY-MM-dd"), "source_image": image.get("system:index")})

            info = cached(f"snow-{sensor}-{digest}-{year}-v2", lambda: annual.map(basin_day).getInfo())
            for feature in info['features']:
                props = feature['properties']
                for name, lo, hi in BANDS:
                    valid = props.get(name + '_valid') or 0
                    snow = props.get(name + '_snow') or 0
                    snow40 = props.get(name + '_snow40') or 0
                    basin_rows.append({"date":props['date'],"sensor":sensor,"elevation_band":name,"minimum_m":lo,"maximum_m":hi,
                        "area_km2":areas[name]/1e6,"valid_area_percent":100*valid/areas[name],
                        "snow_cover_percent":100*snow/valid if valid else None,"snow40_cover_percent":100*snow40/valid if valid else None,
                        "source_asset":asset if sensor!='combined' else 'MODIS/061/MOD10A1 + MODIS/061/MYD10A1',"source_image":props['source_image']})
            # Point observations exist for 2020 onward; retain every date including masked retrievals.
            if year >= 2020:
                def station_day(image):
                    ndsi = classify(image)
                    return ndsi.reduceRegions(points, ee.Reducer.first(), crs=projection).map(lambda f: f.setGeometry(None).set({
                        "date":image.date().format("YYYY-MM-dd"),"source_image":image.get("system:index")}))
                def station_year():
                    features=[]
                    for month in range(1,13):
                        part=annual.filter(ee.Filter.calendarRange(month,month,'month'))
                        record=cached(f'snow-stations-{sensor}-{digest}-{year}-{month:02}-v2',lambda:ee.FeatureCollection(part.toList(part.size()).map(lambda image:station_day(ee.Image(image)))).flatten().getInfo())
                        features.extend(record['features'])
                    return {'features':features}
                records = cached(f"snow-stations-{sensor}-{digest}-{year}-v2", station_year)
                station_rows.extend({**f['properties'],"ndsi":f['properties'].get('first'),"sensor":sensor,"source_asset":asset if sensor!='combined' else 'MODIS/061/MOD10A1 + MODIS/061/MYD10A1'} for f in records['features'])
            print(f"MODIS {sensor} {year}: {len(info['features'])} basin days", flush=True)
            # Checkpoints are complete calendar years; the manifest records the requested span.
            write_csv(OUT / f"pskem-modis-{sensor}-daily.csv", basin_rows,
                      ['date','sensor','elevation_band','minimum_m','maximum_m','area_km2','valid_area_percent','snow_cover_percent','snow40_cover_percent','source_asset','source_image'])
            if station_rows:
                write_csv(OUT / f"station-modis-{sensor}-daily.csv",station_rows,['date','station_id','sensor','ndsi','source_asset','source_image'])


def extract_reservoir(ee,start,end):
    doc=json.loads((DATA/'water-bodies-transboundary.geojson').read_text(encoding='utf-8'))
    matches=[f for f in doc['features'] if str(f['properties'].get('water_body_id'))=='14452']
    if len(matches)!=1:
        raise ValueError('Charvak HydroLAKES 14452 polygon not uniquely found')
    region=ee.Geometry(matches[0]['geometry']).buffer(1000,30)
    asset='JRC/GSW1_4/MonthlyHistory'
    source=ee.ImageCollection(asset)
    rows=[]
    for year in range(start,min(end,2021)+1):
        def reduce_image(image):
            water=image.select('water')
            area=ee.Image.pixelArea()
            sums=ee.Image.cat([area.rename('domain_m2'),area.multiply(water.gt(0)).rename('valid_m2'),
                area.multiply(water.eq(2)).rename('water_m2')]).reduceRegion(ee.Reducer.sum(),region,scale=30,maxPixels=10000000)
            return ee.Feature(None,sums).set({'period':image.date().format('YYYY-MM'),'source_image':image.get('system:index')})
        info=cached(f'charvak-jrc-{year}-buffer1000-v1',lambda:source.filterDate(f'{year}-01-01',f'{year+1}-01-01').map(reduce_image).getInfo())
        for f in info['features']:
            p=f['properties']; valid=p.get('valid_m2') or 0
            rows.append({'period':p['period'],'water_area_km2':(p.get('water_m2') or 0)/1e6 if valid else None,
                         'valid_area_percent':100*valid/p['domain_m2'],'domain_area_km2':p['domain_m2']/1e6,
                         'source_asset':asset,'source_image':p['source_image']})
        print(f'Charvak JRC {year}: {len(info["features"])} months',flush=True)
    write_csv(OUT/'charvak-jrc-monthly.csv',rows,['period','water_area_km2','valid_area_percent','domain_area_km2','source_asset','source_image'])


def verify_reservoir(ee,start,end):
    doc=json.loads((DATA/'water-bodies-transboundary.geojson').read_text(encoding='utf-8'))
    feature=next(f for f in doc['features'] if str(f['properties'].get('water_body_id'))=='14452')
    region=ee.Geometry(feature['geometry']).buffer(1000,30)
    asset='COPERNICUS/S2_SR_HARMONIZED';rows=[]
    for year in range(max(start,2018),min(end,2021)+1):
        for month in range(1,13):
            begin=ee.Date.fromYMD(year,month,1)
            source=ee.ImageCollection(asset).filterBounds(region).filterDate(begin,begin.advance(1,'month')).filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE',70))
            def scene(image):
                scl=image.select('SCL')
                clear=scl.neq(0).And(scl.neq(1)).And(scl.neq(3)).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
                green=image.select('B3');swir=image.select('B11');nir=image.select('B8');red=image.select('B4')
                mndwi=green.subtract(swir).divide(green.add(swir));ndvi=nir.subtract(red).divide(nir.add(red))
                mask=clear.And(mndwi.mask()).And(ndvi.mask())
                area=ee.Image.pixelArea();valid=area.updateMask(mask)
                values=ee.Image.cat([area.rename('domain_m2'),valid.rename('valid_m2'),
                    valid.multiply(mndwi.gt(0).And(ndvi.lt(.3))).rename('water_m2'),
                    valid.multiply(mndwi.gt(.1).And(ndvi.lt(.3))).rename('water01_m2')]).reduceRegion(ee.Reducer.sum(),region,scale=20,crs=image.select('B11').projection(),maxPixels=10000000)
                return ee.Feature(None,values).set({'source_image':image.get('system:index'),'date':image.date().format('YYYY-MM-dd')})
            info=cached(f'charvak-s2-{year}-{month:02}-v1',lambda:source.map(scene).getInfo())
            choices=[]
            for f in info['features']:
                p=f['properties'];coverage=(p.get('valid_m2') or 0)/p['domain_m2']
                choices.append({**p,'coverage':coverage})
            if choices:
                p=sorted(choices,key=lambda p:(-p['coverage'],p['date']))[0]
                rows.append({'period':f'{year}-{month:02}','date':p['date'],'valid_area_percent':p['coverage']*100,
                    'water_area_km2':(p.get('water_m2') or 0)/1e6 if p['coverage'] else None,
                    'water01_area_km2':(p.get('water01_m2') or 0)/1e6 if p['coverage'] else None,
                    'source_asset':asset,'source_image':p['source_image'],'candidate_scenes':len(choices)})
            print(f'Charvak Sentinel-2 {year}-{month:02}: {len(choices)} candidate scenes',flush=True)
    write_csv(OUT/'charvak-sentinel2-check.csv',rows,['period','date','valid_area_percent','water_area_km2','water01_area_km2','source_asset','source_image','candidate_scenes'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task',choices=['climate','snow','reservoir','reservoir-check'],required=True)
    parser.add_argument('--start',type=int,default=2000)
    parser.add_argument('--end',type=int,default=2024)
    parser.add_argument('--sensors',nargs='+',choices=['terra','aqua','combined'],default=['terra','aqua','combined'])
    args=parser.parse_args()
    import ee
    ee.Initialize(project='ee-sabitovty');ee.data.setDeadline(300000)
    if args.task=='climate':extract_climate(ee,args.start,args.end)
    elif args.task=='snow':extract_snow(ee,args.start,args.end,args.sensors)
    elif args.task=='reservoir':extract_reservoir(ee,args.start,args.end)
    else:verify_reservoir(ee,args.start,args.end)
    write_json(OUT/f'remote-{args.task}{"-"+"-".join(args.sensors) if args.task=="snow" else ""}.manifest.json',{
        'status':'complete','start_year':args.start,'end_year':min(args.end,2021) if args.task=='reservoir' else args.end,
        'retrieved_at':datetime.now(timezone.utc).isoformat(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'spatial_scope':'Provisional Pskem gauge catchment; Charvak reference polygon plus 1000m buffer for reservoir task',
        'snow_method':'NDSI snow >0; >=40 sensitivity; best/good QA; exclude inland-water and high-solar-zenith flags; no cloud filling. Daily valid area denominator retained.',
        'reservoir_method':'JRC Landsat-derived water class 2; no-data class 0 excluded; area only, not storage.'})


if __name__=='__main__':main()
