"""Deeper observed/product verification and pre-April seasonal-flow experiments.

No parameters are selected against the held-out flow years. Snow agreement is
cross-product verification; station snow-day bounds are a separate observation check.
"""
from __future__ import annotations

import calendar
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

import numpy as np

from build_chirchik_case_studies import ROOT, DATA, OUT, NAMES, read_csv, write_csv, write_json, period, scores, calendar_audit, discharge_months


def evaluate(rows, observed='observed', predicted='predicted'):
    return scores([r[observed] for r in rows], [r[predicted] for r in rows])


def intervals(rows, observed='observed', predicted='predicted', repeats=500):
    grouped=defaultdict(list)
    for r in rows:grouped[int(r.get('year') or r['period'][:4])].append(r)
    years=sorted(grouped)
    if len(years)<3:return None
    rng=np.random.default_rng(1729);values=defaultdict(list)
    for _ in range(repeats):
        sample=[r for year in rng.choice(years,len(years)) for r in grouped[int(year)]]
        for key,value in evaluate(sample,observed,predicted).items():
            if key in ['bias','rmse','mae','nse','kge'] and value is not None:values[key].append(value)
    return {'years':len(years),'repeats':repeats,'seed':1729,'method':'95% calendar-year percentile bootstrap; fitted parameters fixed',
            'bounds':{k:np.quantile(v,[.025,.975]).tolist() for k,v in values.items()}}


def climate_validation(observations, products):
    obs={(r['station_id'],period(r),r['variable']):float(r['value']) for r in observations}
    groups=defaultdict(list)
    for r in products:
        key=(r['station_id'],r['period'],r['variable'])
        if key in obs and r['value']!='':groups[(r['station_id'],r['product'],r['variable'])].append({
            **r,'observed':obs[key],'predicted':float(r['value']),'year':int(r['period'][:4]),'month':int(r['period'][-2:])})
    common=defaultdict(list)
    for (station,product,variable),rows in groups.items():common[(station,variable)].append({r['period'] for r in rows})
    common={k:set.intersection(*v) for k,v in common.items()}
    results=[];pairs=[]
    for (station,product,variable),rows in sorted(groups.items()):
        rows.sort(key=lambda r:r['period'])
        cutoff=2017 if station.endswith('419704') else 2016 if station.endswith('413694') else None
        training=[r for r in rows if cutoff is not None and r['year']<=cutoff]
        testing=[r for r in rows if cutoff is not None and r['year']>cutoff]
        shared=[r for r in rows if r['period'] in common[(station,variable)]]
        result={'station_id':station,'station':NAMES[station],'product':product,'variable':variable,'unit':rows[0]['unit'],
                'start':rows[0]['period'],'end':rows[-1]['period'],'raw':evaluate(rows),'raw_intervals':intervals(rows),
                'common_window':{'start':min(r['period'] for r in shared),'end':max(r['period'] for r in shared),'scores':evaluate(shared)},
                'training_end':cutoff,'correction':None,'anomaly_scores':None,
                'definition_note':'Monthly average of daily (Tmin+Tmax)/2; proxy differs from observed mean-temperature conventions.' if product=='chirts-midrange' else None}
        if training and testing:
            by_month={m:[r for r in training if r['month']==m] for m in range(1,13)}
            if all(len(v)>=4 for v in by_month.values()):
                adjustments={};climatology={}
                for m,records in by_month.items():
                    o=mean(r['observed'] for r in records);p=mean(r['predicted'] for r in records)
                    climatology[m]=(o,p)
                    adjustments[m]=o/p if variable=='precipitation_total' and p>0 else o-p if variable=='air_temperature_mean' else None
                eligible=[r for r in testing if adjustments[r['month']] is not None]
                for r in eligible:
                    adjustment=adjustments[r['month']]
                    r['corrected']=max(0,r['predicted']*adjustment) if variable=='precipitation_total' else r['predicted']+adjustment
                    r['observed_anomaly']=r['observed']-climatology[r['month']][0]
                    r['predicted_anomaly']=r['predicted']-climatology[r['month']][1]
                result['correction']={'method':'training-only calendar-month multiplicative ratio' if variable=='precipitation_total' else 'training-only calendar-month additive offset',
                    'training_months':len(training),'test_start':min(r['period'] for r in eligible),'test_end':max(r['period'] for r in eligible),
                    'adjustments':adjustments,'raw_test':evaluate(eligible),'corrected_test':evaluate(eligible,predicted='corrected'),
                    'corrected_intervals':intervals(eligible,predicted='corrected')}
                result['anomaly_scores']=evaluate(eligible,'observed_anomaly','predicted_anomaly')
                pairs.extend(eligible)
        if variable=='air_temperature_mean':
            for metric in [result['raw'],result['common_window']['scores'],result['anomaly_scores'],
                           *([result['correction']['raw_test'],result['correction']['corrected_test']] if result['correction'] else [])]:
                if metric:
                    for key in ['kge','beta','pbias']:metric[key]=None
            for bounds in [result['raw_intervals'],result['correction']['corrected_intervals'] if result['correction'] else None]:
                if bounds:bounds['bounds'].pop('kge',None)
        results.append(result)
    return results,pairs


