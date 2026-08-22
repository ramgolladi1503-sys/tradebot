from tep.ci_service import CIReconciler
from tep.ci import CIClass
def test_wait_does_not_repair_or_spin_worker():
 states=iter([{'state':'pending'},{'state':'pending'},{'state':'success'}]);r=CIReconciler(lambda _:next(states),sleep=lambda _:None).wait_terminal('h',interval=0);assert r.classification==CIClass.PASS and r.polls==3
def test_baseline_failure_not_repairable():
 r=CIReconciler(lambda _:{'state':'failed','baseline_state':'failed'},sleep=lambda _:None).wait_terminal('h');assert r.classification==CIClass.BASELINE_FAILURE and not CIReconciler(None).repair_allowed(r)
