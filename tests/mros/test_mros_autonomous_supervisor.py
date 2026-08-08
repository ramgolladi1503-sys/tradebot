from __future__ import annotations
import sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2];SCRIPTS=ROOT/"scripts"/"mros"
if str(SCRIPTS) not in sys.path:sys.path.insert(0,str(SCRIPTS))
from mros_autonomous_supervisor import parse_program_state,derive_phase,receipt_stats,single_instance,SupervisorError
from mros_autonomous_repair_executor import validate_scope,RepairError,MAX_REPAIR_GENERATIONS
from mros_autonomous_cycle import blocking_findings

def test_parse_program_state_and_runtime_boundary():
    s='''active_milestone: M1\nactive_work_package: WP001\nactive_sprint: S003\nprogram_status: ACTIVE\nactive_sprint_status: ANY\nauthority:\n  runtime_authority: NONE\n'''
    d=parse_program_state(s);assert d['active_milestone']=='M1';assert d['active_sprint']=='S003';assert d['runtime_authority']=='NONE'

def test_pending_calibration_waits_automatically():
    state={'active_milestone':'M1','active_sprint':'S003'}
    req=['x/requests/S003_CALIBRATION_R96.json','x/requests/S003_R004_R01.json'];rec={}
    assert derive_phase(state,req,rec)==('NATIVE_CALIBRATION_RUNNING','WAIT_AUTOMATICALLY')

def test_review_phase_waits_automatically():
    state={'active_milestone':'M1','active_sprint':'S003'};req=[f'x/requests/S003_R004_R{i:02}.json' for i in range(1,4)]
    rec={Path(x).name:{'job':{'state':'SUCCEEDED','exit_code':0}} for x in req[:2]}
    assert derive_phase(state,req,rec)==('REVIEW_RUNNING','WAIT_AUTOMATICALLY')

def test_audit_phase_waits_automatically():
    state={'active_milestone':'M1','active_sprint':'S003'};req=['x/requests/S003_A005_A01.json'];assert derive_phase(state,req,{})==('AUDIT_RUNNING','WAIT_AUTOMATICALLY')

def test_no_pending_work_routes_to_cycle_not_human():
    state={'active_milestone':'M1','active_sprint':'S003'}
    assert derive_phase(state,[],{})==('AUTONOMOUS_S003_CYCLE','RUN_AUTONOMOUS_CYCLE')
    assert derive_phase({'active_milestone':'M1','active_sprint':'S004'},[],{})==('SPRINT_AUTOMATION','RUN_AUTONOMOUS_CYCLE')

def test_m9_is_hard_stop():
    assert derive_phase({'active_milestone':'M9','active_sprint':'S999'},[],{})==('HARD_STOP','M9_BOUNDARY_VIOLATION')

def test_receipt_stats_fail_closed():
    r={'a':{'job':{'state':'SUCCEEDED','exit_code':0}},'b':{'job':{'state':'FAILED','exit_code':1}},'c':{'_invalid':True}}
    assert receipt_stats(r)==(1,2)

def test_single_writer_lock(tmp_path:Path):
    lock=tmp_path/'supervisor.lock';h=single_instance(lock)
    try:
        with pytest.raises(SupervisorError,match='SUPERVISOR_ALREADY_RUNNING'):single_instance(lock)
    finally:
        import fcntl;fcntl.flock(h.fileno(),fcntl.LOCK_UN);h.close()

def test_repair_executor_scope_is_governance_only():
    validate_scope(['scripts/mros/advance_program.py','tests/mros/test_advance_program.py'])
    with pytest.raises(RepairError,match='REPAIR_FORBIDDEN_PATH'):
        validate_scope(['research/program/MROS_PROGRAM_STATE.yaml'])
    with pytest.raises(RepairError,match='REPAIR_PATH_NOT_ALLOWLISTED'):
        validate_scope(['core/order_router.py'])
    assert MAX_REPAIR_GENERATIONS==5

def test_blocking_findings_include_invalid_artifact_findings():
    f={'severity':'MAJOR','requirement':'bind receipt path','evidence':'x'}
    aggregate={'reviews':[],'invalid':[{'review':{'findings':[f]}}]}
    assert blocking_findings(aggregate,'review')==[f]
