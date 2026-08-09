import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / 'scripts' / 'research' / 'hypothesis_factory' / 'certify_strategy_candidate.py'
spec = importlib.util.spec_from_file_location('certifier_truth', P)
m = importlib.util.module_from_spec(spec); assert spec and spec.loader; sys.modules[spec.name]=m; spec.loader.exec_module(m)


def eligible_candidate():
    return {
        'hypothesis_id':'SYN-GOOD',
        'candidate_shape_key':'shape-good',
        'rejection_reasons':[],
        'trades':150,
        'sessions_traded':30,
    }


def test_known_good_robustness_maps_to_validated_research_only():
    verdict,reasons=m.decide_verdict(eligible_candidate(), {
        'status':'ROBUSTNESS_PASSED','robustness_passed':True,'failed_gates':[]
    })
    assert verdict=='VALIDATED_RESEARCH'
    assert reasons==[]
    assert verdict not in m.FORBIDDEN_VERDICTS


def test_known_bad_negative_control_or_oos_failure_is_rejected():
    verdict,reasons=m.decide_verdict(eligible_candidate(), {
        'status':'ROBUSTNESS_FAILED','robustness_passed':False,
        'failed_gates':['positive_oos','negative_control_passed']
    })
    assert verdict=='REJECTED'
    assert 'positive_oos' in reasons
    assert 'negative_control_passed' in reasons


def test_missing_robustness_never_certifies():
    verdict,reasons=m.decide_verdict(eligible_candidate(), None)
    assert verdict=='ROBUSTNESS_REQUIRED'
    assert reasons==['missing_robustness_evidence']


def test_candidate_with_any_screen_rejection_is_terminal_rejected_even_if_robustness_claims_pass():
    c=eligible_candidate(); c['rejection_reasons']=['trades_below_threshold']
    verdict,reasons=m.decide_verdict(c, {'status':'ROBUSTNESS_PASSED','robustness_passed':True})
    assert verdict=='REJECTED'
    assert reasons==['trades_below_threshold']
