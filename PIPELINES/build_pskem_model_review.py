"""Independent chronological-run review, preserving the published reference fit."""
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from build_pskem_daily_model import scores
from build_study_landing import monthly_rows, safe_json
from hydromet.io import write_json

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'PUBLISHED/data/case-studies'
RUN=DATA/'model-audit/chronological-20260909'


def class_summary(rows):
    training=[r['observedMcm'] for r in rows if r['period']=='calibration']
    mean,sd=float(np.mean(training)),float(np.std(training))
    if len(training)<3 or sd==0:
        raise ValueError('Insufficient calibration variability for seasonal classes')
    def classify(value):
        z=(value-mean)/sd
        return 0 if z<=-1.28 else 1 if z<=-.43 else 2 if z<.43 else 3 if z<1.28 else 4
    held=[r for r in rows if r['period']=='validation']
    return {'training_years':len(training),'mean_mcm':mean,'std_mcm':sd,'test_years':len(held),
            'exact':sum(classify(r['observedMcm'])==classify(r['simulatedMcm']) for r in held),
            'within_one':sum(abs(classify(r['observedMcm'])-classify(r['simulatedMcm']))<=1 for r in held)}


def main():
    model=json.loads((RUN/'pskem-daily-model.json').read_text(encoding='utf8'))
    reference=json.loads((DATA/'pskem-daily-model.json').read_text(encoding='utf8'))
    with (RUN/'pskem-daily-model.csv').open(encoding='utf8',newline='') as handle:
        daily=list(csv.DictReader(handle))
    valid=[r for r in daily if r['period'] in ['calibration','validation']
           and np.isfinite(float(r['observed_mm'])) and np.isfinite(float(r['simulated_mm']))]
    train=[r for r in valid if r['period']=='calibration']
    test=[r for r in valid if r['period']=='validation']
    train_years=sorted({int(r['date'][:4]) for r in train})
    test_years=sorted({int(r['date'][:4]) for r in test})
    if max(train_years)>=min(test_years) or model['model']['calibration']['split']!='chronological':
        raise ValueError('Expected an ordered chronological holdout.')
    climatology={month:float(np.mean([float(r['observed_mm']) for r in train if int(r['date'][5:7])==month])) for month in range(1,13)}
    for r in valid:
        r['benchmark']=climatology[int(r['date'][5:7])]
    observed=np.array([float(r['observed_mm']) for r in test])
    predictions=np.array([float(r['simulated_mm']) for r in test])
    actual=scores(predictions,observed)
    if actual['n']!=model['skill']['validation']['n'] or abs(actual['nse']-model['skill']['validation']['nse'])>.0001:
        raise ValueError('Candidate summary disagrees with its daily series')
    monthly=monthly_rows(daily)
    for r in monthly:
        r['benchmark']=climatology[int(r['period'][5:7])] if r['observed'] is not None else None
    paired=[r for r in monthly if r['split']=='validation' and r['observed'] is not None]
    monthly_actual=scores(np.array([r['simulated'] for r in paired]),np.array([r['observed'] for r in paired]))
    if abs(monthly_actual['nse']-model['monthlySkill']['validation']['nse'])>.0001:
        raise ValueError('Candidate monthly scores disagree with >=20-day aggregation')
    seasonal=[]
    for record in model['seasonalVolumes']:
        days=[r for r in valid if int(r['date'][:4])==record['year'] and 4<=int(r['date'][5:7])<=9]
        seasonal.append({**record,'label':str(record['year']),
                         'benchmark':sum(r['benchmark'] for r in days)*model['catchment']['areaKm2']/1000,
                         'valid_days':len(days),'expected_days':183})
    seasons=[r for r in seasonal if r['period']=='validation']
    baseline={'daily':scores(np.array([r['benchmark'] for r in test]),observed),
              'monthly':scores(np.array([r['benchmark'] for r in paired]),np.array([r['observed'] for r in paired])),
              'seasonal':scores(np.array([r['benchmark'] for r in seasons]),np.array([r['observedMcm'] for r in seasons]))}
    inputs=[RUN/'pskem-daily-model.json',RUN/'pskem-daily-model.csv',DATA/'pskem-daily-model.json']
    inputs += [ROOT/'PUBLISHED/data/case-studies'/name for name in ['sabitov-daily-forcing.csv','pskem-candidate-catchment.geojson','elevation-profiles.csv']]
    inputs += [ROOT/'PUBLISHED/data/hydroclimate/pskem-discharge-daily.csv',ROOT/'PIPELINES/build_pskem_daily_model.py']
    result={'generated_at':datetime.now(timezone.utc).isoformat(),'run_directory':'/data/case-studies/model-audit/chronological-20260909/',
            'decision':'Preserve the published stratified reference. Foreground the stricter chronological test; do not tune further against its exposed holdout.',
            'train_years':train_years,'test_years':test_years,'model':model['model'],
            'candidate':{'daily':model['skill']['validation'],'monthly':model['monthlySkill']['validation'],'seasonal':model['seasonalValidationScores']},
            'reference':{'split':reference['model']['calibration']['split'],'daily':reference['skill']['validation'],
                         'monthly':reference['monthlySkill']['validation'],'seasonal':reference['seasonalValidationScores']},
            'benchmark':baseline,'monthly_rows':monthly,'seasonal_rows':seasonal,
            'classes':class_summary(model['seasonalVolumes']),'parameters_at_bounds':model['parametersAtBounds'],
            'inputs':{str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
            'limitations':[
                'Parameters were selected using calibration KGE only: 6,000 broad samples plus four refinement rounds of 3,000, seed 1729. Existing bounds were retained.',
                'This is a different validation split, not an accuracy contest with the previous stratified run. Its old parameters saw some years now held out.',
                'Baseline is the calibration-only monthly discharge climatology, evaluated on exactly the same valid days and months.',
                'Negative seasonal NSE means worse squared error than the held-out seasonal mean; that diagnostic mean is not itself an operational forecast.',
                'Monthly means need at least 20 paired days. Seasonal volumes sum available paired days; missing days are not extrapolated.',
                'Discharge screening uses neighbouring days retrospectively. Forcing is reanalysis; the candidate catchment and surveyed gauge location still require review.',
                'No observed snowpack/SWE or independent temperature-profile validation is available. Parameters at bounds are diagnostics, not permission to widen physical bounds to chase holdout skill.',
                'Further development needs inner calibration-period cross-validation and a new external test, not repeated selection against 2011–2017.',
            ]}
    write_json(DATA/'model-review.json',safe_json(result))
    print('Chronological model review published. Benchmark NSE:',{k:v['nse'] for k,v in baseline.items()})


if __name__=='__main__':
    main()