def monthly_snow(rows, minimum_area=70, minimum_days=10):
    groups=defaultdict(list)
    for r in rows:groups[(r['sensor'],r['date'][:7],r['elevation_band'])].append(r)
    output=[]
    for (sensor,p,band),items in sorted(groups.items()):
        eligible=[r for r in items if float(r['valid_area_percent'])>=minimum_area and r['snow_cover_percent']!='']
        output.append({'sensor':sensor,'period':p,'elevation_band':band,'retrieved_days':len(items),'eligible_days':len(eligible),
            'expected_days':calendar.monthrange(int(p[:4]),int(p[-2:]))[1],
            'mean_valid_area_percent':mean(float(r['valid_area_percent']) for r in items),
            'snow_cover_percent':mean(float(r['snow_cover_percent']) for r in eligible) if len(eligible)>=minimum_days else None,
            'snow40_cover_percent':mean(float(r['snow40_cover_percent']) for r in eligible) if len(eligible)>=minimum_days else None})
    return output


def snow_station_bounds(observations,daily):
    ground={(r['station_id'],period(r)):float(r['value']) for r in observations if r['variable']=='snow_cover_days'}
    grouped=defaultdict(list)
    for row in daily:grouped[(row['station_id'],row['sensor'],row['date'][:7])].append(row)
    results=[]
    for (station,sensor,p),rows in sorted(grouped.items()):
        if (station,p) not in ground:continue
        valid=[float(r['ndsi']) for r in rows if r['ndsi']!='']
        expected=calendar.monthrange(int(p[:4]),int(p[-2:]))[1]
        snowy=sum(v>0 for v in valid);missing=expected-len(valid);observed=ground[(station,p)]
        if not 0<=observed<=expected:raise ValueError('Station snow days exceed calendar month')
        if missing<0:raise ValueError('Duplicate satellite station dates')
        results.append({'station_id':station,'station':NAMES[station],'sensor':sensor,'period':p,'observed_snow_days':observed,
            'valid_days':len(valid),'expected_days':expected,'coverage_percent':100*len(valid)/expected,
            'detected_snow_days':snowy,'unknown_days':missing,'lower_bound':snowy,'upper_bound':snowy+missing,
            'compatible_with_bounds':snowy<=observed<=snowy+missing})
    summaries=[]
    for station,sensor in sorted({(r['station'],r['sensor']) for r in results}):
        rows=[r for r in results if r['station']==station and r['sensor']==sensor]
        useful=[r for r in rows if r['coverage_percent']>=70]
        summaries.append({'station':station,'sensor':sensor,'months':len(rows),'months_70pct_observed':len(useful),
            'mean_coverage_percent':mean(r['coverage_percent'] for r in rows),'mean_unknown_days':mean(r['unknown_days'] for r in rows),
            'compatible_percent':100*mean(r['compatible_with_bounds'] for r in useful) if useful else None})
    return summaries,results


def ridge_forecast(train,test,features,alpha=1.0):
    """Fixed regularisation; scaling and response centring use training rows only."""
    y=np.array([r['volume_mcm'] for r in train]);ymean=float(y.mean())
    if not features:return [ymean]*len(test),{'intercept':ymean,'features':[]}
    x=np.array([[r[k] for k in features] for r in train],dtype=float)
    center=x.mean(axis=0);scale=x.std(axis=0);scale[scale==0]=1
    z=(x-center)/scale
    beta=np.linalg.solve(z.T@z+alpha*np.eye(len(features)),z.T@(y-ymean))
    predict=(np.array([[r[k] for k in features] for r in test])-center)/scale@beta+ymean
    return np.maximum(0,predict).tolist(),{'intercept':ymean,'features':features,'centers':center.tolist(),
            'scales':scale.tolist(),'coefficients_standardised':beta.tolist(),'ridge_alpha':alpha,'negative_predictions_clipped_at_zero':True}


