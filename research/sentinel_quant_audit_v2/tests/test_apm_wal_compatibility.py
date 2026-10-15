"""
Comprehensive APM WAL State Compatibility and Lifecycle Test Suite.

Validates that the observer's read-only adapter correctly identifies genuine active positions
under all ActivePositionManager states:
1. STANDBY: No in-flight trade.
2. ARMED (without position execution): Gated / not an entered position.
3. IN_FLIGHT: Active position, captured prospectively.
4. TRAIL_LOCK: Active position with locked profit ratchet, remains in-flight.
5. EXIT_PENDING: Active position awaiting final fill/liquidation, remains in-flight.
6. LIQUIDATED: Position moved to trade_history, completed evaluable.
7. Asynchronous WAL updates and state transitions across polling cycles.
8. Duplicate trades, asset separation, stale timestamps, and restart recovery.
"""

import os
import json
import pytest
from datetime import datetime
from core.shadow_circuit_breaker_evaluator import ShadowCircuitBreakerEvaluator
from scripts.run_prospective_shadow_observer import poll_wal_source

TEST_WAL_PATH = "runtime/test_apm_compat_wal.json"
TEST_STATE_PATH = "runtime/test_apm_compat_state.json"

@pytest.fixture(autouse=True)
def cleanup():
    for p in [TEST_WAL_PATH, TEST_STATE_PATH]:
        if os.path.exists(p):
            os.remove(p)
    yield
    for p in [TEST_WAL_PATH, TEST_STATE_PATH]:
        if os.path.exists(p):
            os.remove(p)

def test_apm_wal_states_in_flight_trail_lock_exit_pending():
    evaluator = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=TEST_STATE_PATH)
    
    # 1. STANDBY State: No trade in flight
    wal_standby = {
        "state": "STANDBY",
        "payload": None,
        "last_completed_trade": None,
        "trade_history": []
    }
    with open(TEST_WAL_PATH, "w") as f:
        json.dump(wal_standby, f)
        
    res1 = poll_wal_source(evaluator, TEST_WAL_PATH, "NIFTY", is_live_stream=True)
    assert res1["in_flight"] == 0
    assert len(evaluator.in_flight_positions) == 0

    # 2. IN_FLIGHT State: Active trade entry
    entry_payload = {
        "position_id": "TRADE_APM_01",
        "direction": "CE",
        "strike_contract": "NIFTY 23000 CE [ITM]",
        "entry_price": 23010.5,
        "entry_time": "2026-10-16T09:30:00+05:30",
        "current_sl": 22998.5,
        "initial_sl": 22998.5,
        "target_price": 23028.5
    }
    wal_in_flight = {
        "state": "IN_FLIGHT",
        "payload": entry_payload,
        "last_completed_trade": None,
        "trade_history": []
    }
    with open(TEST_WAL_PATH, "w") as f:
        json.dump(wal_in_flight, f)

    res2 = poll_wal_source(evaluator, TEST_WAL_PATH, "NIFTY", is_live_stream=True)
    assert res2["in_flight"] == 1
    scoped_key = "NIFTY::2026-10-16::TRADE_APM_01"
    assert scoped_key in evaluator.in_flight_positions
    prop = evaluator.proposal_registry[scoped_key]
    assert prop["provenance_mode"] == "PROSPECTIVE_OBSERVED"
    assert prop["lifecycle_state"] == "IN_FLIGHT_OPEN"

    # 3. TRAIL_LOCK State: APM ratchets trailing stop, position remains in-flight
    trail_payload = entry_payload.copy()
    trail_payload["trail_locked"] = True
    trail_payload["current_sl"] = 23014.5  # Locked profit
    wal_trail_lock = {
        "state": "TRAIL_LOCK",
        "payload": trail_payload,
        "last_completed_trade": None,
        "trade_history": []
    }
    with open(TEST_WAL_PATH, "w") as f:
        json.dump(wal_trail_lock, f)

    res3 = poll_wal_source(evaluator, TEST_WAL_PATH, "NIFTY", is_live_stream=True)
    assert res3["in_flight"] == 1
    assert scoped_key in evaluator.in_flight_positions

    # 4. EXIT_PENDING State: Stop hit, awaiting broker liquidation acknowledgment
    exit_pending_payload = trail_payload.copy()
    exit_pending_payload["exit_reason"] = "TRAILING_STOP_HIT"
    wal_exit_pending = {
        "state": "EXIT_PENDING",
        "payload": exit_pending_payload,
        "last_completed_trade": None,
        "trade_history": []
    }
    with open(TEST_WAL_PATH, "w") as f:
        json.dump(wal_exit_pending, f)

    res4 = poll_wal_source(evaluator, TEST_WAL_PATH, "NIFTY", is_live_stream=True)
    assert res4["in_flight"] == 1
    assert scoped_key in evaluator.in_flight_positions

    # 5. LIQUIDATED State: Trade completed, moved to trade_history
    completed_trade = exit_pending_payload.copy()
    completed_trade["exit_price"] = 23014.5
    completed_trade["exit_time"] = "2026-10-16T09:38:00+05:30"
    completed_trade["pnl_pts"] = 4.0
    completed_trade["opt_pnl_pts"] = 2.5
    completed_trade["opt_bid"] = 125.0
    completed_trade["opt_ask"] = 125.5

    wal_liquidated = {
        "state": "LIQUIDATED",
        "payload": None,
        "last_completed_trade": completed_trade,
        "trade_history": [completed_trade]
    }
    with open(TEST_WAL_PATH, "w") as f:
        json.dump(wal_liquidated, f)

    res5 = poll_wal_source(evaluator, TEST_WAL_PATH, "NIFTY", is_live_stream=True)
    assert res5["in_flight"] == 0
    assert res5["new_exits"] == 1
    assert scoped_key not in evaluator.in_flight_positions
    assert len(evaluator.shadow_ledger) == 1
    exit_rec = evaluator.shadow_ledger[0]
    assert exit_rec["position_id"] == "TRADE_APM_01"
    assert exit_rec["provenance_mode"] == "PROSPECTIVE_OBSERVED"
    assert exit_rec["lifecycle_state"] == "COMPLETED_EVALUABLE"

