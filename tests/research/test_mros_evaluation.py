import pytest
from research.mros_certification.evaluation import evaluate_prospective, structural_edge_decision, trading_integration_decision
SHA='a'*40; MODEL='b'*64
def test_missing_prospective_data_is_honest():
    assert evaluate_prospective(candidate_sha=SHA,index='NIFTY',predictions=(),outcomes={},model_sha=MODEL,baseline='buy_hold').status == 'INSUFFICIENT_PROSPECTIVE_DATA'
def test_provenance_and_future_leakage_rejected():
    row={'prediction_sha':'p','session':'s'}
    with pytest.raises(ValueError, match='PROSPECTIVE_PROVENANCE_MISMATCH'): evaluate_prospective(candidate_sha=SHA,index='NIFTY',predictions=(row,),outcomes={},model_sha=MODEL,baseline='x',minimum_samples=1)
def test_edge_and_integration_fail_closed():
    assert structural_edge_decision(candidate_sha=SHA,prospective_status='INSUFFICIENT_PROSPECTIVE_DATA',historical_oos=True,cost_evidence=True,robustness=True,independent_verification='PASS')['status']=='NOT_CERTIFIED'
    assert trading_integration_decision(candidate_sha=SHA)['live_authorized'] is False
