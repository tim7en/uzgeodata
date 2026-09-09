"""Publish lightweight study cards and current-model charts from stored evidence.

No fitting or Earth Engine retrieval. Scores are checked against the paired
daily output before publication; undefined JSON numbers become explicit nulls.
"""
import calendar
import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from hydromet.io import write_json

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT/'PUBLISHED/data/case-studies'


def safe_json(value):
    if isinstance(value, dict):
        return {k:safe_json(v) for k,v in value.items()}
    if isinstance(value, list):
        return [safe_json(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def monthly_rows(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row['date'][:7]].append(row)
    output = []
    for period, group in sorted(grouped.items()):
        paired = [r for r in group if r['period'] in ['validation','calibration']
                  and all(math.isfinite(float(r[k])) for k in ['observed_mm','simulated_mm'])]
        year, month = map(int, period.split('-'))
        required = calendar.monthrange(year, month)[1]
        # Reproduce the current model's published >=20 paired-day rule exactly.
        eligible = len(paired) >= 20
        split = paired[0]['period'] if paired else 'unused'
        if len({r['period'] for r in paired}) > 1:
            raise ValueError(f'Mixed evaluation splits in {period}')
        output.append({'period': period, 'split': split, 'valid_days': len(paired),
                       'expected_days': required,
                       'observed': float(np.mean([float(r['observed_mm']) for r in paired])) if eligible else None,
                       'simulated': float(np.mean([float(r['simulated_mm']) for r in paired])) if eligible else None})
    return output


def preview(path, draw):
    fig, ax = plt.subplots(figsize=(9,4.6), dpi=120, facecolor='#102632')
    ax.set_facecolor('#102632')
    draw(ax)
    ax.axis('off')
    fig.subplots_adjust(left=.04,right=.96,bottom=.08,top=.92)
    fig.savefig(path, facecolor=fig.get_facecolor(), format='svg', metadata={'Date':None})
    plt.close(fig)


def main():
    source = DATA/'pskem-daily-model.json'
    model = json.loads(source.read_text(encoding='utf8'))
    with (DATA/'pskem-daily-model.csv').open(encoding='utf8',newline='') as handle:
        rows = list(csv.DictReader(handle))
    validation = [r for r in rows if r['period']=='validation'
                  and all(math.isfinite(float(r[k])) for k in ['observed_mm','simulated_mm'])]
    obs = np.array([float(r['observed_mm']) for r in validation])
    sim = np.array([float(r['simulated_mm']) for r in validation])
    nse = 1-float(np.sum((obs-sim)**2)/np.sum((obs-obs.mean())**2))
    if len(obs) != model['skill']['validation']['n'] or abs(nse-model['skill']['validation']['nse']) > .0001:
        raise ValueError('Model summary and daily series disagree; rebuild the model before publishing.')
    clean = safe_json(model)
    if json.dumps(clean,allow_nan=False) != json.dumps(model):
        write_json(source,clean)
    monthly = monthly_rows(rows)
    eligible = [r for r in monthly if r['split']=='validation' and r['observed'] is not None]
    mo=np.array([r['observed'] for r in eligible]); ms=np.array([r['simulated'] for r in eligible])
    monthly_nse=1-float(np.sum((mo-ms)**2)/np.sum((mo-mo.mean())**2))
    if len(eligible)!=model['monthlySkill']['validation']['n'] or abs(monthly_nse-model['monthlySkill']['validation']['nse'])>.0001:
        raise ValueError('Monthly aggregation disagrees with model metrics.')
    regional=json.loads((DATA/'regional-station-study.json').read_text(encoding='utf8'))
    now=datetime.now(timezone.utc).isoformat()
    paths=[source,DATA/'pskem-daily-model.csv',DATA/'regional-station-study.json']
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    current={'generated_at':now,'model_generated_at':model['generatedAt'],'source_hashes':hashes,
             'model':safe_json(model['model']),'catchment':model['catchment'],
             'daily':model['skill']['validation'],'monthly':model['monthlySkill']['validation'],
             'seasonal':model['seasonalValidationScores'],'monthly_rows':monthly,
             'seasonal_rows':[dict(r,period=str(r['year']),expected_days=183,
                 valid_days=sum(1 for day in rows if int(day['date'][:4])==r['year']
                     and 4<=int(day['date'][5:7])<=9 and day['period'] in ['calibration','validation']
                     and all(math.isfinite(float(day[k])) for k in ['observed_mm','simulated_mm']))) for r in model['seasonalVolumes']],
             'validation_years':sorted({int(r['date'][:4]) for r in validation}),
             'calibration_years':model['model']['calibration']['years'],
             'parameters_at_bounds':model.get('parametersAtBounds'),
             'monthly_support':'Monthly means require at least 20 paired valid days, matching this model evaluation. Counts are retained; incomplete months are not total-volume estimates.',
             'scope':f"Historical hindcast using a {model['model']['calibration']['split']} split. Retrospective forcing is not prospective forecast validation."}
    write_json(DATA/'current-model.json',safe_json(current))
    def runoff(ax):
        selected=[r for r in monthly if r['split']=='validation']
        x=np.arange(len(selected))
        ax.fill_between(x,[r['observed'] for r in selected],color='#58c9e5',alpha=.15)
        ax.plot(x,[r['observed'] for r in selected],color='#58c9e5',linewidth=2)
        ax.plot(x,[r['simulated'] for r in selected],color='#edb06c',linewidth=1.8)
    preview(DATA/'chirchik-study-preview.svg',runoff)
    def network(ax):
        sites=regional['stations']
        ax.scatter([s['longitude'] for s in sites],[s['latitude'] for s in sites],
                   c=[s.get('elevation_m',0) for s in sites],cmap=LinearSegmentedColormap.from_list('terrain',['#49bcd1','#8bd9bf','#ffd596']),s=65,edgecolors='#a7dbe7',linewidths=.4)
        ax.set_aspect(1/math.cos(math.radians(41)))
    preview(DATA/'regional-study-preview.svg',network)
    payload={'generated_at':now,'source_hashes':hashes,'studies':[
        {'id':'chirchik','href':'#chirchik-study','title':'From mountain snow to river flow',
         'region':'CHIRCHIK / PSKEM','aim':'Test how elevation, snowfall and soil-water storage shape seasonal river flow.',
         'image':'/data/case-studies/chirchik-study-preview.svg',
         'image_alt':'Observed and simulated monthly runoff in held-out years, arranged consecutively as a study preview.',
         'evidence_date':model['generatedAt'],'metric':model['monthlySkill']['validation']['nse'],
         'metric_label':'Monthly NSE · historical validation','detail':f"{len(eligible)} held-out months · daily snowmelt model",
         'status':'Historical model evaluation'},
        {'id':'regional','href':'#regional-study','title':'Read the landscape through its stations',
         'region':'REGIONAL HYDROMET NETWORK','aim':'Explore how location, elevation and mapped soil texture relate to satellite vegetation and temperature.',
         'image':'/data/case-studies/regional-study-preview.svg',
         'image_alt':'Actual meteorological station locations, coloured by terrain elevation.',
         'evidence_date':regional['generated_at'],'metric':len(regional['stations']),
         'metric_label':'Meteorological locations','detail':f"{regional['period']} · {len(regional['monthly']):,} station-month records",
         'status':'Exploratory relationships'}]}
    write_json(DATA/'study-directory.json',payload)
    write_json(DATA/'study-landing.manifest.json',{'generated_at':now,'input_hashes':hashes,
               'daily_validation_nse_recomputed':nse,'monthly_validation_nse_recomputed':monthly_nse,
               'note':'Existing fit reused, not retrained. Undefined source summary numbers normalized to null.'})
    print('Published current-model.json, study-directory.json and two data-derived SVG previews.')


if __name__=='__main__':
    main()
