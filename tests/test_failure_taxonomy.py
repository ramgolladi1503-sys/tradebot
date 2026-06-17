import pytest
from core.analytics.failure_taxonomy import classify_failure

def test_classify_failure_no_failure():
    outcome = {"outcome": "hit_target", "exec_feasible": True, "mfe_points": 20.0}
    assert classify_failure(outcome) == "no_failure"

def test_classify_failure_execution_failure():
    outcome = {"outcome": "hit_target", "exec_feasible": False, "mfe_points": 20.0}
    assert classify_failure(outcome) == "execution_failure"

def test_classify_failure_signal_failure_low_mfe():
    outcome = {"outcome": "hit_sl", "exec_feasible": True, "mfe_points": 5.0}
    assert classify_failure(outcome, volatility_mfe_threshold=10.0) == "signal_failure"

def test_classify_failure_volatility_failure_high_mfe():
    outcome = {"outcome": "hit_sl", "exec_feasible": True, "mfe_points": 15.0}
    assert classify_failure(outcome, volatility_mfe_threshold=10.0) == "volatility_failure"

def test_classify_failure_no_hit():
    outcome = {"outcome": "no_hit", "exec_feasible": True, "mfe_points": 2.0}
    assert classify_failure(outcome) == "signal_failure"
