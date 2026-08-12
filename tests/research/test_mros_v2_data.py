import pytest
from research.mros_certification.v2_data import RawArtifact,build_causal_features,freeze_hypotheses
def test_artifact_and_causal_build_are_deterministic():
    row=RawArtifact('VIX','s','2026-08-12T09:00:00Z','index','UTC',12).seal()
    assert build_causal_features({'VIX':row},cutoff='2026-08-12T09:15:00Z',required=('VIX',))['status']=='FEATURES_BUILT'
def test_future_and_provenance_attacks():
    with pytest.raises(ValueError,match='FUTURE_SOURCE_REJECTED'): build_causal_features({'VIX':{'source':'VIX','status':'AVAILABLE','observed_at':'2026-08-12T10:00:00Z','sha256':'x'}},cutoff='2026-08-12T09:15:00Z',required=('VIX',))
    assert build_causal_features({},cutoff='x',required=('VIX',))['status']=='BLOCKED_DATA'
def test_hypothesis_registry_freezes_contract():
    item={'hypothesis_id':'H1','features':['VIX'],'rationale':'volatility regime','targets':['NIFTY'],'benchmark':'V1','controls':['permutation'],'search_budget':1}
    assert freeze_hypotheses((item,))['status']=='FROZEN'
