from __future__ import annotations
import json,sys,time
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2];SCRIPTS=ROOT/"scripts"/"mros"
if str(SCRIPTS) not in sys.path:sys.path.insert(0,str(SCRIPTS))
from mros_autonomous_supervisor import parse_program_state,derive_phase,receipt_stats,single_instance,SupervisorError

def test_parse_program_state_and_runtime_boundary():
    s='''active_milestone: M1\nactive_work_package: WP001\nactive_sprint: S003\nprogram_status: ACTIVE\nactive_sprint_status: BOARD_BOOTSTRAP_CALIBRATION_IN_PROGRESS\nauthority:\n  runtime_authority: NONE\n'''
    d=parse_program_state(s);assert d['active_milestone']=='M1';assert d['active_sprint']=='S003';assert d['runtime_authority']=='NONE'

def test_pending_calibration_beats_other_phases():
    state={'active_milestone':'M1','active_sprint':'S003'}
    req=['x/requests/S003_CALIBRATION_R96.json','x/requests/S003_BOARD_R01.json'];rec={}
    assert derive_phase(state,req,rec)==('BOOTSTRAP_CALIBRATION_RUNNING','WAIT_FOR_CALIBRATION_RECEIPT')

def test_review_phase_and_quorum_waiting():
    state={'active_milestone':'M1','active_sprint':'S003'};req=[f'x/requests/S003_BOARD_R{i:02}.json' for i in range(1,11)]
    rec={Path(x).name:{'job':{'state':'SUCCEEDED','exit_code':0}} for x in req[:9]}
    assert derive_phase(state,req,rec)==('BOOTSTRAP_REVIEW_RUNNING','WAIT_FOR_REVIEW_QUORUM')

def test_audit_phase():
    state={'active_milestone':'M1','active_sprint':'S003'};req=['x/requests/S003_BOARD_A01.json'];assert derive_phase(state,req,{})==('BOOTSTRAP_AUDIT_RUNNING','WAIT_FOR_AUDIT_QUORUM')

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
