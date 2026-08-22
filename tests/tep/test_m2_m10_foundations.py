from datetime import datetime
from pathlib import Path
import hashlib
import pytest
from tep.kernel import *
from tep.state import StateStore,StateConflict,LeaseConflict
from tep.authority import *
from tep.ci import *
from tep.evidence import *
from tep.missions import *
from tep.live import *
from tep.research import *
from tep.migration import *

def store(tmp_path): return StateStore(tmp_path/'tep.db')

def test_atomic_transition_and_event(tmp_path):
    s=store(tmp_path);s.create_mission('m','h');s.create_task('ti','m','t','fp')
    e=EventRecord('e','k','transition','ti',(),{'to':'RUNNABLE'})
    s.transition_task('ti',TaskState.RUNNABLE,e)
    snap=s.snapshot();assert snap['tasks'][0]['state']=='RUNNABLE';assert len(snap['events'])==1

def test_failed_transition_does_not_append_event(tmp_path):
    s=store(tmp_path);s.create_mission('m','h');s.create_task('ti','m','t','fp')
    with pytest.raises(ValueError):s.transition_task('ti',TaskState.SUCCEEDED,EventRecord('e','k','bad','ti'))
    assert s.snapshot()['events']==[]

def test_event_idempotency_and_collision(tmp_path):
    s=store(tmp_path);e=EventRecord('e','k','x','s');s.append_event(e);s.append_event(e)
    assert len(s.snapshot()['events'])==1
    with pytest.raises(StateConflict):s.append_event(EventRecord('different','k','x','s'))

def test_lease_conflict_expiry_and_recovery(tmp_path):
    s=store(tmp_path);s.acquire_lease('t','a','fp',10,now=100)
    with pytest.raises(LeaseConflict):s.acquire_lease('t','b','fp',10,now=101)
    s.acquire_lease('t','b','fp',10,now=111)

def test_optimistic_version_rejects_stale(tmp_path):
    s=store(tmp_path);s.create_mission('m','h');s.create_task('ti','m','t','fp')
    s.transition_task('ti',TaskState.RUNNABLE,EventRecord('e1','k1','x','ti'),expected_version=0)
    with pytest.raises(StateConflict):s.transition_task('ti',TaskState.LEASED,EventRecord('e2','k2','x','ti'),expected_version=0)

def ctx(grants=frozenset()):return AuthorityContext('m','t','worker','sha',grants)
def test_authority_fail_closed_and_capability_independence():
    a=AuthorityEvaluator();assert not a.evaluate('MERGE_PR',ctx()).allowed
    assert a.evaluate('PUSH_BRANCH',ctx(frozenset({'PUSH_BRANCH'}))).allowed
    assert not a.evaluate('MERGE_PR',ctx(frozenset({'PUSH_BRANCH'}))).allowed
    assert not a.evaluate('ORDER_ACTION',ctx(frozenset({'LIVE_EXECUTION'}))).allowed
    assert not a.evaluate('INVENTED_CAPABILITY',ctx(frozenset({'INVENTED_CAPABILITY'}))).allowed

def test_stale_authority_rejected():
    d=AuthorityEvaluator().evaluate('PUSH_BRANCH',ctx(frozenset({'PUSH_BRANCH'})))
    with pytest.raises(PermissionError):require_authority(d,'PUSH_BRANCH','other-sha')

def test_execution_envelope_protected_and_scope(tmp_path):
    allowed=tmp_path/'allowed';blocked=allowed/'sealed';allowed.mkdir();blocked.mkdir()
    e=ExecutionEnvelope('t','fp','PUSH_BRANCH','w',(str(allowed),),(str(blocked),))
    e.validate_path(str(allowed/'x'))
    with pytest.raises(PermissionError):e.validate_path(str(blocked/'x'))
    with pytest.raises(PermissionError):e.validate_path('/tmp/outside')

def test_ci_wait_is_worker_free_and_failures_classified():
    assert classify_ci(CIObservation('queued')) is CIClass.WAITING
    assert not worker_required(CIClass.WAITING)
    assert classify_ci(CIObservation('failed','failed')) is CIClass.BASELINE_FAILURE
    assert classify_ci(CIObservation('failed','success')) is CIClass.CANDIDATE_FAILURE
    assert classify_ci(CIObservation('failed',external=True)) is CIClass.EXTERNAL_FAILURE

def test_evidence_requires_independent_validator_and_hash():
    idx=EvidenceIndex();b=b'abc';h=hashlib.sha256(b).hexdigest()
    r=EvidenceRecord('e','claim','producer','validator','source','ref',h);idx.seal(r,b)
    with pytest.raises(EvidenceError):idx.seal(EvidenceRecord('x','c','same','same','s','r',h),b)
    with pytest.raises(EvidenceError):idx.seal(EvidenceRecord('y','c','p','v','s','r','bad'),b)

def test_relationship_requires_governed_verdict():
    Relationship('1','2','PARTIAL_OVERLAP',())
    with pytest.raises(ValueError):Relationship('1','2','looks similar',())

def test_blocker_router_does_not_escalate_ordinary_repair_to_human():
    r=BlockerRouter();assert r.route('CONFLICT')=='REPAIR';assert r.route('CI_WAIT')=='WAIT';assert r.route('TRUE_HUMAN_APPROVAL_REQUIRED')=='HUMAN'

def test_reference_missions_validate_and_do_not_grant_authority():
    for m in (repository_consolidation_mission(),read_only_live_observation_mission(),structural_edge_research_mission()):validate_mission(m)
    assert 'ORDER_ACTION' not in {t.capability for t in read_only_live_observation_mission().tasks}

def test_dynamic_subscription_union_not_hardcoded():
    p=LaunchPlan('2026-08-22','abcdef123',(1,2,3),(3,4),'/tmp/runtime');p.validate();assert p.union_tokens==(1,2,3,4);assert p.overlap_tokens==(3,)

def test_durability_rejects_produce_caveat_not_causal_claim():
    d=DurabilityCounters(rejected_depth=41466,rejected_runtime=29352);assert d.degraded;assert d.verdict()=='SEALED_WITH_DURABILITY_CAVEATS'

def test_research_certification_separates_historical_and_prospective():
    h=ResearchGate(True,True,True,True,True,True,False);assert h.historical_supported();assert not h.structural_certified()
    assert ResearchGate(True,True,True,True,True,True,True).structural_certified()

def test_search_pressure_records_failures():
    l=SearchPressureLedger();l.record('trend','FAIL','h1');l.record('mean_reversion','PASS','h2');assert l.selection_pressure=={'trials':2,'families':2};assert l.failures==['h1']

def test_migration_unknown_never_becomes_safe_delete():
    c=MigrationCandidate('old',None,None,(),False);d=classify(c);assert d is MigrationDisposition.UNKNOWN_PROVENANCE;assert not deletion_allowed(d,True)
