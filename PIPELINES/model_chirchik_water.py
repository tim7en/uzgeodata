"""Compare monthly seasonal, snow/soil bucket, random-forest and Bayesian models.

Exploratory hindcasts for a provisional catchment, with fixed chronological splits.
No model is declared operational from a good score alone.
"""
import calendar
import hashlib
import json
from datetime import date,datetime,timedelta,timezone
from statistics import mean

import numpy as np
from scipy.optimize import differential_evolution
from scipy.stats import t as student_t
from sklearn.ensemble import RandomForestRegressor

from build_chirchik_case_studies import DATA,OUT,read_csv,write_csv,write_json,scores,discharge_months,calendar_audit

FEATURES=['precipitation_mm','temperature_c','potential_et_mm','antecedent_p3_mm','season_sin','season_cos']


def readiness_summary(steps):
    statuses={s['status'] for s in steps}
    if not statuses <= {'green','amber','red'}:raise ValueError('Unknown readiness status')
    return {'steps':steps,'overall':'red' if 'red' in statuses else 'amber' if 'amber' in statuses else 'green',
        'operational_ready':bool(steps) and statuses=={'green'},
        'meaning':'Green marks a completed stated check. Release readiness requires every listed check to be green; a red gate cannot be averaged away. Refreshing inputs does not replace validation.'}


def bucket(forcing,parameters,area_km2):
    melt_factor,p_factor,capacity,release,quick_fraction=parameters
    snow=soil=0.;rows=[]
    for row in forcing:
        year,month=map(int,row['period'].split('-'));days=calendar.monthrange(year,month)[1]
        p=max(0,float(row['precipitation_mm']))*p_factor;temp=float(row['temperature_c']);pet=max(0,float(row['potential_et_mm']))
        previous=snow+soil;snow_fraction=1/(1+np.exp(np.clip(temp/2,-40,40)))
        snow+=p*snow_fraction;melt=min(snow,melt_factor*max(temp,0)*days);snow-=melt
        liquid=p*(1-snow_fraction)+melt;quick=quick_fraction*liquid;soil+=liquid-quick
        et=min(soil,pet*min(soil/capacity,1));soil-=et
        excess=max(0,soil-capacity);soil-=excess;base=release*soil;soil-=base
        runoff=quick+excess+base
        residual=p-et-runoff-(snow+soil-previous)
        rows.append({'period':row['period'],'discharge_cms':runoff*area_km2*1000/(days*86400),'runoff_mm':runoff,
            'snow_storage_mm':snow,'soil_storage_mm':soil,'et_mm':et,'melt_mm':melt,'mass_balance_residual_mm':residual})
    return rows


def design_rows(forcing):
    rows=[]
    for i,row in enumerate(forcing):
        month=int(row['period'][-2:]);items={key:float(row[key]) for key in ['precipitation_mm','temperature_c','potential_et_mm']}
        items['potential_et_mm']=max(0,items['potential_et_mm'])
        items.update(period=row['period'],antecedent_p3_mm=sum(float(r['precipitation_mm']) for r in forcing[max(0,i-3):i]),
            season_sin=np.sin(2*np.pi*month/12),season_cos=np.cos(2*np.pi*month/12))
        rows.append(items)
    return rows


