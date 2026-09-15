"""Recompute model diagnostics on an explicit common domain; no inferred water-stress metric."""
from __future__ import annotations
import csv
import json
import math
from pathlib import Path
import sys
import duckdb

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ATLAS_MODULES.core.runtime import utc_now,write_json
from PIPELINES.build_water_flow_diagram import digest
FLOW=ROOT/'PUBLISHED/data/water-flow'
CUBE=ROOT/'PUBLISHED/data/atlas/cube'
GEOMETRY=ROOT/'PUBLISHED/data/hydroclimate/basins-level12.geojson'
OUT=FLOW/'regional-water-flow-sensitivity.json'
VARIABLES={'pre_mm_s':('TerraClimate precipitation','terraclimate-ee'),
           'aet_mm_s':('TerraClimate actual evapotranspiration','terraclimate-ee'),
           'run_mm_s':('ERA5-Land runoff','era5-provider'),
           'rtc_mm_s':('TerraClimate runoff','terraclimate-ee')}


def annual_totals(connection, areas, start, end, variables):
    """Each variable/year needs exactly 12 distinct non-null months for EVERY basin.

    Incomplete domain totals are withheld, never silently summed over a smaller area.
    Duplicate months are errors, including duplicates replacing a missing month.
    """
    if not areas or any(not math.isfinite(a) or a<=0 for a in areas.values()):
        raise ValueError('Invalid basin area')
    connection.execute('CREATE OR REPLACE TABLE basin_area (basin_id VARCHAR PRIMARY KEY, area_km2 DOUBLE)')
    connection.executemany('INSERT INTO basin_area VALUES (?,?)',list(areas.items()))
    dup=connection.execute('SELECT basin_id,variable,year,month FROM records WHERE year BETWEEN ? AND ? GROUP BY ALL HAVING count(*)>1 LIMIT 1',[start,end]).fetchone()
    if dup:raise ValueError(f'Duplicate basin month: {dup}')
    bad=connection.execute("SELECT count(*) FROM records WHERE year BETWEEN ? AND ? AND (month NOT BETWEEN 1 AND 12 OR month IS NULL OR unit != 'millimetres per month' OR unit IS NULL OR (value IS NOT NULL AND NOT isfinite(value)))",[start,end]).fetchone()[0]
    if bad:raise ValueError('Invalid period, unit or value')
    unknown=connection.execute('SELECT count(*) FROM records r LEFT JOIN basin_area a USING(basin_id) WHERE a.basin_id IS NULL AND year BETWEEN ? AND ?',[start,end]).fetchone()[0]
    if unknown:raise ValueError('Unknown basin geometry')
    values=connection.execute('''WITH annual AS (
      SELECT basin_id,variable,year,sum(value) mm FROM records WHERE year BETWEEN ? AND ?
      GROUP BY ALL HAVING count(*)=12 AND count(value)=12 AND count(DISTINCT month)=12
    ) SELECT variable,year,count(*) basins,sum(area_km2) area,sum(mm*area_km2*1e-6) volume
      FROM annual JOIN basin_area USING(basin_id) GROUP BY variable,year''',[start,end]).fetchall()
    lookup={(v,y):(n,a,total) for v,y,n,a,total in values}
    rows=[]
    for year in range(start,end+1):
        for variable in variables:
            n,a,total=lookup.get((variable,year),(0,0,None))
            rows.append(dict(year=year,variable=variable,complete_basins=n,total_basins=len(areas),
                             coverage_area_fraction=a/sum(areas.values()),
                             volume_km3=total if n==len(areas) else None,
                             status='complete' if n==len(areas) else 'incomplete_domain'))
    return rows


def efficiency_example(initial=.63,target=.73,withdrawal=100, recoverable_fraction=0):
    if not 0<initial<=target<=1 or not 0<=recoverable_fraction<=1 or withdrawal<0:
        raise ValueError('Invalid efficiency example')
    reduction=withdrawal*(1-initial/target)
    return dict(baseline_withdrawal_units=withdrawal,initial_efficiency=initial,target_efficiency=target,
                recoverable_fraction=recoverable_fraction,gross_withdrawal_reduction_units=reduction,
                reduced_return_flow_units=reduction*recoverable_fraction,
                net_downstream_gain_units=reduction*(1-recoverable_fraction))


