"""Retrieve reproducible Pskem climate, Terra/Aqua snow and Charvak water extent.

Yearly cache files allow restart after service interruptions. Remote assets are
read only. Catchment results retain the provisional gauge-boundary designation.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
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
    value = computation()
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
        asset = f"MODIS/061/{'MOD' if sensor == 'terra' else 'MYD'}10A1"
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
                ndsi = image.select("NDSI_Snow_Cover")
                flags = image.select("NDSI_Snow_Cover_Algorithm_Flags_QA")
                valid = ndsi.gte(0).And(ndsi.lte(100)).And(image.select("NDSI_Snow_Cover_Basic_QA").lte(1)).And(flags.bitwiseAnd(129).eq(0))
                return ndsi.updateMask(valid).rename("ndsi")

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
                        "source_asset":asset,"source_image":props['source_image']})
            # Point observations exist for 2020 onward; retain every date including masked retrievals.
            if year >= 2020:
                def station_day(image):
                    ndsi = classify(image)
                    return ndsi.reduceRegions(points, ee.Reducer.first(), crs=projection).map(lambda f: f.setGeometry(None).set({
                        "date":image.date().format("YYYY-MM-dd"),"source_image":image.get("system:index")}))
                records = cached(f"snow-stations-{sensor}-{digest}-{year}-v2", lambda: ee.FeatureCollection(annual.toList(annual.size()).map(lambda image: station_day(ee.Image(image)))).flatten().getInfo())
                station_rows.extend({**f['properties'],"ndsi":f['properties'].get('first'),"sensor":sensor,"source_asset":asset} for f in records['features'])
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


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task',choices=['climate','snow','reservoir'],required=True)
    parser.add_argument('--start',type=int,default=2000)
    parser.add_argument('--end',type=int,default=2024)
    parser.add_argument('--sensors',nargs='+',choices=['terra','aqua'],default=['terra','aqua'])
    args=parser.parse_args()
    import ee
    ee.Initialize(project='ee-sabitovty');ee.data.setDeadline(300000)
    if args.task=='climate':extract_climate(ee,args.start,args.end)
    elif args.task=='snow':extract_snow(ee,args.start,args.end,args.sensors)
    else:extract_reservoir(ee,args.start,args.end)
    write_json(OUT/f'remote-{args.task}{"-"+"-".join(args.sensors) if args.task=="snow" else ""}.manifest.json',{
        'status':'complete','start_year':args.start,'end_year':min(args.end,2021) if args.task=='reservoir' else args.end,
        'retrieved_at':datetime.now(timezone.utc).isoformat(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'spatial_scope':'Provisional Pskem gauge catchment; Charvak reference polygon plus 1000m buffer for reservoir task',
        'snow_method':'NDSI snow >0; >=40 sensitivity; best/good QA; exclude inland-water and high-solar-zenith flags; no cloud filling. Daily valid area denominator retained.',
        'reservoir_method':'JRC Landsat-derived water class 2; no-data class 0 excluded; area only, not storage.'})


if __name__=='__main__':main()
