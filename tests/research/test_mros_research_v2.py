import pytest
from research.mros_certification.research_v2 import *
SHA='a'*40
def registry(): return {'status':'FROZEN','hypotheses':({'hypothesis_id':'H1'},)}
def test_oos_blocker_and_no_edge_are_honest():
    assert run_incremental_oos(candidate_sha=SHA,registry=registry(),available_sources=('VIX',),required_sources=('VIX','DXY'),sample_count=2).status=='BLOCKED_DATA'
    assert run_incremental_oos(candidate_sha=SHA,registry=registry(),available_sources=('VIX',),required_sources=('VIX',),sample_count=20).status=='NO_STRUCTURAL_EDGE_FOUND'
def test_freeze_no_edge_and_package_safety():
    r=OOSResult('NO_STRUCTURAL_EDGE_FOUND',SHA,(),0,1)
    assert freeze_v2(r,feature_sha='b'*64,source_contract_sha='c'*64)['status']=='NO_STRUCTURAL_EDGE_FOUND'
    assert build_certification_package(candidate_sha=SHA,result=r,v1_sha='d'*64,safety={'broker_write_authority':False,'order_authority':False,'paper_authorized':False,'live_authorized':False})['independent_verification']=='PENDING'
def test_intraday_spec_and_discovery():
    spec=freeze_intraday_spec(); assert spec['gap_target_relabelled'] is False
    assert discover_intraday(candidate_sha=SHA,spec=spec,sample_count=0)['status']=='BLOCKED_DATA'
def test_invalid_spec_rejected():
    with pytest.raises(ValueError,match='INTRADAY_SPEC_INVALID'): discover_intraday(candidate_sha=SHA,spec={'status':'SPEC_FROZEN','gap_target_relabelled':True},sample_count=1)