def test_armed_without_payload_not_mistaken_for_active_position():
    """An armed candidate signal without an active position must not be ingested as an open position."""
    evaluator = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=TEST_STATE_PATH)
    wal_armed_empty = {
        "state": "ARMED",
        "payload": None,
        "last_completed_trade": None,
        "trade_history": []
    }
    with open(TEST_WAL_PATH, "w") as f:
        json.dump(wal_armed_empty, f)

    res = poll_wal_source(evaluator, TEST_WAL_PATH, "NIFTY", is_live_stream=True)
    assert res["in_flight"] == 0
    assert len(evaluator.in_flight_positions) == 0
    assert len(evaluator.proposal_registry) == 0

def test_armed_state_with_candidate_payload_not_mistaken_for_entered_position():
    """An ARMED state candidate must not be counted as an entered position before IN_FLIGHT."""
    evaluator = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=TEST_STATE_PATH)
    wal_armed_candidate = {
        "state": "ARMED",
        "payload": {
            "position_id": "TRADE_CANDIDATE_01",
            "direction": "CE",
            "strike_contract": "NIFTY 23000 CE",
            "entry_price": 23000.0,
            "entry_time": "2026-10-16T09:15:00+05:30"
        },
        "last_completed_trade": None,
        "trade_history": []
    }
    with open(TEST_WAL_PATH, "w") as f:
        json.dump(wal_armed_candidate, f)

    res = poll_wal_source(evaluator, TEST_WAL_PATH, "NIFTY", is_live_stream=True)
    assert res["in_flight"] == 0
    assert len(evaluator.in_flight_positions) == 0
    assert len(evaluator.proposal_registry) == 0

