import pytest
from tep.authority import *
from tep.ci import *
from tep.merge_queue import *
from tep.migration import MigrationPlanner
from tep.live_observer import ReadOnlyObserver,LiveObserverError

def ctx(grants=frozenset()):return AuthorityContext('m','t','actor','fp',grants)
def test_unknown_capability_denied():assert not AuthorityEvaluator().evaluate('MAGIC',ctx({'MAGIC'})).allowed
def test_trading_default_denied():assert not AuthorityEvaluator().evaluate('ORDER_ACTION',ctx()).allowed
def test_authority_target_mismatch_rejected():
 d=AuthorityEvaluator().evaluate('PUSH_BRANCH',ctx({'PUSH_BRANCH'}))
 with pytest.raises(PermissionError):require_authority(d,'PUSH_BRANCH','other')
def test_pending_ci_worker_free():assert classify_ci(CIObservation('pending'))==CIClass.WAITING and not worker_required(CIClass.WAITING)
def test_baseline_failure_not_candidate():assert classify_ci(CIObservation('failed','failed'))==CIClass.BASELINE_FAILURE
def test_serial_merge_invalidates_all_after_main_change():
 q=SerialMergeQueue();q.admit(MergeCandidate(2,'h','m',True,True),'m');q.admit(MergeCandidate(1,'x','m',True,True),'m');assert q.next().pr==1;assert q.main_advanced('m2')==(1,2);assert q.next() is None
def test_stale_base_not_ready():assert not ready(MergeCandidate(1,'h','old',True,True),'new')
def test_readonly_observer_rejects_order_surface():
 class Bad:
  def place_order(self):pass
 with pytest.raises(LiveObserverError):ReadOnlyObserver(Bad())
def test_reuse_requires_rollback(tmp_path):
 p=tmp_path/'x';p.write_text('x')
 with pytest.raises(ValueError):MigrationPlanner().inspect(p,'REUSE_VERIFIED')
