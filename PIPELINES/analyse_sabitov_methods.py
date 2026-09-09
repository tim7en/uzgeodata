"""Auditable daily adaptations of Sabitov (2018), with held-out evaluation.

All stores/fluxes are mm water equivalent over a zone. Model output is converted
to m3/s only after area weighting. These experiments are not thesis replications.
"""
import calendar
import hashlib
import json
import math
from collections import defaultdict
from datetime import date, timedelta, datetime, timezone

import numpy as np
from scipy.optimize import minimize
from scipy.stats import qmc, kendalltau, theilslopes

from build_chirchik_case_studies import ROOT, DATA, OUT, read_csv, write_csv, write_json, scores, calendar_audit

MODELS = [('m1', 'M1 adapted · lumped snow and stores', False, False, False),
          ('m2', 'M2 adapted · elevation and glacier', True, True, False),
          ('m3', 'M3 adapted · lumped curve number', False, True, True),
          ('m4', 'M4 adapted · elevation and curve number', True, True, True)]
PARAMETERS = ['precipitation_multiplier', 'soil_capacity_mm', 'groundwater_retention_daily', 'crop_coefficient', 'cn_offset']
BOUNDS = [(.5,1.5), (10,300), (.94,.999), (.3,1.2), (-15,15)]


def hamon_mm(temperature, day_of_year, latitude=41.9, printed=False):
    """Hamon with explicit kPa -> hPa conversion for vapour density (g/m3).

    printed=True evaluates the thesis Eq.1 literally, including cm/day -> mm/day.
    It is retained as a sensitivity, not silently treated as equivalent.
    """
    if temperature <= 0:
        return 0.
    declination = .409 * math.sin(2*math.pi*day_of_year/365 - 1.39)
    sunset = math.acos(max(-1., min(1., -math.tan(math.radians(latitude))*math.tan(declination))))
    daylight = 24/math.pi * sunset
    es_kpa = .6108 * math.exp(17.27*temperature/(237.3+temperature))
    if printed:
        return 10*.021*daylight**2*es_kpa/(temperature+273.)
    density = 2167*es_kpa/(temperature+273.15)
    return .1651*(daylight/12)*density


def adjusted_cn(cn, antecedent_mm, growing):
    low, high = (36.,53.) if growing else (13.,28.)
    value = cn/(2.334-.01334*cn) if antecedent_mm < low else cn/(.4036+.0059*cn) if antecedent_mm > high else cn
    return max(1., min(99.9, value))


def scs_runoff(liquid_mm, cn):
    """Correct SI form: S=25400/CN-254 mm, and Q=0 below initial loss."""
    if not 0 < cn <= 100:
        raise ValueError('Curve number must be in (0,100]')
    retention = 25400/cn - 254
    return (liquid_mm-.2*retention)**2/(liquid_mm+.8*retention) if liquid_mm > .2*retention else 0.


def prepare(forcing, zones, distributed, pet_method='hamon'):
    total = sum(z['area_km2'] for z in zones)
    zmean = sum(z['area_km2']*z['mean_elevation_m'] for z in zones)/total
    if not distributed:
        zones = [{'zone':0, 'area_km2':total, 'mean_elevation_m':zmean,
                  'glacier_fraction':sum(z['glacier_area_km2'] for z in zones)/total}]
    dates = [date.fromisoformat(r['date']) for r in forcing]
    if any(b-a != timedelta(days=1) for a,b in zip(dates,dates[1:])):
        raise ValueError('Daily forcing must be contiguous; gaps cannot become zero weather')
    result = []
    for z in zones:
        rows = []
        for d,r in zip(dates, forcing):
            # Negative lapse: thesis magnitudes summer 6.5, autumn/winter 6, spring 6.7 C/km.
            lapse = -6.7 if d.month in (3,4,5) else -6.5 if d.month in (6,7,8) else -6.
            t = float(r['temperature_c']) + lapse*(z['mean_elevation_m']-zmean)/1000
            ice_t = float(r['temperature_c']) + lapse*(3643-zmean)/1000
            pet = max(0.,float(r['potential_et_mm'])) if pet_method=='era5' else hamon_mm(t,d.timetuple().tm_yday,printed=pet_method=='thesis_printed')
            p = float(r['precipitation_mm'])
            if not all(math.isfinite(v) for v in [p,t,pet,ice_t]):
                raise ValueError('Nonfinite daily forcing')
            rows.append((max(0.,p),t,pet,ice_t,4<=d.month<=9))
        result.append({'weight':z['area_km2']/total,'glacier_fraction':z['glacier_fraction'],
                       'cn':90. if distributed and z['zone']==2 else 50.,'forcing':rows})
    return result