def seasonal_flow(climate,snow,discharge,sensor='combined',require_snow=True):
    forcing={r['period']:r for r in climate}
    march={r['period']:r for r in snow if r['sensor']==sensor and r['elevation_band']=='all'}
    years=[];excluded=[]
    for year in range(2001,2018):
        flow=[r for r in discharge if r['year']==year and 4<=r['month']<=9]
        periods=[f'{year-1}-{m:02}' for m in [10,11,12]]+[f'{year}-{m:02}' for m in [1,2,3]]
        if len(flow)!=6 or any(r['observed_volume_mcm'] is None for r in flow):
            excluded.append({'year':year,'reason':'incomplete screened April–September observed volume'});continue
        if any(p not in forcing for p in periods):excluded.append({'year':year,'reason':'antecedent forcing absent'});continue
        s=march.get(f'{year}-03')
        if require_snow and (not s or s['snow_cover_percent'] is None):excluded.append({'year':year,'reason':f'March {sensor} snow coverage fails minimum'});continue
        years.append({'year':year,'volume_mcm':sum(r['observed_volume_mcm'] for r in flow),
            'winter_precip_mm':sum(float(forcing[p]['precipitation_mm']) for p in periods),
            'march_temperature_c':float(forcing[f'{year}-03']['temperature_c']),
            'march_swe_mm':float(forcing[f'{year}-03']['swe_mm']),
            'march_snow_percent':s['snow_cover_percent'] if s else None,'march_snow40_percent':s['snow40_cover_percent'] if s else None,
            'march_snow_days':s['eligible_days'] if s else 0})
    train=[r for r in years if r['year']<=2010];test=[r for r in years if r['year']>=2011]
    models=[];predictions=[]
    if len(train)>=6 and len(test)>=3:
        specifications={'seasonal_climatology':[],'climate':['winter_precip_mm','march_temperature_c'],
            'climate_plus_snow':['winter_precip_mm','march_temperature_c','march_snow_percent'],
            'climate_plus_snow40':['winter_precip_mm','march_temperature_c','march_snow40_percent'],
            'climate_plus_swe':['winter_precip_mm','march_temperature_c','march_swe_mm']}
        if not require_snow:
            specifications={k:v for k,v in specifications.items() if k not in ['climate_plus_snow','climate_plus_snow40']}
        for name,features in specifications.items():
            values,parameters=ridge_forecast(train,test,features)
            paired=[{'year':r['year'],'observed':r['volume_mcm'],'predicted':v,'model':name} for r,v in zip(test,values)]
            models.append({'model':name,'scores':evaluate(paired),'intervals':intervals(paired),'parameters':parameters})
            predictions.extend(paired)
        baseline=models[0]['scores']['rmse'];clim=models[1]['scores']['rmse']
        for m in models:
            m['rmse_skill_vs_climatology']=1-m['scores']['rmse']/baseline if baseline else None
            m['rmse_skill_vs_climate']=1-m['scores']['rmse']/clim if clim else None
    return {'status':'computed' if models else 'insufficient_eligible_years','snow_sensor':sensor if require_snow else None,'training_years':[r['year'] for r in train],
        'test_years':[r['year'] for r in test],'excluded_years':excluded,'annual_predictors':years,'models':models,'predictions':predictions,
        'protocol':f'Retrospective April 1 issue date. October–March precipitation and March temperature/SWE'+(f' and March {sensor} snow only.' if require_snow else ' only; no satellite snow coverage requirement.')+' Fixed ridge alpha=1; same complete years for every model; no held-out tuning.',
        'limits':'Provisional catchment; short record; reanalysis and retrospective snow product availability do not establish real-time forecast skill. No independent melt-source attribution.'}


def cross_sensor_snow(terra,aqua):
    t={(r['date'],r['elevation_band']):r for r in terra};pairs=defaultdict(list)
    for a in aqua:
        key=(a['date'],a['elevation_band']);b=t.get(key)
        if b and min(float(a['valid_area_percent']),float(b['valid_area_percent']))>=70:
            pairs[a['elevation_band']].append({'period':a['date'][:7],'date':a['date'],'observed':float(b['snow_cover_percent']),
                'predicted':float(a['snow_cover_percent'])})
    return [{'elevation_band':band,'scores':evaluate(rows),'interpretation':'Aqua minus Terra, percentage points; different overpass times and clear-pixel footprints. Agreement, not accuracy against ground truth.'} for band,rows in sorted(pairs.items())]