def build(cube=CUBE,out=OUT):
    cube=Path(cube);index=json.loads((cube/'index.json').read_text())
    geo=json.loads(GEOMETRY.read_text())
    areas={str(f['properties']['HYBAS_ID']):float(f['properties']['SUB_AREA']) for f in geo['features']}
    if len(areas)!=len(geo['features']):raise ValueError('Duplicate basin geometry')
    paths=[]; available=[]; missing=[]; hashes={}
    for variable in VARIABLES:
        entry=index['files'].get(variable)
        if not entry:
            missing.append(variable);continue
        # Follow the manifest; never glob stale files alongside its chosen partition.
        relative=Path(entry['path']).relative_to('/data/atlas/cube')
        path=cube/relative
        if not path.is_file():raise ValueError(f'Manifest file missing: {path}')
        paths.append(str(path));available.append(variable);hashes[str(relative)]=digest(path)
    if not {'pre_mm_s','aet_mm_s','run_mm_s'}<=set(available):raise ValueError('Required diagnostics unavailable')
    con=duckdb.connect()
    con.execute('SET threads=1')
    try:
        con.from_parquet(paths,hive_partitioning=True).create_view('records')
        annual=annual_totals(con,areas,2003,2024,available)
    finally:con.close()
    by={(r['year'],r['variable']):r['volume_km3'] for r in annual}
    matched=[y for y in range(2003,2025) if all(by[y,v] is not None for v in available)]
    if not matched:raise ValueError('No complete common-domain years')
    balance=[]
    for y in range(2003,2025):
        p,a=by[y,'pre_mm_s'],by[y,'aet_mm_s']
        balance.append(dict(year=y,**{v:by[y,v] for v in available},
                            p_minus_aet_km3=p-a if p is not None and a is not None else None))
    report=dict(schema_version=2,generated_at=utc_now(),title='Modelled land-water diagnostics',
      basis='modelled',period=[2003,2024],matched_years=matched,domain=dict(basins=len(areas),area_km2=sum(areas.values()),geometry=str(GEOMETRY.relative_to(ROOT)),geometry_sha256=digest(GEOMETRY)),
      source_cube_index_sha256=digest(cube/'index.json'),input_hashes=hashes,
      source_cube_release=index.get('release'),
      variables={v:dict(label=VARIABLES[v][0],source_id=VARIABLES[v][1],status='available' if v in available else 'not_in_snapshot') for v in VARIABLES},
      annual_coverage=annual,annual=balance,
      means_km3={v:sum(by[y,v] for y in matched)/len(matched) for v in available},
      methodology=dict(volume='sum over non-overlapping local basins: sum of 12 monthly depths (mm) × basin area (km2) × 1e-6 = km3/year',
        completeness='Exactly 12 distinct finite values per basin/variable/year; all domain basins required. Null annual totals are withheld.',
        comparison='Means use common complete years. P minus AET uses two TerraClimate outputs. ERA5 runoff is a separate model diagnostic, not a closure term.',
        evidence_limit='The published cube lacks within-basin pixel/day coverage and revisions; complete monthly values do not certify source accuracy or full pixel coverage.',
        uncertainty='No confidence interval or local gauge validation established. Inter-product differences are not error bars.'),
      efficiency_example=dict(status='Illustrative dimensional arithmetic, not a policy forecast',unit='units per 100 units initially withdrawn',source_ids=['fao-real-savings'],
        assumptions=['Fixed delivered demand','No irrigated-area expansion or rebound','Recoverability is hypothetical, not measured','No national or multi-country volume extrapolation'],
        cases=[efficiency_example(recoverable_fraction=r) for r in (0,.5,1)]),
      withdrawn_claims=['Historical shortage/exceedance counts based on a constant 2022 withdrawal and modelled P minus AET.',
        'Regional km3 savings inferred from Uzbekistan efficiency and sector shares.',
        'Causal climate-trend attribution or a validated regional discharge forecast.'])
    write_json(out,report)
    csvpath=Path(out).with_name('regional-model-annual.csv')
    with csvpath.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(annual[0]),lineterminator='\n');w.writeheader();w.writerows(annual)
    return report


if __name__=='__main__':
    r=build();print(json.dumps({'means_km3':r['means_km3'],'matched_years':r['matched_years'],'variables':r['variables']},indent=2))