def simulate(prepared, parameters, ice=True, curve=True, glacier_scale=1., ice_depth_mm=30000.,
             snow_ddf=4.5, ice_ddf=6., ice_method='degree_day', event_cn=False):
    """Independent snow, soil, groundwater, and finite glacier-ice stores.

    Snowmelt uses remaining SWE. Ice is shielded by remaining seasonal snow;
    available positive degree days exclude the fraction used to melt that snow.
    Glacier melt drains directly (thesis assumption); it is not a measured source
    fraction. CN partitions rain+snowmelt; infiltration supplies ET and recharge.
    """
    p_factor,capacity,kb,kc,cn_offset = parameters
    n = len(prepared[0]['forcing'])
    # Q, snow, soil, groundwater, AET, snowmelt, ice melt, quickflow, baseflow,
    # water balance residual, remaining ice, snow-covered area proxy, corrected P.
    output = np.zeros((n,13))
    for zone in prepared:
        snow=soil=ground=0.
        fraction=min(1.,zone['glacier_fraction']*glacier_scale) if ice else 0.
        stock=fraction*ice_depth_mm
        antecedent=[0.]*5
        event_input=event_output=0.;event_number=50.
        for i,(rawp,t,pet,ice_t,growing) in enumerate(zone['forcing']):
            before=snow+soil+ground+stock
            p=rawp*p_factor
            snowfall=p if t<=0 else 0.;rain=p-snowfall
            snow+=snowfall
            melt=min(snow,snow_ddf*max(t,0.));snow-=melt
            available_fraction=max(0.,1-melt/(snow_ddf*t)) if t>0 else 0.
            if snow>1e-9 or t<=0:
                ice_melt=0.
            elif ice_method=='annual_cubic':
                # Eq.10-11 dimensional interpretation: mm/year -> mm/day.
                # Applying daily T to an annual empirical relation is a sensitivity only.
                ice_melt=min(stock,fraction*max(9.5+ice_t,0.)**3/365.25*available_fraction)
            else:
                ice_melt=min(stock,fraction*ice_ddf*max(ice_t,0.)*available_fraction)
            stock-=ice_melt
            liquid=rain+melt
            cn=adjusted_cn(max(1.,min(99.,zone['cn']+cn_offset)),sum(antecedent),growing)
            if curve and event_cn:
                if liquid<=.1:
                    event_input=event_output=0.
                    quick=0.
                else:
                    if event_input==0.:event_number=cn
                    event_input+=liquid
                    cumulative=scs_runoff(event_input,event_number)
                    quick=max(0.,min(liquid,cumulative-event_output));event_output=cumulative
            else:
                quick=scs_runoff(liquid,cn) if curve else 0.
            antecedent=antecedent[1:]+[rain]
            soil+=liquid-quick
            et=min(soil,kc*pet);soil-=et
            recharge=max(soil-capacity,0.);soil-=recharge
            base=(1-kb)*ground;ground+=recharge-base
            runoff=quick+base+ice_melt
            residual=p-et-runoff-(snow+soil+ground+stock-before)
            values=(runoff,snow,soil,ground,et,melt,ice_melt,quick,base,residual,stock,float(snow>1.),p)
            w=zone['weight']
            for j,v in enumerate(values):output[i,j]+=w*v
    return output


def observed_daily():
    manifest=json.loads((DATA/'pskem-observations.manifest.json').read_text(encoding='utf-8'))
    flags={(r['year'],r['month'],r['day']) for r in manifest['suspectDailyValues']}
    valid, invalid=calendar_audit(read_csv(DATA/'pskem-discharge-daily.csv'))
    values={}
    for r in valid:
        key=tuple(int(r[k]) for k in ('year','month','day'))
        if key in flags:continue
        value=float(r['discharge_cms'])
        if not math.isfinite(value) or value<0:raise ValueError('Invalid discharge')
        stamp=date(*key).isoformat()
        if stamp in values:raise ValueError('Duplicate gauge date')
        values[stamp]=value
    return values