def bayesian_linear(x,y,predict):
    """Conjugate normal/inverse-gamma regression on training-standardised variables.

    Prior beta|variance ~ N(0, variance I), weak intercept precision 1e-6,
    variance ~ InvGamma(2,1) in standardised response units. No MCMC required.
    """
    center=x.mean(0);scale=x.std(0);scale[scale==0]=1
    ym=float(y.mean());ys=float(y.std()) or 1
    z=np.column_stack([np.ones(len(x)),(x-center)/scale]);target=(y-ym)/ys
    prior=np.diag([1e-6]+[1.]*x.shape[1]);precision=prior+z.T@z;cov=np.linalg.inv(precision)
    beta=cov@z.T@target;a=2+len(y)/2;b=1+.5*(target@target-beta@precision@beta)
    xp=np.column_stack([np.ones(len(predict)),(predict-center)/scale])
    mu=xp@beta*ys+ym;sd=np.sqrt(b/a*(1+np.sum((xp@cov)*xp,axis=1)))*ys
    quantile=student_t.ppf(.975,2*a)
    coefficient_sd=np.sqrt(np.diag(cov)*b/a)*ys
    return mu,mu-quantile*sd,mu+quantile*sd,{'features':FEATURES,'coefficients':(beta[1:]*ys).tolist(),
        'coefficient_lower':((beta-quantile*np.sqrt(np.diag(cov)*b/a))*ys)[1:].tolist(),
        'coefficient_upper':((beta+quantile*np.sqrt(np.diag(cov)*b/a))*ys)[1:].tolist(),
        'prior':'Normal / inverse-gamma; coefficient precision 1; intercept precision 1e-6; a0=2,b0=1 after training-only standardisation',
        'interpretation':'Coefficient change per training standard deviation of each predictor; correlated covariates prevent causal interpretation. Gaussian predictions may be negative and are shown honestly.'}


def surface_months(rows,product):
    """Allocate composite means/totals to calendar months by overlap duration."""
    groups={}
    for row in rows:
        if row['value']=='' or float(row['valid_area_percent'])<=0:continue
        begin=date.fromisoformat(row['date']);duration=1 if product=='albedo' else min(8,(date(begin.year+1,1,1)-begin).days)
        for offset in range(duration):
            day=begin+timedelta(days=offset);key=day.strftime('%Y-%m');g=groups.setdefault(key,{'sum':0.,'days':0,'coverage_sum':0.})
            g['sum']+=float(row['value'])/duration if product=='et' else float(row['value'])
            g['days']+=1;g['coverage_sum']+=float(row['valid_area_percent'])
    result=[]
    for p,g in sorted(groups.items()):
        expected=calendar.monthrange(int(p[:4]),int(p[-2:]))[1]
        result.append({'period':p,'product':product,'value':g['sum'] if product=='et' and g['days']==expected else g['sum']/g['days'] if product!='et' else None,
            'covered_days':g['days'],'expected_days':expected,'mean_valid_area_percent':g['coverage_sum']/g['days']})
    return result


