"""Scalable elevation, land-cover and surface-energy summaries for Pskem.

250 m elevation bins do not downscale ERA5's ~9 km information. Land-cover
statistics use 10 m classifications; map thumbnails are overview displays.
"""
import argparse
import calendar
import json
from datetime import datetime,timezone

import requests

from build_chirchik_case_studies import DATA,OUT,write_csv,write_json
from extract_chirchik_remote import cached,context

DEM='COPERNICUS/DEM/GLO30_2024_1'
LULC='projects/sat-io/open-datasets/landcover/ESRI_Global-LULC_10m_TS'
CLASSES={1:'Water',2:'Trees',4:'Flooded vegetation',5:'Crops',7:'Built area',8:'Bare ground',9:'Snow/ice',10:'Clouds',11:'Rangeland'}
COLORS={1:'#419bdf',2:'#397d49',4:'#7a87c6',5:'#e49635',7:'#c4281b',8:'#a59b8f',9:'#d9f1fa',10:'#ffffff',11:'#c8c688'}


def profiles(ee):
    region,digest=context(ee);collection=ee.ImageCollection(DEM).filterBounds(region)
    dem=collection.mosaic().select('DEM').setDefaultProjection(collection.first().select('DEM').projection())
    band=dem.divide(250).floor().int().rename('band');area=ee.Image.pixelArea().divide(1e6)
    era=ee.ImageCollection('ECMWF/ERA5_LAND/MONTHLY_AGGR').filterDate('2010-01-01','2025-01-01')
    temp=era.select('temperature_2m').mean().subtract(273.15).rename('temperature_c')
    precip=era.select('total_precipitation_sum').sum().multiply(1000/15).rename('precipitation_mm_year')
    runoff=era.select('runoff_sum').sum().multiply(1000/15).rename('runoff_mm_year')
    # Group weighted sums in one reduction, preserving topographic area at 30 m.
    def grouped(image,names,scale):
        channels=[area.rename('area_km2')]+[image.select(name).multiply(area).rename(name) for name in names]+[band]
        reducer=ee.Reducer.sum().repeat(len(names)+1).group(groupField=len(names)+1,groupName='band')
        return ee.Image.cat(channels).reduceRegion(reducer,region,scale=scale,crs='EPSG:32642',maxPixels=100000000,tileScale=4).getInfo()
    summary=cached(f'profiles-{digest}-v1',lambda:grouped(ee.Image.cat([temp,precip,runoff]),['temperature_c','precipitation_mm_year','runoff_mm_year'],30))
    rows=[]
    for g in summary['groups']:
        a,t,p,r=g['sum'];lo=int(g['band'])*250
        rows.append({'minimum_m':lo,'maximum_m':lo+250,'area_km2':a,'temperature_c':t/a,'precipitation_mm_year':p/a,
            'runoff_mm_year':r/a,'runoff_generated_mcm_year':r/1000})
    cumulative=0
    for row in sorted(rows,key=lambda r:-r['minimum_m']):
        cumulative+=row['runoff_generated_mcm_year'];row['cumulative_runoff_above_mcm_year']=cumulative
    rows.sort(key=lambda r:r['minimum_m']);write_csv(OUT/'elevation-profiles.csv',rows,list(rows[0]))
    land=ee.ImageCollection(LULC).filterBounds(region)
    latest=int(ee.Date(land.aggregate_max('system:time_start')).format('YYYY').getInfo());land_rows=[]
    for year in range(2017,latest+1):
        image=land.filterDate(f'{year}-01-01',f'{year+1}-01-01').mosaic().select('b1')
        category=band.multiply(100).add(image).rename('category').int()
        info=cached(f'landcover-{digest}-{year}-10m-v1',lambda:area.addBands(category).reduceRegion(
            ee.Reducer.sum().group(1,'category'),region,scale=10,crs='EPSG:32642',maxPixels=100000000,tileScale=4).getInfo())
        for g in info.get('groups',[]):
            key=int(g['category']);code=key%100
            land_rows.append({'year':year,'minimum_m':key//100*250,'maximum_m':key//100*250+250,'class_code':code,
                'class':CLASSES.get(code,'No data / unclassified'),'area_km2':g['sum'],'valid_class':code in CLASSES and code!=10})
        print(f'Esri land cover {year}: 10 m elevation-class areas',flush=True)
    write_csv(OUT/'landcover-elevation.csv',land_rows,list(land_rows[0]))
    comparison=cached(f'dem-comparison-{digest}-v1',lambda:dem.subtract(ee.Image('USGS/SRTMGL1_003')).reduceRegion(
        ee.Reducer.mean().combine(ee.Reducer.stdDev(),sharedInputs=True),region,scale=90,maxPixels=10000000).getInfo())
    bounds=region.bounds(100).coordinates().getInfo()[0];west=min(p[0] for p in bounds);east=max(p[0] for p in bounds);south=min(p[1] for p in bounds);north=max(p[1] for p in bounds)
    rectangle=ee.Geometry.Rectangle([west,south,east,north])
    # These are data-derived rendered rasters, not AI illustrations.
    for name,image in [('terrain',ee.Terrain.hillshade(dem.reproject('EPSG:32642',None,60)).visualize(min=60,max=240)),
        ('landcover',land.filterDate(f'{latest}-01-01',f'{latest+1}-01-01').mosaic().select('b1').remap(list(CLASSES),list(range(len(CLASSES)))).visualize(min=0,max=len(CLASSES)-1,palette=list(COLORS.values())))]:
        path=OUT/f'pskem-{name}-overview.png'
        if not path.exists():
            url=image.clip(region).getThumbURL({'region':rectangle,'dimensions':1400,'format':'png','crs':'EPSG:4326'})
            response=requests.get(url,timeout=180);response.raise_for_status();path.write_bytes(response.content)
    write_json(OUT/'environment-profile.manifest.json',{'dem_asset':DEM,'dem_nominal_resolution_m':30,'elevation_bin_m':250,'landcover_asset':LULC,
        'landcover_years':[2017,latest],'landcover_source':'Impact Observatory / Esri / Microsoft; community-hosted Earth Engine mirror',
        'climate_reference':'2010–2024','climate_support':'ERA5 native coarse grid sampled across DEM elevation bins; not fine-resolution downscaling',
        'temperature_statistic':'Mean of 180 monthly means','runoff_interpretation':'Local ERA5 runoff generated by elevation, summed from high to low. Not routed flow or measured discharge by elevation.',
        'dem_comparison':comparison,'dem_note':'Copernicus and SRTM difference is inter-product spread, not error against ground control. No verified open sub-30 m DEM was identified for this basin.',
        'map_bounds':[[south,west],[north,east]],'class_colors':COLORS,'classes':CLASSES,'retrieved_at':datetime.now(timezone.utc).isoformat()})


