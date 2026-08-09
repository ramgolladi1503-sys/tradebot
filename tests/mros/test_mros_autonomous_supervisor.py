from __future__ import annotations
import sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2];SCRIPTS=ROOT/"scripts"/"mros"
if str(SCRIPTS) not in sys.path:sys.path.insert(0,str(SCRIPTS))
from mros_autonomous_supervisor import parse_program_state,derive_phase,receipt_stats,single_instance,SupervisorError,AUTHORITY_WT
from mros_autonomous_repair_executor import validate_scope,RepairError,MAX_REPAIR_GENERATIONS
from mros_autonomous_cycle import blocking_findings
from mros_program_catalog import sprint_spec,next_sprint,sprint_acceptance
import mros_autonomous_supervisor as supervisor
import mros_s003_autonomous_finalizer as finalizer
import mros_calibration_failure_repair as calibration_repair
import mros_post_bootstrap_cycle as post_cycle
import mros_post_bootstrap_cycle_v2 as post_cycle_v2
import mros_program_sprint_executor as sprint_executor
import mros_program_repair_executor as program_repair
import mros_program_native_validator as program_native

def test_supervisor_default_authority_checkout_is_dedicated_worktree():
    assert AUTHORITY_WT == Path('/Users/madhuram/.mros-agent-bridge/authority')
def test_clean_authority_checkout_fast_forwards_before_cycle(monkeypatch,tmp_path:Path):
    from types import SimpleNamespace
    calls=[]
    def fake_git(repo,*args,timeout=180,check=True):
        calls.append(args)
        if args==('status','--porcelain'):return SimpleNamespace(stdout='',stderr='',returncode=0)
        if args==('merge','--ff-only',f'origin/{supervisor.AUTHORITY_BRANCH}'):return SimpleNamespace(stdout='Already up to date.\n',stderr='',returncode=0)
        raise AssertionError(f'unexpected git call: {args}')
    monkeypatch.setattr(supervisor,'git',fake_git)
    assert supervisor.recover_authority_checkout(tmp_path,tmp_path) is None
    assert ('merge','--ff-only',f'origin/{supervisor.AUTHORITY_BRANCH}') in calls
def test_parse_program_state_and_runtime_boundary():
    s='''active_milestone: M1\nactive_work_package: WP001\nactive_sprint: S003\nprogram_status: ACTIVE\nactive_sprint_status: ANY\nauthority:\n  runtime_authority: NONE\n''';d=parse_program_state(s);assert d['active_milestone']=='M1';assert d['active_sprint']=='S003';assert d['runtime_authority']=='NONE'
def test_pending_calibration_waits_automatically():
    state={'active_milestone':'M1','active_sprint':'S003'};req=['x/requests/S003_CALIBRATION_R96.json','x/requests/S003_R004_R01.json'];assert derive_phase(state,req,{})==('NATIVE_CALIBRATION_RUNNING','WAIT_AUTOMATICALLY')
def test_review_and_audit_wait_automatically():
    state={'active_milestone':'M1','active_sprint':'S004'};assert derive_phase(state,['x/requests/S004_R001_R01.json'],{})==('REVIEW_RUNNING','WAIT_AUTOMATICALLY');assert derive_phase(state,['x/requests/S004_A001_A01.json'],{})==('AUDIT_RUNNING','WAIT_AUTOMATICALLY')
def test_authorization_routes_to_finalizer():
    state={'active_milestone':'M1','active_sprint':'S003','active_sprint_status':'BOARD_BOOTSTRAP_AUTHORIZATION_PENDING'};assert derive_phase(state,[],{})==('S003_AUTHORIZATION','FINALIZE_AUTOMATICALLY')
def test_no_pending_work_routes_to_correct_autonomous_cycle():
    assert derive_phase({'active_milestone':'M1','active_sprint':'S003'},[],{})==('AUTONOMOUS_S003_CYCLE','RUN_AUTONOMOUS_CYCLE');assert derive_phase({'active_milestone':'M1','active_sprint':'S004'},[],{})==('AUTONOMOUS_PROGRAM_CYCLE','RUN_AUTONOMOUS_CYCLE');assert derive_phase({'active_milestone':'M8','active_sprint':'S110'},[],{})==('AUTONOMOUS_PROGRAM_CYCLE','RUN_AUTONOMOUS_CYCLE')
def test_m9_and_completed_m8_are_hard_stops():
    assert derive_phase({'active_milestone':'M9','active_sprint':'S111'},[],{})==('HARD_STOP','M9_BOUNDARY_PRESERVED');assert derive_phase({'active_milestone':'M8','active_sprint':'S110','program_status':'M8_COMPLETE_M9_HARD_STOP'},[],{})==('HARD_STOP','M9_BOUNDARY_PRESERVED')
def test_receipt_stats_fail_closed():
    r={'a':{'job':{'state':'SUCCEEDED','exit_code':0}},'b':{'job':{'state':'FAILED','exit_code':1}},'c':{'_invalid':True}};assert receipt_stats(r)==(1,2)
def test_single_writer_lock(tmp_path:Path):
    lock=tmp_path/'supervisor.lock';h=single_instance(lock)
    try:
        with pytest.raises(SupervisorError,match='SUPERVISOR_ALREADY_RUNNING'):single_instance(lock)
    finally:
        import fcntl;fcntl.flock(h.fileno(),fcntl.LOCK_UN);h.close()
def test_repair_executor_scope_is_governance_only():
    validate_scope(['scripts/mros/advance_program.py','tests/mros/test_advance_program.py'])
    with pytest.raises(RepairError,match='REPAIR_FORBIDDEN_PATH'):validate_scope(['research/program/MROS_PROGRAM_STATE.yaml'])
    with pytest.raises(RepairError,match='REPAIR_PATH_NOT_ALLOWLISTED'):validate_scope(['core/order_router.py'])
    assert MAX_REPAIR_GENERATIONS==5
def test_blocking_findings_include_invalid_artifact_findings():
    f={'severity':'MAJOR','requirement':'bind receipt path','evidence':'x'};assert blocking_findings({'reviews':[],'invalid':[{'review':{'findings':[f]}}]},'review')==[f]
def test_program_catalog_boundaries_assurance_and_wp_acceptance():
    assert sprint_spec(4).phase=='VERIFICATION_CALIBRATION_INDEPENDENT_ATTACK';assert sprint_spec(30).assurance_tier=='FULL' and sprint_spec(30).milestone=='M1';assert sprint_spec(110).milestone=='M8' and sprint_spec(110).terminal_m8 and next_sprint(110) is None
    assert not any('Constitution can be applied' in x for x in sprint_acceptance(4));assert any('Constitution can be applied' in x for x in sprint_acceptance(5));assert any('milestone evidence manifest' in x.lower() for x in sprint_acceptance(30))
    with pytest.raises(ValueError):sprint_spec(111)
def test_auxiliary_controller_modules_are_importable():
    assert callable(finalizer.finalize);assert callable(calibration_repair.main);assert callable(post_cycle.cycle);assert callable(post_cycle_v2.cycle);assert callable(sprint_executor.execute);assert callable(program_repair.execute);assert callable(program_native.validate)