def main():
    forcing=read_csv(OUT/'pskem-energy-monthly.csv');forcing.sort(key=lambda r:r['period'])
    candidates=json.loads((OUT/'chirchik.json').read_text(encoding='utf-8'));area=candidates['catchment']['area_km2']
    manifest=json.loads((DATA/'pskem-observations.manifest.json').read_text(encoding='utf-8'))
    flagged={('uz:station/gauge-16290',r['year'],r['month'],r['day']) for r in manifest['suspectDailyValues']}
    valid,_=calendar_audit(read_csv(DATA/'pskem-discharge-daily.csv'));q=discharge_months(valid,flagged)
    observed={r['period']:r['screened_mean'] for r in q if r['eligible']}
    train_ids=[i for i,r in enumerate(forcing) if '2001-01'<=r['period']<='2010-12' and r['period'] in observed]
    test_ids=[i for i,r in enumerate(forcing) if '2011-01'<=r['period']<='2017-12' and r['period'] in observed]
    training_y=np.array([observed[forcing[i]['period']] for i in train_ids]);test_y=np.array([observed[forcing[i]['period']] for i in test_ids])
    parameter_names=['melt_factor_mm_C_day','precipitation_multiplier','soil_capacity_mm','monthly_baseflow_fraction','quickflow_fraction']
    bounds=[(1,8),(.5,1.5),(50,500),(.03,.6),(0,.5)]
    train_forcing=[r for r in forcing if r['period']<='2010-12']
    def objective(parameters):
        result=bucket(train_forcing,parameters,area)
        prediction=np.array([result[i]['discharge_cms'] for i in train_ids])
        return float(np.sqrt(np.mean((prediction-training_y)**2)))
    fit=differential_evolution(objective,bounds,seed=1729,maxiter=60,popsize=8,tol=.001,polish=True,workers=1)
    physics=bucket(forcing,fit.x,area);print('Bucket calibration complete',flush=True)
    features=design_rows(forcing);x=np.array([[r[k] for k in FEATURES] for r in features]);trainx=x[train_ids];testx=x[test_ids]
    forest=RandomForestRegressor(n_estimators=200,max_depth=5,min_samples_leaf=8,random_state=1729,n_jobs=1).fit(trainx,training_y)
    forest_all=forest.predict(x);bayes,lower,upper,posterior=bayesian_linear(trainx,training_y,x)
    climatology={m:mean(observed[r['period']] for r in forcing if '2001-01'<=r['period']<='2010-12' and int(r['period'][-2:])==m) for m in range(1,13)}
    output=[]
    for i,row in enumerate(forcing):
        output.append({'period':row['period'],'observed_cms':observed.get(row['period']),
            'seasonal_climatology':climatology[int(row['period'][-2:])],'physical_bucket':physics[i]['discharge_cms'],
            'random_forest':float(forest_all[i]),'bayesian_linear':float(bayes[i]),'bayesian_lower95':float(lower[i]),'bayesian_upper95':float(upper[i]),
            'phase':'warmup' if row['period']<'2001-01' else 'training' if row['period']<='2010-12' else 'held_out' if row['period']<='2017-12' else 'unverified_continuation'})
    models=[]
    for key in ['seasonal_climatology','physical_bucket','random_forest','bayesian_linear']:
        model_scores=scores(test_y.tolist(),[output[i][key] for i in test_ids])
        models.append({'model':key,'scores':model_scores})
    # Permute whole test years while retaining calendar-month alignment.
    rng=np.random.default_rng(1729);years=sorted({forcing[i]['period'][:4] for i in test_ids});importance=[]
    year_indices={year:[j for j,i in enumerate(test_ids) if forcing[i]['period'].startswith(year)] for year in years}
    reference=models[2]['scores']['rmse']
    for k,feature in enumerate(FEATURES):
        deltas=[]
        for _ in range(20):
            permuted=testx.copy();shuffle=rng.permutation(years)
            for target,source in zip(years,shuffle):permuted[year_indices[target],k]=testx[year_indices[source],k]
            rmse=float(np.sqrt(np.mean((forest.predict(permuted)-test_y)**2)));deltas.append(rmse-reference)
        importance.append({'variable':feature,'mean_rmse_increase_cms':mean(deltas),'min':min(deltas),'max':max(deltas),
            'interpretation':'Whole-year permutation preserves month alignment; predictive reliance, not causation. Calendar features do not vary between years, so this test cannot measure their importance.'})
    intervals={'nominal':.95,'held_out_coverage':float(np.mean((test_y>=lower[test_ids])&(test_y<=upper[test_ids]))),
        'mean_width_cms':float(np.mean(upper[test_ids]-lower[test_ids])),'note':'Posterior predictive intervals conditional on linear structure and independent Gaussian errors; serial dependence and catchment uncertainty are omitted.'}
    surface=[]
    for product in ['lst','et','albedo']:surface.extend(surface_months(read_csv(OUT/f'pskem-{product}-composites.csv'),product))
    profiles=read_csv(OUT/'elevation-profiles.csv');land=read_csv(OUT/'landcover-elevation.csv')
    latest=json.loads((OUT/'environment-energy.manifest.json').read_text());spatial=json.loads((OUT/'environment-profile.manifest.json').read_text())
    scenarios=[]
    for name,delta_t,p_factor in [('reference',0,1),('temperature_plus_2C',2,1),('precipitation_minus_10pct',0,.9)]:
        changed=[{**r,'temperature_c':float(r['temperature_c'])+delta_t,'precipitation_mm':float(r['precipitation_mm'])*p_factor} for r in forcing]
        result=bucket(changed,fit.x,area);years=[]
        for year in range(2011,2018):
            rows=[r for r in result if r['period'].startswith(str(year))]
            years.append(sum(r['runoff_mm'] for r in rows))
        scenarios.append({'scenario':name,'mean_annual_runoff_mm_2011_2017':mean(years),'interpretation':'Fixed-parameter sensitivity scenario; not a climate projection or causal attribution.'})
    result={'version':'3.0.0','generated_at':datetime.now(timezone.utc).isoformat(),'monthly_models':models,'model_series':output,
        'physical_parameters':dict(zip(parameter_names,map(float,fit.x))),'physical_parameter_bounds':dict(zip(parameter_names,bounds)),
        'physical_optimisation':{'method':'differential_evolution + polish','seed':1729,'maxiter':60,'popsize':8,'training_rmse':float(fit.fun),'converged':bool(fit.success)},
        'physical_mass_balance_max_abs_mm':max(abs(r['mass_balance_residual_mm']) for r in physics),
        'physical_states':physics,'bayesian_posterior':posterior,'bayesian_interval_check':intervals,'feature_importance':importance,
        'surface_monthly':surface,'energy_monthly':forcing,'elevation_profiles':profiles,'landcover_elevation':land,
        'profile_metadata':spatial,'freshness':latest,'scenarios':scenarios,'model_limits':[
            'Gauge coordinate is ambiguous; no model is approved for operational use.',
            'Physical model uses monthly temperature as a coarse snow/rain and melt approximation; it has no explicit glacier, reservoir or channel routing component.',
            'Random forest and Bayesian linear regression are exploratory models with 120 training and 84 held-out monthly observations; effective independent sample size is much smaller.',
            'Bayesian priors and Gaussian-error assumptions are explicit; posterior intervals do not include all sources of uncertainty.',
            '2018 onward is an unverified continuation driven by reanalysis; no contemporaneous discharge validation exists in this delivery.']}
    statuses=[('Observations','green','Historical P/T/Q and snow-day records imported; source dates retained.'),
        ('Quality control','amber','Three suspect discharge values screened; one impossible date quarantined; source confirmation pending.'),
        ('Station validation','amber','Historical comparisons and chronological correction tests computed; station metadata and product independence still need verification.'),
        ('Snow coverage','amber','Clouds and short eligible March samples restrict the snow–flow experiment.'),
        ('Gauge & terrain','red','Gauge-to-main-channel assignment unresolved; do not use nearest-reach snapping automatically.'),
        ('Land cover','amber','10 m class areas computed; local change accuracy has no independent labelled sample yet.'),
        ('Model verification','amber','Held-out scores and Bayesian interval coverage available; catchment and structural uncertainty remain.'),
        ('Current inputs','green' if forcing[-1]['period']==latest['era5_latest_available'] else 'amber',f"ERA5 processed through {forcing[-1]['period']}; latest available {latest['era5_latest_available']}. Individual satellite dates differ.")]
    result['readiness']=readiness_summary([{'label':a,'status':b,'reason':c} for a,b,c in statuses])
    result['readiness']['blocker']='Resolve gauge location and verify the catchment; then repeat calibration and verification. Latest inputs alone do not make a model operational.'
    inputs=[OUT/'pskem-energy-monthly.csv',OUT/'elevation-profiles.csv',OUT/'landcover-elevation.csv',DATA/'pskem-discharge-daily.csv',DATA/'pskem-observations.manifest.json',OUT/'chirchik.json',OUT/'environment-profile.manifest.json',OUT/'environment-energy.manifest.json',__import__('pathlib').Path(__file__)]+[OUT/f'pskem-{p}-composites.csv' for p in ['lst','et','albedo']]
    result['provenance']=[{'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in inputs]
    write_json(OUT/'environment-modelling.json',result);write_csv(OUT/'monthly-model-predictions.csv',output,list(output[0]));write_csv(OUT/'surface-monthly.csv',surface,list(surface[0]))
    print(json.dumps({'models':models,'bayesian_intervals':intervals,'physical_parameters':result['physical_parameters'],'latest':forcing[-1]['period']},indent=2))


if __name__=='__main__':main()
