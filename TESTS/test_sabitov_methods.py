"""Dimensional, conservation, leakage and reference-label checks."""
import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'PIPELINES'))
from analyse_sabitov_methods import hamon_mm, adjusted_cn, scs_runoff, simulate, prepare, monthly_pairs, classification_accuracy


def test_scs_units_threshold_and_water_limit():
    assert scs_runoff(10,50)==0
    assert scs_runoff(100,50)==pytest.approx((100-50.8)**2/(100+203.2))
    assert scs_runoff(100,100)==100
    for cn in [30,50,90,100]:
        for p in [0,1,10,100,1000]:assert 0<=scs_runoff(p,cn)<=p


def test_antecedent_thresholds_are_mm_and_ordered():
    assert adjusted_cn(50,12,False)<50
    assert adjusted_cn(50,20,False)==50
    assert adjusted_cn(50,29,False)>50
    assert adjusted_cn(50,29,True)<50
    assert adjusted_cn(50,40,True)==50


def test_hamon_physical_units_and_freezing():
    assert hamon_mm(-5,180)==0
    # 20 C saturated density is about 17.3 g/m3, PET ~3.6 mm/day here.
    assert 3<hamon_mm(20,180)<4
    assert hamon_mm(20,180,printed=True)<hamon_mm(20,180)/5


@pytest.mark.parametrize('curve',[False,True])
@pytest.mark.parametrize('event',[False,True])
def test_stores_conserve_water_and_ice_is_finite(curve,event):
    rows=[(20.,-10.,0.,-10.,False)]*15+[(0.,15.,4.,10.,True)]*120
    prepared=[{'weight':1.,'glacier_fraction':.2,'cn':90.,'forcing':rows}]
    result=simulate(prepared,[1,50,.98,.6,0],curve=curve,event_cn=event,ice_depth_mm=100)
    assert np.max(np.abs(result[:,9]))<1e-10
    assert np.min(result[:,:9])>=0
    assert result[:,6].sum()<=20+1e-10
    assert result[:15,6].sum()==0
    assert result[-1,10]==pytest.approx(0)
    assert np.allclose(result[:,0],result[:,6]+result[:,7]+result[:,8])


def test_future_weather_cannot_change_earlier_runoff():
    first=[(20.,5.,2.,5.,True)]*10
    zone={'weight':1.,'glacier_fraction':.05,'cn':50.}
    a=simulate([{**zone,'forcing':first+[(100.,20.,4.,15.,True)]*10}],[1,50,.98,.6,0])
    b=simulate([{**zone,'forcing':first+[(0.,-20.,0.,-25.,False)]*10}],[1,50,.98,.6,0])
    assert np.array_equal(a[:10],b[:10])


def test_groundwater_retention_is_not_release_fraction():
    z={'weight':1.,'glacier_fraction':0.,'cn':50.,'forcing':[(100.,10.,0.,0.,True),(0.,10.,0.,0.,True)]}
    r=simulate([z],[1,10,.99,.45,0],ice=False,curve=False)
    assert r[0,3]==90
    assert r[1,8]==pytest.approx(.9)


def test_no_water_no_ice_cannot_generate_flow_or_et():
    z={'weight':1.,'glacier_fraction':0.,'cn':50.,'forcing':[(0.,20.,20.,20.,True)]*20}
    r=simulate([z],[1,50,.98,.6,0])
    assert np.max(np.abs(r))==0


def test_temperature_redistribution_preserves_basin_mean_and_rejects_gaps():
    zones=[{'zone':i,'area_km2':1+i,'mean_elevation_m':1000+i*1000,'glacier_fraction':0.,'glacier_area_km2':0.} for i in range(3)]
    row={'date':'2000-01-01','temperature_c':5,'precipitation_mm':10,'potential_et_mm':2}
    p=prepare([row],zones,True)
    assert sum(z['weight']*z['forcing'][0][1] for z in p)==pytest.approx(5)
    with pytest.raises(ValueError,match='contiguous'):prepare([row,{**row,'date':'2000-01-03'}],zones,True)


def test_monthly_prediction_uses_same_observed_days():
    dates=[f'2017-01-{d:02}' for d in range(1,32)]
    obs={d:2. for d in dates[:-1]}
    pred=[2.]*30+[1000.]
    rows=monthly_pairs(dates,obs,pred)
    assert rows[0]['paired_days']==30 and rows[0]['predicted']==2


def test_reference_accuracy_needs_labels_and_has_correct_orientation():
    assert classification_accuracy([{'mapped_class':'water','reference_class':''}])['overall_accuracy'] is None
    rows=[{'sample_id':str(i),'mapped_class':m,'reference_class':r} for i,(m,r) in enumerate([('water','water'),('water','rock'),('rock','rock')])]
    accuracy=classification_accuracy(rows)
    assert accuracy['overall_accuracy']==pytest.approx(2/3)
    water=next(r for r in accuracy['classes'] if r['class']=='water')
    assert water['user_accuracy']==.5 and water['producer_accuracy']==1
