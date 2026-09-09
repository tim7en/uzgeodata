import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'PIPELINES'))
from cross_reference_water_bodies import relation,name_check,compare


def test_nearby_lake_is_not_promoted_to_identifier_match():
    dam={'hylak_id':'12','grand_id':'44'}
    assert relation(dam,{'water_body_id':'99','grand_id':'66'},12)=='nearby_candidate'
    assert relation(dam,{'water_body_id':'99','grand_id':'66'},2001) is None
    assert relation(dam,{'water_body_id':'12'},6700)=='native_hydrolakes_id'


def test_missing_identifiers_cannot_match_each_other():
    assert relation({'hylak_id':'','grand_id':'0'},{'water_body_id':'','grand_id':'0'},5000) is None
    assert relation({'grand_id':'4'},{'water_body_id':'123','grand_id':'4'},5000)=='native_grand_id'


def test_missing_names_are_not_agreement_and_spelling_is_not_identity():
    assert name_check({'dam_name':'Charvak'},{'name':''})==('name_missing',None)
    assert name_check({'dam_name':'Toktogul'},{'name':'TOKTOGUL'})==('same_normalised_name',1.0)


def test_zero_storage_stays_zero_and_never_creates_infinite_difference():
    r=compare({'dam_id':'1','capacity_mcm':'2000','reservoir_area_km2':'26'},
        {'water_body_id':'2','storage_volume_mcm':'0','area_km2':'25'},6700,'native_hydrolakes_id')
    assert r['lake_storage_mcm']==0 and r['storage_difference_percent'] is None
    assert r['area_difference_percent']==4
    assert r['spatial_check']=='spatial_disagreement'
