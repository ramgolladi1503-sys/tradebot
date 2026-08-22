import pytest
from tep.research import *
from tep.live import *
from tep.config import TEPConfig
from tep.cleanup import *
def test_edge_certification_cannot_skip_evidence():
 with pytest.raises(ValueError):ResearchVerdict(structural_edge_certified=True).validate()
def test_search_pressure_rejects_duplicate_trial():
 h=FrozenHypothesis('h','trend','m','s','d','o');l=SearchPressureLedger();l.record(h,'FAIL')
 with pytest.raises(ValueError):l.record(h,'PASS')
def test_cost_model_is_net_cost_component():assert CostModel(1,2,3,4,5).round_trip_bps==15
def test_dynamic_subscriptions_are_not_hardcoded_counts():
 p=LaunchPlan('s','2026-08-22','abcdef1',('NIFTY',),('A',));assert derive_subscriptions(p,['B','A'])==('A','B','NIFTY')
def test_live_evidence_requires_lossless_independent_session():
 e=SessionEvidence('s','sha','p','v',1,DurabilityCounters(1,1,0),True);assert e.live_verified()
 assert not SessionEvidence('s','sha','p','p',1,DurabilityCounters(1,1,0),True).live_verified()
def test_secret_values_rejected():
 with pytest.raises(ValueError):TEPConfig('/r','/e','/s',('TOKEN=abc',)).validate()
def test_cleanup_fails_closed():
 with pytest.raises(PermissionError):require_safe(CleanupCandidate('/x',True,True,False,False,False,False,False))