def energy(ee,start,end):
    region,digest=context(ee);source=ee.ImageCollection('ECMWF/ERA5_LAND/MONTHLY_AGGR');native=source.first().select(0).projection()
    latest=source.sort('system:time_start',False).first().date().format('YYYY-MM').getInfo();output=[]
    for year in range(start,int(latest[:4])+1):
        def image_row(image):
            begin=image.date();seconds=begin.advance(1,'month').difference(begin,'second')
            fields=[image.select('temperature_2m').subtract(273.15).rename('temperature_c'),
                image.select('total_precipitation_sum').multiply(1000).rename('precipitation_mm'),
                image.select('total_evaporation_sum').multiply(-1000).rename('evapotranspiration_mm'),
                image.select('potential_evaporation_sum').multiply(-1000).rename('potential_et_mm'),
                image.select('surface_solar_radiation_downwards_sum').divide(seconds).rename('solar_down_wm2'),
                image.select('surface_net_solar_radiation_sum').divide(seconds).rename('net_solar_wm2'),
                image.select('runoff_sum').multiply(1000).rename('runoff_mm')]
            values=ee.Image.cat(fields).reduceRegion(ee.Reducer.mean(),region,crs=native,scale=11132,maxPixels=1000000)
            return ee.Feature(None,values).set({'period':begin.format('YYYY-MM'),'source_image':image.get('system:index')})
        info=cached(f'energy-era5-{digest}-{year}-{latest if year==int(latest[:4]) else "complete"}-v1',lambda:source.filterDate(f'{year}-01-01',f'{year+1}-01-01').map(image_row).getInfo())
        output.extend(f['properties'] for f in info['features']);print(f'ERA5 energy {year}: {len(info["features"])} months',flush=True)
    write_csv(OUT/'pskem-energy-monthly.csv',output,list(output[0]))
    products={'lst':('MODIS/061/MOD11A2',1000),'et':('MODIS/061/MOD16A2GF',500),'albedo':('MODIS/061/MCD43A3',500)}
    current={}
    for product,(asset,scale) in products.items():
        collection=ee.ImageCollection(asset);current[product]=collection.sort('system:time_start',False).first().date().format('YYYY-MM-dd').getInfo()
        rows=[]
        for year in range(start,min(end,int(current[product][:4]))+1):
            def reduce_image(image):
                if product=='lst':
                    qa=image.select('QC_Day');v=image.select('LST_Day_1km').multiply(.02).subtract(273.15).updateMask(qa.bitwiseAnd(3).eq(0).And(qa.rightShift(6).bitwiseAnd(3).lte(1)))
                elif product=='et':
                    raw=image.select('ET');qa=image.select('ET_QC')
                    v=raw.multiply(.1).updateMask(raw.gte(0).And(raw.lt(32700)).And(qa.bitwiseAnd(1).eq(0)).And(qa.rightShift(5).bitwiseAnd(7).lte(1)))
                else:
                    raw=image.select('Albedo_BSA_shortwave');qa=image.select('BRDF_Albedo_Band_Mandatory_Quality_shortwave')
                    v=raw.multiply(.001).updateMask(raw.gte(0).And(raw.lte(1000)).And(qa.eq(0)))
                area=ee.Image.pixelArea();values=ee.Image.cat([area.rename('total_area'),area.updateMask(v.mask()).rename('valid_area'),v.multiply(area).rename('weighted_value')]).reduceRegion(
                    ee.Reducer.sum(),region,scale=scale,crs=image.select(0).projection(),maxPixels=10000000)
                return ee.Feature(None,values).set({'date':image.date().format('YYYY-MM-dd'),'source_image':image.get('system:index')})
            stamp=current[product] if year==int(current[product][:4]) else 'complete'
            # Prior completed-year caches are compatible; live years are date-keyed.
            from extract_chirchik_remote import CACHE
            old=CACHE/f'energy-{product}-{digest}-{year}-v1.json'
            if old.exists() and year<int(current[product][:4]):info=json.loads(old.read_text(encoding='utf-8'))
            else:info=cached(f'energy-{product}-{digest}-{year}-{stamp}-v1',lambda:collection.filterDate(f'{year}-01-01',f'{year+1}-01-01').map(reduce_image).getInfo())
            for f in info['features']:
                p=f['properties'];valid=p.get('valid_area') or 0
                rows.append({'date':p['date'],'value':p['weighted_value']/valid if valid else None,'valid_area_percent':100*valid/p['total_area'],'source_asset':asset,'source_image':p['source_image']})
            print(f'MODIS {product} {year}: {len(info["features"])} composites',flush=True)
        write_csv(OUT/f'pskem-{product}-composites.csv',rows,['date','value','valid_area_percent','source_asset','source_image'])
    write_json(OUT/'environment-energy.manifest.json',{'era5_latest_available':latest,'modis_latest_available':current,'modis_extracted_years':[start,end],
        'era5_support':'Basin mean at native grid; monthly accumulations converted to mm and time-mean W/m²',
        'et_note':'MOD16 is modelled terrestrial evapotranspiration; masked non-vegetated/water/snow areas restrict its footprint. It is not basin-wide measured ET.',
        'lst_note':'Clear-sky daytime land-surface skin temperature, not 2 m air temperature. Eight-day composites.',
        'albedo_note':'Black-sky shortwave albedo; daily estimates use a moving 16-day window, so adjacent days are not independent.',
        'retrieved_at':datetime.now(timezone.utc).isoformat()})


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--task',choices=['profiles','energy'],required=True)
    parser.add_argument('--start',type=int,default=2000);parser.add_argument('--end',type=int,default=2024);args=parser.parse_args()
    import ee
    ee.Initialize(project='ee-sabitovty');ee.data.setDeadline(300000)
    if args.task=='profiles':profiles(ee)
    else:energy(ee,args.start,args.end)


if __name__=='__main__':main()