def reservoir_summary(rows):
    result=[]
    for r in rows:
        result.append({**r,'water_area_km2':float(r['water_area_km2']) if r['water_area_km2'] else None,
            'valid_area_percent':float(r['valid_area_percent']),'eligible':float(r['valid_area_percent'])>=95})
    good=[r for r in result if r['eligible'] and r['water_area_km2'] is not None]
    seasonal=[]
    for m in range(1,13):
        values=[r['water_area_km2'] for r in good if int(r['period'][-2:])==m]
        seasonal.append({'month':m,'mean_area_km2':mean(values) if values else None,'n':len(values)})
    return {'monthly':result,'total_months':len(rows),'eligible_months':len(good),'minimum_valid_area_percent':95,
        'min_observed':min(good,key=lambda r:r['water_area_km2']) if good else None,
        'max_observed':max(good,key=lambda r:r['water_area_km2']) if good else None,'seasonal':seasonal,
        'limits':'Landsat-derived JRC water detections within HydroLAKES 14452 plus 1 km buffer; may include adjoining channels. Not independently validated shoreline area, bathymetry or storage. Cloud/no-data months remain gaps.'}


def main():
    names=['station-product-monthly.csv','pskem-basin-climate-monthly.csv','pskem-modis-terra-daily.csv',
           'pskem-modis-aqua-daily.csv','station-modis-terra-daily.csv','station-modis-aqua-daily.csv','charvak-jrc-monthly.csv',
           'pskem-modis-combined-daily.csv','station-modis-combined-daily.csv','charvak-sentinel2-check.csv']
    missing=[name for name in names if not (OUT/name).exists()]
    if missing:raise SystemExit('Required remote inputs missing: '+', '.join(missing))
    tables={name:read_csv(OUT/name) for name in names}
    observations=read_csv(DATA/'pskem-station-monthly.csv')
    raw=read_csv(DATA/'pskem-discharge-daily.csv');valid,rejected=calendar_audit(raw)
    manifest=json.loads((DATA/'pskem-observations.manifest.json').read_text(encoding='utf-8'))
    flagged={('uz:station/gauge-16290',r['year'],r['month'],r['day']) for r in manifest['suspectDailyValues']}
    discharge=discharge_months(valid,flagged)
    climate,corrected=climate_validation(observations,tables[names[0]])
    snow=monthly_snow(tables[names[2]]+tables[names[3]]+tables[names[7]])
    station_summary,station_rows=snow_station_bounds(observations,tables[names[4]]+tables[names[5]]+tables[names[8]])
    flow=seasonal_flow(tables[names[1]],snow,discharge)
    climate_flow=seasonal_flow(tables[names[1]],snow,discharge,require_snow=False)
    terra_flow=seasonal_flow(tables[names[1]],snow,discharge,sensor='terra')
    inputs=[OUT/name for name in names]+[DATA/'pskem-station-monthly.csv',DATA/'pskem-discharge-daily.csv',DATA/'pskem-observations.manifest.json',Path(__file__)]
    result={'version':'2.0.0','generated_at':datetime.now(timezone.utc).isoformat(),'climate_validation':climate,'corrected_pairs':corrected,
        'snow_monthly':snow,'snow_station_summary':station_summary,'snow_station_bounds':station_rows,
        'snow_sensor_agreement':cross_sensor_snow(tables[names[2]],tables[names[3]]),'seasonal_flow':flow,
        'climate_only_flow':climate_flow,'terra_only_flow':terra_flow,
        'reservoir':reservoir_summary(tables[names[6]]),'provenance':[{'path':p.relative_to(ROOT).as_posix(),
            'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in inputs],
        'snow_policy':{'minimum_daily_valid_area_percent':70,'minimum_valid_days_per_month':10,'snow_ndsi_threshold':'>0','sensitivity_threshold':'>=40',
                       'no_cloud_gap_fill':True,'interpretation':'Snow cover is classified area among valid pixels; NDSI values are not fractional snow cover.'}}
    jrc={r['period']:r for r in result['reservoir']['monthly']}
    reservoir_pairs=[]
    for r in tables[names[9]]:
        match=jrc.get(r['period'])
        if match and match['eligible'] and float(r['valid_area_percent'])>=95 and r['water_area_km2']!='':
            reservoir_pairs.append({'period':r['period'],'sentinel_date':r['date'],'observed':match['water_area_km2'],
                'predicted':float(r['water_area_km2']),'threshold01':float(r['water01_area_km2']),'source_image':r['source_image']})
    result['reservoir']['sentinel_check']={'pairs':reservoir_pairs,'scores':evaluate(reservoir_pairs),
        'method':'Same-month independent-sensor comparison: JRC monthly Landsat water against highest-coverage Sentinel-2 scene; ≥95% coverage in both. MNDWI>0 and NDVI<0.3; MNDWI>0.1 sensitivity.',
        'limits':'JRC is not ground truth and its monthly dates differ from the selected Sentinel-2 acquisition. Optical errors can be correlated. No manually labelled shorelines yet.'}
    for name in ['gauge-reach-audit.json','station-terrain-context.json']:
        path=OUT/name
        if path.exists():
            result[name.removesuffix('.json').replace('-','_')]=json.loads(path.read_text(encoding='utf-8'))
            result['provenance'].append({'path':path.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    write_json(OUT/'advanced-validation.json',result)
    write_csv(OUT/'snow-monthly.csv',snow,list(snow[0]))
    write_csv(OUT/'snow-station-bounds.csv',station_rows,list(station_rows[0]))
    write_csv(OUT/'seasonal-flow-predictions.csv',flow['predictions'],['year','model','observed','predicted'])
    write_csv(OUT/'climate-only-flow-predictions.csv',climate_flow['predictions'],['year','model','observed','predicted'])
    write_csv(OUT/'charvak-cross-sensor-pairs.csv',reservoir_pairs,['period','sentinel_date','observed','predicted','threshold01','source_image'])
    write_csv(OUT/'seasonal-flow-predictors.csv',flow['annual_predictors'],list(flow['annual_predictors'][0]) if flow['annual_predictors'] else ['year'])
    write_csv(OUT/'corrected-station-pairs.csv',corrected,['station_id','product','variable','period','unit','observed','predicted','corrected','observed_anomaly','predicted_anomaly'])
    report(result)
    print(json.dumps({'climate_comparisons':len(climate),'snow_station':station_summary,'flow_models':[{k:m[k] for k in ['model','scores','rmse_skill_vs_climatology']} for m in flow['models']],
                      'flow_training':flow['training_years'],'flow_testing':flow['test_years'],'reservoir_eligible':result['reservoir']['eligible_months']},indent=2))


def report(d):
    def f(v,n=2):return 'undefined' if v is None else f'{v:.{n}f}'
    lines=['# Pskem–Charvak: historical validation and seasonal water evidence','',
        'This study replaces the initial data-readiness assessment with Earth Engine extractions and reproducible tests against the held station records. '
        'It distinguishes station validation, agreement between satellite products, a retrospective seasonal-flow experiment, and reservoir extent monitoring. '
        'None of these by itself identifies glacier melt fractions or absolute reservoir storage.','',
        '## Study domain and data','',
        'The Pskem candidate contains 20 level-12 units, approximately 2,627 km². It includes the full unit containing the Mullala gauge and is provisional pending reach/partial-unit review. '
        'Pskem and Oygaing are the mountain station checks; Tashkent is the lowland comparison. Ground records cover precipitation and temperature (Pskem 2010–2024, Oygaing 2020–2022, Tashkent 2010–2019), '
        'Pskem discharge (2001–2017), and observed snow-day counts (Pskem 2020–2024; Oygaing 2020–2022).','',
        '| Product | Extracted support | Role |','| --- | --- | --- |',
        '| ERA5-Land monthly | Native station cells for observed months; area-weighted Pskem basin 2000–2024 | Temperature/precipitation validation; antecedent precipitation, March temperature and SWE |',
        '| CHIRPS v3 pentads | Six pentads per observed station month | Precipitation comparison |',
        '| CHIRTS daily | Daily Tmin/Tmax midrange aggregated monthly, 2010–2016 overlap | Temperature proxy cross-check |',
        '| MODIS Terra/Aqua v6.1 | Daily Terra/Aqua basin snow 2000–2024; combined series extended to latest extraction; station cells 2020–2024 | Snow-day checks, sensor agreement and pre-April predictors |',
        '| SRTM | Elevation bands below 1500, 1500–2500, 2500–3500 and above 3500 m | Snow stratification |',
        '| JRC Global Surface Water v1.4 | Monthly water detections, 2000–2021, Charvak polygon plus 1 km | Reservoir extent evidence, with missing-data screening |','',
        'ERA5 accumulated precipitation is converted from m to mm; 2 m temperature from K to °C. CHIRPS pentads are summed, not averaged. '
        'CHIRTS is monthly mean daily (Tmin+Tmax)/2 and is explicitly a proxy: the station mean may use another observing convention. '
        'Native station sampling uses the source projection and affine transform. [ERA5-Land documentation](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_MONTHLY_AGGR), '
        '[CHIRPS v3](https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHC_CHIRPS_V3_PENTAD), '
        '[CHIRTS](https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRTS_DAILY).','',
        'Station assimilation/contribution to these gridded products has not been audited. These are observation comparisons, not proof of fully independent product validation. '
        'Station elevations and relocations are not established by the supplied ontology, so no fixed lapse rate is assumed.','',
        '## 1. Raw forcing validation','',
        'Bias is product minus observation. Temperature errors are °C; precipitation errors are mm/month. Each row uses its own explicitly stated overlap.','',
        '| Station | Product | Variable | Period | N | RMSE | Bias | r |','| --- | --- | --- | --- | ---: | ---: | ---: | ---: |']
    for r in d['climate_validation']:
        m=r['raw'];lines.append(f"| {r['station']} | {r['product']} | {r['variable']} | {r['start']}–{r['end']} | {m['n']} | {f(m['rmse'])} | {f(m['bias'])} | {f(m['r'],3)} |")
    lines+=['','### Fair comparison on identical months','',
        'The following scores restrict each station/variable to the intersection of months available from every compared product. '
        'This prevents a short CHIRTS window from being ranked directly against a longer ERA5 period. CHIRTS remains a midrange proxy.','',
        '| Station | Variable | Product | Common window | N | RMSE |','| --- | --- | --- | --- | ---: | ---: |']
    for r in d['climate_validation']:
        c=r['common_window'];lines.append(f"| {r['station']} | {r['variable']} | {r['product']} | {c['start']}–{c['end']} | {c['scores']['n']} | {f(c['scores']['rmse'])} |")
    lines+=['','## 2. Corrections tested on later years','',
        'For Pskem, fit through 2017 and test 2018–2024. For Tashkent, fit through 2016 and test 2017–2019. '
        'Each calendar month needs at least four training observations. Temperature uses an additive monthly offset; precipitation uses the ratio of observed to product training means. '
        'No coefficient or correction form is selected against the test scores. Oygaing is too short for this split and receives raw checks only; CHIRTS has no later test overlap.','',
        '| Station | Product | Variable | Test period | N | Raw RMSE | Corrected RMSE | Corrected bias | Test anomaly r |',
        '| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for r in d['climate_validation']:
        c=r['correction']
        if c:lines.append(f"| {r['station']} | {r['product']} | {r['variable']} | {c['test_start']}–{c['test_end']} | {c['raw_test']['n']} | {f(c['raw_test']['rmse'])} | {f(c['corrected_test']['rmse'])} | {f(c['corrected_test']['bias'])} | {f(r['anomaly_scores']['r'],3)} |")
    lines+=['','Anomalies subtract each calendar month’s training mean separately from observed and product values. This removes the recurring seasonal cycle without using test observations to establish a baseline. '
        'Calendar-year bootstrap intervals are in advanced-validation.json; they condition on fitted corrections and do not capture instrument or structural uncertainty. '
        'Temperature percent bias and temperature KGE are not reported because Celsius ratios depend on an arbitrary zero.','',
        'A strong raw correlation can coexist with a large mean error. Use held-out RMSE, seasonal biases and anomaly correlation together when choosing forcing. '
        'Station-cell corrections do not automatically transfer to area-mean mountain forcing. Product ranking can differ by station and season.','',
        '## 3. MODIS snow: quality first','',
        'Terra and Aqua are analysed separately and as a same-day combination: valid Terra pixels take priority, with valid Aqua observations filling Terra gaps. No adjacent dates are used. Valid pixels have NDSI in 0–100, best/good basic QA, and neither inland-water nor high-solar-zenith flag. '
        'The main snow mask is positive provider-screened NDSI; NDSI ≥40 is a conservative sensitivity test. '
        'Snow area is summed and divided by valid observed area. NDSI is never interpreted as fractional cover. '
        'Daily valid area must be at least 70%; monthly means require at least ten qualifying days. No cloud filling is used. '
        '[MODIS Terra band and QA definitions](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD10A1), '
        '[MODIS Aqua](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MYD10A1).','',
        '### Cross-sensor verification','',
        'These are matched-date comparisons with ≥70% coverage in both products. Terra is the reference for the sign of differences, not ground truth. '
        'Their clear pixels and overpass times can differ, so these are aggregate agreement scores, not pixel-level classification accuracy.','',
        '| Elevation band | Paired days | RMSE (percentage points) | Aqua − Terra bias | r |','| --- | ---: | ---: | ---: | ---: |']
    for r in d['snow_sensor_agreement']:
        m=r['scores'];lines.append(f"| {r['elevation_band']} | {m['n']} | {f(m['rmse'])} | {f(m['bias'])} | {f(m['r'],3)} |")
    lines+=['','### Independent station snow-day consistency','',
        'The ground record provides monthly snow-day counts, not daily snow/no-snow labels. For each station-month, the satellite lower bound is the number of valid snowy days; '
        'the upper bound adds all unobserved days. The station count is checked against those bounds. A wide cloudy-month interval is weak evidence, so compatibility is reported only for months with ≥70% daily observations. '
        'Even then, a 500 m mixed pixel can differ from the station snow patch. No daily confusion matrix, snow-depth validation or SWE validation is inferred.','',
        '| Station | Sensor | Paired months | Months ≥70% observed | Mean daily coverage (%) | Mean unknown days | Compatible (%) in ≥70% months |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for r in d['snow_station_summary']:lines.append(f"| {r['station']} | {r['sensor']} | {r['months']} | {r['months_70pct_observed']} | {f(r['mean_coverage_percent'])} | {f(r['mean_unknown_days'])} | {f(r['compatible_percent'])} |")
    flow=d['seasonal_flow']
    terra=d['terra_only_flow'];climate_only=d['climate_only_flow']
    lines+=['','## 4. Does pre-April snow information improve summer-flow estimates?','',flow['protocol'],'',
        'The target is observed April–September discharge volume in million m³. Every day must be present after screening; 2017 is excluded because flagged daily observations leave incomplete seasonal volume. '
        'Three source flags and the impossible 2015-02-29 date are retained in the separate audit. '
        'All candidate models use identical eligible training and test years. Predictors and response are centred/scaled from training data only; negative predicted volumes are clipped at zero.','',
        f"Training years: {', '.join(map(str,flow['training_years']))}. Test years: {', '.join(map(str,flow['test_years']))}.",'',
        '| Model | Test years | RMSE (million m³) | Bias (million m³) | NSE | RMSE skill vs climatology | RMSE skill vs climate |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for m in flow['models']:
        s=m['scores'];lines.append(f"| {m['model']} | {s['n']} | {f(s['rmse'])} | {f(s['bias'])} | {f(s['nse'],3)} | {f(m['rmse_skill_vs_climatology'],3)} | {f(m['rmse_skill_vs_climate'],3)} |")
    lines+=['',f"Terra-only coverage check: {len(terra['training_years'])} eligible training years and {len(terra['test_years'])} test years; status `{terra['status']}`. "
        'The analysis requires at least six training and three test years before fitting these specifications. This threshold is a minimum feasibility gate, not a guarantee of strong statistical evidence.','',
        '### Climate-only cohort, without a satellite-coverage gate','',climate_only['protocol'],'',
        f"Training years: {', '.join(map(str,climate_only['training_years']))}. Test years: {', '.join(map(str,climate_only['test_years']))}. "
        'This larger cohort is a separate experiment; its scores cannot be used to claim snow improvement on a different set of years.','',
        '| Model | Test years | RMSE (million m³) | Bias (million m³) | NSE | RMSE skill vs climatology |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for m in climate_only['models']:
        s=m['scores'];lines.append(f"| {m['model']} | {s['n']} | {f(s['rmse'])} | {f(s['bias'])} | {f(s['nse'],3)} | {f(m['rmse_skill_vs_climatology'],3)} |")
    lines+=['','Positive RMSE skill means lower error than the named baseline; negative skill means worse error. All tested specifications are retained, including failures. '
        'The snow40 model tests snow-threshold sensitivity; the SWE model uses reanalysis snow mass rather than observed snow extent. '
        'These tests measure retrospective association and predictive utility, not causal snowmelt attribution. '
        'Retrospective product latency and the provisional boundary prevent operational forecast claims. Small test samples produce broad uncertainty. '
        '[NSE/KGE benchmark interpretation](https://hess.copernicus.org/articles/23/4323/2019/).','',
        'Excluded years: '+('; '.join(f"{r['year']}: {r['reason']}" for r in flow['excluded_years']) or 'none')+'.','']
    reservoir=d['reservoir']
    lines+=['## 5. Charvak extent, not assumed storage','',
        f"JRC provides {reservoir['total_months']} monthly records; {reservoir['eligible_months']} pass the ≥95% valid-area rule within the fixed analysis domain. "
        'Detected water area is not scaled up to fill unobserved pixels. The series stops in 2021 because that is the end of this JRC version. '
        '[JRC monthly water-history classes, coverage and attribution](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_MonthlyHistory).','']
    if reservoir['min_observed']:
        low,high=reservoir['min_observed'],reservoir['max_observed']
        lines += [f"Among eligible months, detected water area ranges from {low['water_area_km2']:.2f} km² ({low['period']}) to {high['water_area_km2']:.2f} km² ({high['period']}). "
                  'These are extrema of the screened available observations, not guaranteed extrema of actual reservoir operation.','']
    lines += [reservoir['limits'],'',
        'JRC is generated from Landsat, so a Landsat-derived comparison would not be fully independent. '
        'Pskem discharge covers only one tributary; without other inflows, releases, diversions and independent levels/bathymetry, no absolute storage or operational rule is validated.','',
        '### Sentinel-2 verification','',reservoir['sentinel_check']['method'],'',
        f"There are {reservoir['sentinel_check']['scores']['n']} qualified month pairs. Sentinel-2 minus JRC bias is {f(reservoir['sentinel_check']['scores']['bias'])} km²; "
        f"RMSE is {f(reservoir['sentinel_check']['scores']['rmse'])} km². The CSV retains the Sentinel-2 acquisition date and both water thresholds.",'',
        'Sentinel-2 SCL removes no-data, defective, shadow, cloud/cirrus and snow/ice classes. Within each month the highest valid-area scene is selected, with earliest date breaking ties; selection does not optimise agreement. '
        'The 20 m SWIR grid defines the reduction. [Sentinel-2 harmonised surface reflectance and SCL](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED). '
        +reservoir['sentinel_check']['limits'],'',
        '## Spatial verification and representativeness','']
    if 'gauge_reach_audit' in d:
        candidates=d['gauge_reach_audit']['candidates'][:3]
        lines += ['The stored gauge coordinate is effectively on a small tributary. Two larger Pskem reaches lie roughly 700 m away. '
            'An automatic nearest-reach snap would select the wrong hydrological scale; no coordinate was changed. The full-unit basin trace is retained only as a provisional experimental domain.','',
            '| Candidate reach | Distance (m) | Upstream area (km²) | Reference discharge (m³/s) |','| --- | ---: | ---: | ---: |']
        for r in candidates:lines.append(f"| {r['HYRIV_ID']} | {r['distance_m']:.1f} | {r['UPLAND_SKM']:.1f} | {r['DIS_AV_CMS']:.2f} |")
    if 'station_terrain_context' in d:
        lines += ['','SRTM gives terrain context, not surveyed station elevation or the actual ERA5 model orography. These differences should not be used as a verified lapse-rate correction.','',
            '| Station | SRTM at coordinate (m) | Mean SRTM within ERA5 cell (m) | Difference (m) |','| --- | ---: | ---: | ---: |']
        for r in d['station_terrain_context']['rows']:lines.append(f"| {NAMES[r['station_id']]} | {r['station_dem_m']:.0f} | {r['era5_cell_dem_mean_m']:.0f} | {r['era5_cell_dem_mean_m']-r['station_dem_m']:.0f} |")
        lines += ['','At Pskem, the terrain difference is much smaller than would by itself explain a 7°C offset under a conventional lapse-rate assumption. '
            'Station representativeness, observing definitions and model orography therefore remain open questions; the successful empirical correction is not a causal explanation. '
            '[SRTM data specification](https://developers.google.com/earth-engine/datasets/catalog/USGS_SRTMGL1_003).']
    lines += ['',
        '## Conclusions and next discriminating tests','',
        '1. Select climate forcing by station, variable and held-out error; raw seasonal correlation alone is insufficient. Audit station elevations, relocations and product station contributions before treating the comparisons as independent.',
        '2. Use MODIS valid-area and missing-day budgets in every snow interpretation. Cross-sensor agreement and station snow-day bounds answer different questions and should not be merged into one accuracy score.',
        '3. Retain the seasonal-flow baseline and every tested model. Added snow predictors must reduce held-out error; a plausible process story is insufficient. Extend discharge observations beyond 2017 before operational use.',
        '4. Review the gauge-to-reach match and outlet-unit delineation, then repeat basin reductions to measure boundary sensitivity. A whole level-12 unit is a candidate spatial approximation.',
        '5. Publish Charvak water extent with observation completeness. Upgrade to storage only when independent height and elevation–volume constraints support it.',
        '6. Glacier-source attribution and land-use classifier accuracy remain separate studies. Neither is validated by a successful station comparison or runoff fit.','',
        '## Reproduction','',
        '```bash','npm run cases:forcing','python PIPELINES/extract_chirchik_remote.py --task climate',
        'python PIPELINES/extract_chirchik_remote.py --task snow','python PIPELINES/extract_chirchik_remote.py --task reservoir',
        'python PIPELINES/extract_chirchik_remote.py --task reservoir-check','python PIPELINES/audit_chirchik_spatial.py --terrain',
        'npm run cases:analyse','npm run cases:build','npm run cases:figures','npm run cases:figures:validation','```','',
        'Input hashes, fitted coefficients, paired records, model predictions and uncertainty intervals are in advanced-validation.json and the adjacent CSVs. '
        'Earth Engine source image identifiers accompany the remote tables; cache files allow reproducible retrieval recovery without discarding completed years.']
    (OUT/'chirchik-deep-study.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':main()
