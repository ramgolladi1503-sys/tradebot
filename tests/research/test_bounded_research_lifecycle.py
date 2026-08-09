import importlib.util
import json
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / 'scripts' / 'research' / 'hypothesis_factory' / 'bounded_research_lifecycle.py'
spec = importlib.util.spec_from_file_location('bounded_lifecycle', P)
m = importlib.util.module_from_spec(spec); assert spec and spec.loader; sys.modules[spec.name]=m; spec.loader.exec_module(m)


def spec():
    return {
        'instrument':'BANKNIFTY','family':'opening_pullback','direction':'BUY_CE',
        'parameters':{'opening_minutes':30,'retrace':0.5,'hold_minutes':15},
        'entry_rule':'opening_pullback_resume','exit_rule':'time_stop','cost_bps':8.0,
        'dataset_sha256':'abc123','information_set_id':'BANKNIFTY_5M_PRICE_ONLY_V1'
    }


def test_candidate_identity_is_immutable_after_creation():
    r=m.new_candidate(spec()); m.assert_integrity(r)
    r['immutable_spec']['parameters']['retrace']=0.4
    with pytest.raises(ValueError, match='candidate_fingerprint_mismatch'):
        m.assert_integrity(r)


def test_rejection_is_terminal_and_cannot_be_reopened():
    r=m.new_candidate(spec())
    r=m.transition(r,'CANDIDATE_OF_RECORD','screen gate passed')
    r=m.transition(r,'REJECTED','walk-forward failed')
    assert r['certification']=='REJECTED'
    with pytest.raises(ValueError, match='illegal_transition'):
        m.transition(r,'CANDIDATE_OF_RECORD','try again')


def test_clean_zero_survivor_domain_closes_permanently():
    gens=[
        {'generation_id':'BASELINE','hypotheses':120,'admissible_candidates':0,'dataset_sha256':'sha'},
        {'generation_id':'EXPANDED','hypotheses':500,'admissible_candidates':0,'dataset_sha256':'sha'},
        {'generation_id':'STATE','hypotheses':1152,'admissible_candidates':0,'dataset_sha256':'sha'},
        {'generation_id':'CROSS','hypotheses':800,'admissible_candidates':0,'dataset_sha256':'sha'},
    ]
    out=m.close_search_domain(domain_id='BANKNIFTY_PRICE_DISCOVERY_V1', information_set_id='BANKNIFTY_NIFTY_SENSEX_5M_PRICE_V1', dataset_sha256='sha', generations=gens)
    assert out['status']=='NO_CANDIDATE_FOUND_IN_SEARCH_DOMAIN'
    assert out['closed'] is True
    assert out['generation_count']==4
    assert out['total_hypotheses_evaluated']==2572
    assert out['reopen_rule']=='NEW_INFORMATION_SET_ID_REQUIRED'


def test_domain_cannot_close_if_even_one_candidate_survives():
    gens=[{'generation_id':'G1','hypotheses':100,'admissible_candidates':1,'dataset_sha256':'sha'}]
    with pytest.raises(ValueError, match='domain_has_admissible_candidates'):
        m.close_search_domain(domain_id='D',information_set_id='I',dataset_sha256='sha',generations=gens)


def test_domain_rejects_mixed_dataset_hashes():
    gens=[{'generation_id':'G1','hypotheses':100,'admissible_candidates':0,'dataset_sha256':'other'}]
    with pytest.raises(ValueError, match='generation_dataset_sha_mismatch'):
        m.close_search_domain(domain_id='D',information_set_id='I',dataset_sha256='sha',generations=gens)