def monthly_pairs(dates, observed, prediction):
    groups=defaultdict(list)
    for i,d in enumerate(dates):groups[d[:7]].append((observed.get(d),float(prediction[i])))
    result=[]
    for period,items in sorted(groups.items()):
        valid=[(o,p) for o,p in items if o is not None]
        days=calendar.monthrange(int(period[:4]),int(period[-2:]))[1]
        if len(valid)/days>=.9:
            result.append({'period':period,'observed':float(np.mean([o for o,p in valid])),
                'predicted':float(np.mean([p for o,p in valid])),'paired_days':len(valid)})
    return result


def flow_duration(values):
    a=np.asarray(values,dtype=float)
    if not len(a):return []
    return [{'exceedance_percent':p,'discharge_cms':float(np.quantile(a,1-p/100))} for p in range(1,100)]


def trend_diagnostics(observed):
    groups=defaultdict(list)
    for stamp,q in observed.items():groups[stamp[:7]].append(q)
    rows=[]
    for month in range(1,13):
        pairs=[(int(p[:4]),float(np.mean(v))) for p,v in sorted(groups.items())
               if int(p[-2:])==month and len(v)/calendar.monthrange(int(p[:4]),month)[1]>=.9]
        x,y=map(np.array,zip(*pairs))
        tau,p=kendalltau(x,y);slope,intercept,lo,hi=theilslopes(y,x)
        rows.append({'month':month,'years':len(x),'sen_slope_cms_year':float(slope),'slope_lower95':float(lo),'slope_upper95':float(hi),
                     'kendall_tau':float(tau),'p_uncorrected':float(p)})
    # Holm correction across the twelve predeclared month tests.
    order=sorted(range(12),key=lambda i:rows[i]['p_uncorrected']);running=0.
    for rank,i in enumerate(order):
        running=max(running,min(1.,(12-rank)*rows[i]['p_uncorrected']));rows[i]['p_holm']=running
    return rows


def classification_accuracy(rows):
    """Independent reference labels only; missing labels never count as agreement."""
    valid=[r for r in rows if r.get('reference_class') not in ('',None) and r.get('mapped_class') not in ('',None)]
    if not valid:return {'status':'pending_independent_labels','n':0,'overall_accuracy':None,'classes':[]}
    identifiers=[r.get('sample_id') for r in valid]
    if None in identifiers or '' in identifiers or len(set(identifiers))!=len(identifiers):
        raise ValueError('Reference samples require unique sample_id')
    classes=sorted({str(r[k]) for r in valid for k in ('reference_class','mapped_class')})
    matrix=[[sum(str(r['mapped_class'])==m and str(r['reference_class'])==ref for r in valid) for ref in classes] for m in classes]
    stats=[]
    for i,label in enumerate(classes):
        mapped=sum(matrix[i]);reference=sum(row[i] for row in matrix)
        stats.append({'class':label,'user_accuracy':matrix[i][i]/mapped if mapped else None,'producer_accuracy':matrix[i][i]/reference if reference else None})
    return {'status':'sample_accuracy_not_area_adjusted','n':len(valid),'overall_accuracy':sum(matrix[i][i] for i in range(len(classes)))/len(valid),
            'classes':stats,'labels':classes,'matrix_rows_mapped_columns_reference':matrix}


def gauge_comparison():
    from shapely.geometry import Point, shape
    from shapely.ops import transform
    from pyproj import Transformer
    projection=Transformer.from_crs(4326,32642,always_xy=True).transform
    old=(70.2,41.766667);thesis=(70+13/60,41+47/60)
    features=json.loads((ROOT/'PUBLISHED/data/hydrography/rivers-unified.geojson').read_text(encoding='utf-8'))['features']
    points=[]
    for label,coord in [('Existing station',old),('Thesis p.15',thesis)]:
        point=transform(projection,Point(coord));near=[]
        for f in features:
            geom=shape(f['geometry']);w,s,e,n=geom.bounds
            if w>coord[0]+.05 or e<coord[0]-.05 or s>coord[1]+.05 or n<coord[1]-.05:continue
            distance=point.distance(transform(projection,geom))
            if distance<=3000:near.append({'reach_id':f['properties']['HYRIV_ID'],'distance_m':distance,'upstream_area_km2':f['properties']['UPLAND_SKM']})
        points.append({'source':label,'longitude':coord[0],'latitude':coord[1],'nearest_reaches':sorted(near,key=lambda r:r['distance_m'])[:5]})
    return {'coordinates':points,'coordinate_separation_m':transform(projection,Point(old)).distance(transform(projection,Point(thesis))),
            'status':'unresolved_no_automatic_relocation','note':'The thesis is additional metadata evidence, not surveyed confirmation. Reach and drainage area must be corroborated before changing the catchment.'}


