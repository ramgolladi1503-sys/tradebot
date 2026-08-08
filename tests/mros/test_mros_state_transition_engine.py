from __future__ import annotations
import subprocess,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2];SCRIPTS=ROOT/'scripts'/'mros'
if str(SCRIPTS) not in sys.path:sys.path.insert(0,str(SCRIPTS))
from mros_state_transition_engine import _check_path,_check_boundary,writer_lock,TransitionError

def test_path_allowlist():
    _check_path('research/program/MROS_PROGRAM_STATE.yaml')
    _check_path('research/evidence/sprints/S003/x.md')
    with pytest.raises(TransitionError,match='PATH_NOT_ALLOWLISTED'):_check_path('core/runtime.py')
    with pytest.raises(TransitionError,match='INVALID_PATH'):_check_path('../x')

def test_m9_and_runtime_boundary(tmp_path:Path):
    p=tmp_path/'state.yaml';p.write_text('active_milestone: M9\nruntime_authority: NONE\n')
    with pytest.raises(TransitionError,match='M9_OR_RUNTIME_BOUNDARY_VIOLATION'):_check_boundary(p)
    p.write_text('active_milestone: M1\nruntime_authority: LIVE\n')
    with pytest.raises(TransitionError,match='M9_OR_RUNTIME_BOUNDARY_VIOLATION'):_check_boundary(p)

def test_writer_lock_excludes_second_writer(tmp_path:Path):
    lp=tmp_path/'lock'
    with writer_lock(lp):
        with pytest.raises(TransitionError,match='ANOTHER_SUPERVISOR_HOLDS_WRITER_LOCK'):
            with writer_lock(lp):pass
