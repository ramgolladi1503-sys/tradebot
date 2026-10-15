import pytest
import os
import json
from datetime import datetime, timezone, timedelta
from core.shadow_circuit_breaker_evaluator import ShadowCircuitBreakerEvaluator

TEST_LOG_PATH = "runtime/test_shadow_evaluator_v4_state.json"

@pytest.fixture(autouse=True)
def cleanup():
    if os.path.exists(TEST_LOG_PATH):
        os.remove(TEST_LOG_PATH)
    yield
    if os.path.exists(TEST_LOG_PATH):
        os.remove(TEST_LOG_PATH)

def test_unmatched_exit_quarantined_not_defaulted():
    evaluator = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=TEST_LOG_PATH)
    date = "2026-10-15"
    
    # An exit arrives with NO prior proposal
    exit_res = evaluator.observe_trade_exit(
        "GHOST_TRADE", "NIFTY", date, 10.0, 5.0, "TARGET_HIT", "2026-10-15T10:00:00+05:30"
    )
    
    assert exit_res["status"] == "UNMATCHED_EXIT_QUARANTINED"
    assert exit_res["reason"] == "MISSING_PRIOR_PROPOSAL_DECISION"
    assert len(evaluator.unmatched_exit_queue) == 1
    assert len(evaluator.shadow_ledger) == 0
    # Breaker state must NOT be mutated
    st = evaluator._get_state("NIFTY", date)
    assert st["total_completed_exits"] == 0

def test_timezone_aware_timestamp_validation():
    evaluator = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=TEST_LOG_PATH)
    
    # Valid ISO timestamp with offset +05:30
    p1 = evaluator.observe_trade_proposal("T1", "NIFTY", "2026-10-15", "CE", "C1", "2026-10-15T10:00:00+05:30")
    assert p1["shadow_decision"] == "PERMITTED"
    
    # Malformed timestamp
    p2 = evaluator.observe_trade_proposal("T2", "NIFTY", "2026-10-15", "CE", "C2", "2026-10-15 10:05 INVALID")
    assert p2["shadow_decision"] == "QUARANTINED"
    assert "MALFORMED_TIMESTAMP_FORMAT" in p2["quarantine_reason"]
    
    # Missing timestamp
    p3 = evaluator.observe_trade_proposal("T3", "NIFTY", "2026-10-15", "CE", "C3", "")
    assert p3["shadow_decision"] == "QUARANTINED"
    assert p3["quarantine_reason"] == "MISSING_TIMESTAMP"

def test_in_flight_position_lifecycle():
    evaluator = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=TEST_LOG_PATH)
    date = "2026-10-15"
    
    # 1. Proposal registered -> IN_FLIGHT_OPEN
    p = evaluator.observe_trade_proposal("T_OPEN", "NIFTY", date, "CE", "C1", "2026-10-15T10:00:00+05:30")
    assert p["lifecycle_state"] == "IN_FLIGHT_OPEN"
    scoped_key = evaluator._make_scoped_key("NIFTY", date, "T_OPEN")
    assert scoped_key in evaluator.in_flight_positions
    
    # 2. Re-load from persistence: in_flight_positions must survive restart
    reloaded = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=TEST_LOG_PATH)
    assert scoped_key in reloaded.in_flight_positions
    assert reloaded.in_flight_positions[scoped_key]["position_id"] == "T_OPEN"
    
    # 3. Exit observed -> Transitions from IN_FLIGHT_OPEN to COMPLETED_EVALUABLE
    e = reloaded.observe_trade_exit("T_OPEN", "NIFTY", date, 10.0, 5.0, "TARGET_HIT", "2026-10-15T10:15:00+05:30")
    assert e["lifecycle_state"] == "COMPLETED_EVALUABLE"
    assert scoped_key not in reloaded.in_flight_positions

def test_quote_depth_explicit_classification():
    evaluator = ShadowCircuitBreakerEvaluator(max_consecutive_losses=2, log_path=TEST_LOG_PATH)
    date = "2026-10-15"
    
    # Trade 1: Entry depth only -> ENTRY_DEPTH_ONLY_NON_EXECUTABLE_ESTIMATE
    evaluator.observe_trade_proposal("T1", "NIFTY", date, "CE", "C1", "2026-10-15T10:00:00+05:30")
    e1 = evaluator.observe_trade_exit(
        "T1", "NIFTY", date, 10.0, 5.0, "TARGET_HIT", "2026-10-15T10:05:00+05:30",
        opt_entry_bid=150.0, opt_entry_ask=150.4, opt_exit_bid=None, opt_exit_ask=None
    )
    assert e1["depth_coverage"] == "ENTRY_DEPTH_ONLY_NON_EXECUTABLE_ESTIMATE"
    
    # Trade 2: Depth completely missing -> DEPTH_MISSING_LTP_MODELED_ONLY
    evaluator.observe_trade_proposal("T2", "NIFTY", date, "CE", "C2", "2026-10-15T10:10:00+05:30")
    e2 = evaluator.observe_trade_exit(
        "T2", "NIFTY", date, 10.0, 5.0, "TARGET_HIT", "2026-10-15T10:15:00+05:30",
        opt_entry_bid=None, opt_entry_ask=None, opt_exit_bid=None, opt_exit_ask=None
    )
    assert e2["depth_coverage"] == "DEPTH_MISSING_LTP_MODELED_ONLY"
    
    # Trade 3: Full Bid/Ask on both sides -> FULL_BID_ASK_VERIFIED
    evaluator.observe_trade_proposal("T3", "NIFTY", date, "CE", "C3", "2026-10-15T10:20:00+05:30")
    e3 = evaluator.observe_trade_exit(
        "T3", "NIFTY", date, 10.0, 5.0, "TARGET_HIT", "2026-10-15T10:25:00+05:30",
        opt_entry_bid=150.0, opt_entry_ask=150.4, opt_exit_bid=155.0, opt_exit_ask=155.4
    )
    assert e3["depth_coverage"] == "FULL_BID_ASK_VERIFIED"
