"""Scientific invariants for the extended hydrology experiments."""
import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'PIPELINES'))
from analyse_chirchik_validation import monthly_snow, snow_station_bounds, ridge_forecast, climate_validation
from model_chirchik_water import bucket, bayesian_linear, design_rows, readiness_summary, surface_months


def test_bucket_conserves_water_across_snow_accumulation_melt_and_overflow():
    forcing=[{'period':f'2020-{m:02}','precipitation_mm':500 if m<7 else 0,'temperature_c':-10 if m<4 else 15,'potential_et_mm':50} for m in range(1,13)]
    rows=bucket(forcing,[3,1,120,.2,.1],2000)
    assert max(abs(r['mass_balance_residual_mm']) for r in rows)<1e-9
    assert rows[2]['snow_storage_mm']>1000
    assert rows[5]['melt_mm']>0
    assert all(r['soil_storage_mm']>=0 and r['snow_storage_mm']>=0 and r['runoff_mm']>=0 for r in rows)
    assert rows[1]['discharge_cms']==pytest.approx(rows[1]['runoff_mm']*2000*1000/(29*86400))


def test_zero_water_cannot_create_runoff():
    rows=bucket([{'period':'2020-01','precipitation_mm':0,'temperature_c':10,'potential_et_mm':100}], [3,1,100,.3,.2],2000)
    assert rows[0]['discharge_cms']==rows[0]['et_mm']==0


def test_antecedent_rain_excludes_current_and_future_months():
    rows=[{'period':f'2020-{m:02}','precipitation_mm':m,'temperature_c':1,'potential_et_mm':1} for m in range(1,7)]
    assert design_rows(rows)[3]['antecedent_p3_mm']==6
    rows[3]['precipitation_mm']=999
    assert design_rows(rows)[3]['antecedent_p3_mm']==6


def test_bayesian_prediction_does_not_restandardise_on_test_distribution():
    rng=np.random.default_rng(1);x=rng.normal(size=(50,6));y=20+5*x[:,0]+rng.normal(size=50)
    small=bayesian_linear(x,y,x[:3]);large=bayesian_linear(x,y,np.vstack([x[:3],np.ones((4,6))*1000]))
    assert np.allclose(small[0],large[0][:3])
    assert np.all(small[1]<small[0]) and np.all(small[0]<small[2])


def test_ridge_fit_cannot_see_held_out_responses():
    train=[{'p':i,'volume_mcm':2*i+1} for i in range(10)]
    first,fit=ridge_forecast(train,[{'p':12,'volume_mcm':1}],['p'])
    second,fit2=ridge_forecast(train,[{'p':12,'volume_mcm':99999}],['p'])
    assert first==second and fit==fit2


def test_snow_calendar_retains_cloud_gaps_and_minimum_days():
    rows=[{'sensor':'terra','date':f'2020-01-{i:02}','elevation_band':'all','valid_area_percent':'90' if i<10 else '20','snow_cover_percent':'50','snow40_cover_percent':'40'} for i in range(1,32)]
    r=monthly_snow(rows)[0]
    assert r['eligible_days']==9 and r['snow_cover_percent'] is None
    rows[9]['valid_area_percent']='70'
    assert monthly_snow(rows)[0]['snow_cover_percent']==50


def test_station_snow_bounds_do_not_treat_cloud_as_snow_free():
    station='uz:station/meteo-419704'
    obs=[{'station_id':station,'year':'2020','month':'2','variable':'snow_cover_days','value':'20'}]
    rows=[{'station_id':station,'sensor':'terra','date':f'2020-02-{i:02}','ndsi':'50' if i<6 else ''} for i in range(1,30)]
    _,bounds=snow_station_bounds(obs,rows)
    assert bounds[0]['lower_bound']==5 and bounds[0]['upper_bound']==29
    assert bounds[0]['unknown_days']==24


def test_et_composite_overlap_and_partial_month_policy():
    rows=[{'date':f'2020-01-{d:02}','value':'8','valid_area_percent':'50'} for d in [1,9,17,25]]
    result=surface_months(rows,'et')
    assert result[0]['value']==31 and result[0]['covered_days']==31
    assert result[1]['value'] is None and result[1]['covered_days']==1


def test_last_year_composite_uses_actual_five_days():
    r=surface_months([{'date':'2021-12-27','value':'10','valid_area_percent':'80'}],'et')[0]
    assert r['covered_days']==5 and r['value'] is None


def test_readiness_cannot_average_out_a_red_or_amber_gate():
    for status in ['red','amber']:
        r=readiness_summary([{'status':'green'}]*7+[{'status':status}])
        assert r['overall']==status and not r['operational_ready']
    assert readiness_summary([{'status':'green'}]*8)['operational_ready']
    assert not readiness_summary([])['operational_ready']


def test_station_correction_cannot_learn_test_observations():
    station='uz:station/meteo-419704';obs=[];products=[]
    for year in range(2010,2021):
        for month in range(1,13):
            obs.append({'station_id':station,'year':str(year),'month':str(month),'variable':'air_temperature_mean','value':str(month)})
            products.append({'station_id':station,'period':f'{year}-{month:02}','variable':'air_temperature_mean','value':str(month-5),'product':'era5-land','unit':'°C'})
    first,_=climate_validation(obs,products)
    for r in obs:
        if int(r['year'])>2017:r['value']='999'
    second,_=climate_validation(obs,products)
    assert first[0]['correction']['adjustments']==second[0]['correction']['adjustments']
    assert first[0]['correction']['corrected_test']['rmse']==0
    assert first[0]['raw']['kge'] is None