def main():
    forcing=read_csv(OUT/'sabitov-daily-forcing.csv')
    manifest=json.loads((OUT/'sabitov-inputs.manifest.json').read_text(encoding='utf-8'))
    zones=manifest['zones'];area=sum(z['area_km2'] for z in zones);factor=area*1000/86400
    observed=observed_daily();dates=[r['date'] for r in forcing]
    train=[i for i,d in enumerate(dates) if '2001-01-01'<=d<='2010-12-31' and d in observed]
    test=[i for i,d in enumerate(dates) if '2011-01-01'<=d<='2017-12-31' and d in observed]
    train_y=np.array([observed[dates[i]] for i in train]);test_y=np.array([observed[dates[i]] for i in test])
    if len(train)<3000 or len(test)<2000:raise ValueError('Insufficient predeclared training/test coverage')
    train_end=next(i for i,d in enumerate(dates) if d=='2011-01-01')
    predictions=[{'date':d,'observed_cms':observed.get(d),'phase':'warmup' if d<'2001-01-01' else 'training' if d<='2010-12-31' else 'held_out' if d<='2017-12-31' else 'unverified_continuation'} for d in dates]
    monthly=defaultdict(dict);models=[];prepared_models={};fitted={};simulations={}
    low=np.array([b[0] for b in BOUNDS]);span=np.array([b[1]-b[0] for b in BOUNDS])
    for key,label,distributed,ice,curve in MODELS:
        prepared=prepare(forcing,zones,distributed);prepared_models[key]=prepared
        fit_forcing=[{**z,'forcing':z['forcing'][:train_end]} for z in prepared]
        def objective(unit):
            parameters=low+np.asarray(unit)*span
            pred=simulate(fit_forcing,parameters,ice=ice,curve=curve)[:,0]*factor
            return float(np.sqrt(np.mean((pred[train]-train_y)**2)))
        candidates=qmc.Sobol(5,scramble=True,seed=1729).random_base2(5)
        # Thesis M3 parameters are a documented additional starting point.
        reference=(np.array([1.,81.5,.99,.45,0.])-low)/span
        candidates=np.vstack([reference,candidates]);losses=[objective(p) for p in candidates]
        start=candidates[int(np.argmin(losses))]
        fit=minimize(objective,start,method='Powell',bounds=[(0,1)]*5,options={'maxfev':800,'xtol':.002,'ftol':.0001})
        best=fit.x if fit.fun<=min(losses) else start
        parameters=low+best*span
        if not curve:parameters[-1]=0.
        fitted[key]=parameters
        result=simulate(prepared,parameters,ice=ice,curve=curve);simulations[key]=result
        pred=result[:,0]*factor
        pairs=monthly_pairs(dates,observed,pred);held=[r for r in pairs if '2011-01'<=r['period']<='2017-12']
        daily_scores=scores(test_y.tolist(),pred[test].tolist())
        model={'key':key,'label':label,'daily_scores':daily_scores,'monthly_scores':scores([r['observed'] for r in held],[r['predicted'] for r in held]),
            'training_daily_scores':scores(train_y.tolist(),pred[train].tolist()),'parameters':dict(zip(PARAMETERS,map(float,parameters))),
            'optimizer':{'method':'33 fixed Sobol/reference candidates then bounded Powell, maximum 800 local evaluations','success':bool(fit.success),'message':str(fit.message),'evaluations':int(fit.nfev)+33},
            'glacier_exhaustion_date':next((dates[i] for i in range(len(dates)) if ice and result[i,10]<=1e-9),None),
            'max_abs_mass_balance_residual_mm':float(np.max(np.abs(result[:,9]))),
            'held_out_ice_fraction_of_modelled_flow':float(result[test,6].sum()/result[test,0].sum()),
            'held_out_et_mm_year':float(result[test,4].sum()/(len(test)/365.25)),
            'parameters_at_bounds':[name for name,v,(lo,hi) in zip(PARAMETERS,parameters,BOUNDS) if (curve or name!='cn_offset') and min(v-lo,hi-v)/(hi-lo)<.01]}
        models.append(model)
        for row,value in zip(predictions,pred):row[key]=float(value)
        for r in pairs:monthly[r['period']].update(period=r['period'],observed=r['observed'],**{key:r['predicted']})
        print(f'{key}: held-out daily NSE {daily_scores["nse"]:.3f}; RMSE {daily_scores["rmse"]:.2f}; balance {model["max_abs_mass_balance_residual_mm"]:.2g}',flush=True)
    # Training monthly climatology is identical for every day of that month.
    climatology={m:float(np.mean([q for d,q in observed.items() if '2001-01-01'<=d<='2010-12-31' and int(d[5:7])==m])) for m in range(1,13)}
    baseline=np.array([climatology[int(d[5:7])] for d in dates])
    baseline_scores=scores(test_y.tolist(),baseline[test].tolist())
    duration=[]
    for label,values in [('Observed',test_y),('Seasonal baseline',baseline[test])]+[(m['key'],np.array([predictions[i][m['key']] for i in test])) for m in models]:
        duration.extend({'series':label,**r} for r in flow_duration(values))
    observed_fdc=flow_duration(test_y)
    q_at={r['exceedance_percent']:r['discharge_cms'] for r in observed_fdc}
    low_flow={'period':'2011–2017 screened daily record','q50_cms':q_at[50],'q90_cms':q_at[90],'q95_cms':q_at[95],
        'q90_q50_proxy':q_at[90]/q_at[50],'specific_discharge_l_s_km2':float(test_y.mean()*1000/area),
        'note':'Q90/Q50 is a flow-duration proxy, not a separated groundwater/baseflow fraction. Specific discharge depends on the provisional raster drainage area.'}
    # Fixed-parameter perturbations diagnose structural sensitivity, never refit to test years.
    sensitivity=[]
    base_params=fitted['m4'];base_result=simulations['m4'];base_rmse=models[-1]['daily_scores']['rmse']
    scenarios=[('No glacier melt',{'ice':False},None,None),('Half mapped glacier area',{'glacier_scale':.5},None,None),
        ('Initial ice depth 15 m water equivalent',{'ice_depth_mm':15000.},None,None),('Initial ice depth 60 m water equivalent',{'ice_depth_mm':60000.},None,None),
        ('Annual cubic glacier relation',{'ice_method':'annual_cubic'},None,None),('Event-accumulated CN',{'event_cn':True},None,None),
        ('No curve-number partition',{'curve':False},None,None),('ERA5 potential evaporation',{},'era5',None),
        ('Thesis printed Hamon units',{},'thesis_printed',None),('Precipitation +10%',{},None,(0,1.1)),
        ('Soil capacity +20%',{},None,(1,1.2)),('Crop coefficient +20%',{},None,(3,1.2)),
        ('Snow degree-day factor 3 mm/C/day',{'snow_ddf':3.},None,None),('Snow degree-day factor 6 mm/C/day',{'snow_ddf':6.},None,None)]
    for label,options,pet_method,change in scenarios:
        params=base_params.copy()
        if change:params[change[0]]*=change[1]
        prepared=prepare(forcing,zones,True,pet_method) if pet_method else prepared_models['m4']
        r=simulate(prepared,params,**options);sc=scores(test_y.tolist(),(r[test,0]*factor).tolist())
        sensitivity.append({'scenario':label,'scores':sc,'rmse_change_cms':sc['rmse']-base_rmse,
            'mean_flow_change_percent':float(100*(r[test,0].sum()/base_result[test,0].sum()-1)),
            'max_abs_mass_balance_residual_mm':float(np.max(np.abs(r[:,9])))})
    components=[]
    for period in sorted({d[:7] for d in dates}):
        ids=[i for i,d in enumerate(dates) if d.startswith(period)]
        r=base_result[ids];last=r[-1]
        components.append({'period':period,'precipitation_mm':float(r[:,12].sum()),'et_mm':float(r[:,4].sum()),
            'snowmelt_mm':float(r[:,5].sum()),'glacier_melt_mm':float(r[:,6].sum()),'quickflow_mm':float(r[:,7].sum()),
            'baseflow_mm':float(r[:,8].sum()),'runoff_mm':float(r[:,0].sum()),'snow_storage_mm':float(last[1]),
            'soil_storage_mm':float(last[2]),'groundwater_storage_mm':float(last[3]),'remaining_glacier_ice_mm':float(last[10]),
            'snow_area_proxy_percent':float(r[:,11].mean()*100)})
    label_path=ROOT/'CASE_STUDIES/landcover-reference-labels.csv'
    accuracy=classification_accuracy(read_csv(label_path))
    input_paths=[OUT/'sabitov-daily-forcing.csv',OUT/'sabitov-inputs.manifest.json',DATA/'pskem-discharge-daily.csv',
                 DATA/'pskem-observations.manifest.json',ROOT/'storage/Sabitov_Master_ERE_2018.pdf',label_path]
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'status':'exploratory_adaptation_not_operational',
        'thesis':{'author':'Timur Sabitov','year':2018,'title':'Hydrologic Modeling of Glaciated Watershed in Central Asia','local_file':'storage/Sabitov_Master_ERE_2018.pdf',
            'page_convention':'Printed thesis pages; PDF page = printed page + 9 for the main text','sha256':hashlib.sha256(input_paths[-2].read_bytes()).hexdigest()},
        'split':{'warmup':'2000','training':'2001–2010','held_out':'2011–2017','training_days':len(train),'held_out_days':len(test),
            'note':'Chronological holdout improves on thesis calibration of the last two years after one-year warm-up (p.36). Test results are reported for every predefined structure; no operational winner is selected.'},
        'inputs':manifest,'area_km2':area,'models':models,'baseline_daily_scores':baseline_scores,'monthly_predictions':list(monthly.values()),
        'flow_duration':duration,'low_flow':low_flow,'monthly_trends':trend_diagnostics(observed),'sensitivity':sensitivity,'components':components,
        'gauge_audit':gauge_comparison(),'classification_accuracy':accuracy,
        'assumptions':['Fixed glacier outlines and an assumed 30 m initial water-equivalent ice reservoir; not measured ice thickness.',
            'Degree-day ice melt 6 mm/C/day is an adaptation; thesis annual cubic relation retained only as dimensional sensitivity.',
            'SWE threshold 1 mm applied to three entire zones gives a coarse snow-area proxy, not MODSNOW or pixel snow validation.',
            'Daily resetting CN is a thesis-style continuous-model approximation. The SCS relationship is event based; an event-accumulated sensitivity resets after a day with <=0.1 mm liquid input.',
            'Growing season April–September is declared, not locally measured. Antecedent moisture uses previous five days of rain, excluding the current day.',
            'Hamon uses physical vapour density units and available-water ET; printed thesis formulation is tested separately.',
            'No independently validated soil hydrologic groups or land-cover labels; CN50/CN90 are thesis structural assumptions with a calibrated offset.',
            'No river travel-time routing, groundwater observations or glacier mass-balance calibration; ice fraction is simulated direct drainage.',
            'A fixed limited calibration budget can stop before convergence; boundary parameters and optimizer status are disclosed.',
            'Monthly Kendall/Sen diagnostics use 17 years with Holm correction; serial dependence can invalidate nominal p-values. These are exploratory, not causal climate attribution.'],
        'source_hashes':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in input_paths}}
    write_csv(OUT/'sabitov-daily-predictions.csv',predictions,list(predictions[0]))
    write_csv(OUT/'sabitov-model-components.csv',components,list(components[0]))
    write_csv(OUT/'sabitov-flow-duration.csv',duration,list(duration[0]))
    write_csv(OUT/'sabitov-monthly-trends.csv',report['monthly_trends'],list(report['monthly_trends'][0]))
    write_json(OUT/'sabitov-methods.json',report)
    print('Published daily adaptations, flow duration, monthly trends, sensitivities and audit.',flush=True)


if __name__=='__main__':
    main()
