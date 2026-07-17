import pytest
from datetime import date
import pandas as pd
from research.opening_state_momentum.partition import PartitionGuard
from research.opening_state_momentum.outcome import OutcomeEngine, HoldoutLockedError

@pytest.fixture
def holdout_dates():
    return ["2024-07-10", "2024-07-11"]

@pytest.fixture
def dev_dates():
    return ["2024-07-01", "2024-07-02"]

@pytest.fixture
def guard(holdout_dates):
    return PartitionGuard(holdout_dates)

@pytest.fixture
def engine(guard):
    return OutcomeEngine(guard)

def test_direct_single_session_holdout(engine):
    with pytest.raises(HoldoutLockedError, match="HOLDOUT_LOCKED"):
        engine.evaluate_session("2024-07-10")

def test_batch_only_holdout(engine):
    with pytest.raises(HoldoutLockedError, match="HOLDOUT_LOCKED"):
        engine.evaluate_batch(["2024-07-10", "2024-07-11"])
        
def test_mixed_batch(engine, dev_dates, holdout_dates):
    with pytest.raises(HoldoutLockedError, match="HOLDOUT_LOCKED"):
        engine.evaluate_batch(dev_dates + holdout_dates)

def test_holdout_date_formats(engine):
    with pytest.raises(HoldoutLockedError, match="HOLDOUT_LOCKED"):
        engine.evaluate_session("2024-07-10") # string
    with pytest.raises(HoldoutLockedError, match="HOLDOUT_LOCKED"):
        engine.evaluate_session(date(2024, 7, 10)) # date
    with pytest.raises(HoldoutLockedError, match="HOLDOUT_LOCKED"):
        engine.evaluate_session(pd.Timestamp("2024-07-10")) # timestamp

def test_reordered_holdout_list(guard):
    # Testing that order doesn't matter for the guard
    engine2 = OutcomeEngine(PartitionGuard(["2024-07-11", "2024-07-10"]))
    with pytest.raises(HoldoutLockedError, match="HOLDOUT_LOCKED"):
        engine2.evaluate_session("2024-07-10")

def test_lower_level_outcome_helper(guard):
    with pytest.raises(Exception, match=".*"):
        guard.check_access("2024-07-10", "evaluate_outcome")
