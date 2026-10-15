import pytest
from core.session_chop_circuit_breaker import SessionChopCircuitBreaker

def test_initial_state_permitted():
    cb = SessionChopCircuitBreaker(max_consecutive_losses=2)
    ok, reason = cb.evaluate_entry_permission("2026-10-14")
    assert ok is True
    assert reason == "PERMITTED"

def test_trip_on_two_consecutive_losses():
    cb = SessionChopCircuitBreaker(max_consecutive_losses=2)
    date = "2026-10-14"
    
    cb.record_trade_exit(date, 4.75, "RUNNER_HWM_TRAILING_EXIT")
    assert cb.evaluate_entry_permission(date)[0] is True
    
    cb.record_trade_exit(date, 2.55, "TRAILING_STOP_HIT")
    assert cb.evaluate_entry_permission(date)[0] is True
    
    cb.record_trade_exit(date, -0.85, "STOP_LOSS_HIT")
    assert cb.evaluate_entry_permission(date)[0] is True
    
    cb.record_trade_exit(date, -34.60, "OPTION_NATIVE_STOP_LOSS_HIT")
    ok, reason = cb.evaluate_entry_permission(date)
    assert ok is False
    assert reason == "BLOCKED_BY_CHOP_CIRCUIT_BREAKER"

def test_state_persistence_and_recovery():
    cb = SessionChopCircuitBreaker(max_consecutive_losses=2)
    date = "2026-10-14"
    cb.record_trade_exit(date, -5.0, "STOP_LOSS_HIT")
    cb.record_trade_exit(date, -10.0, "STOP_LOSS_HIT")
    assert cb.evaluate_entry_permission(date)[0] is False
    
    # Snapshot to dict (WAL serialization)
    state = cb.to_dict()
    
    # Reconstruct in a new instance (Crash recovery)
    recovered_cb = SessionChopCircuitBreaker.from_dict(state)
    ok, reason = recovered_cb.evaluate_entry_permission(date)
    assert ok is False
    assert reason == "BLOCKED_BY_CHOP_CIRCUIT_BREAKER"
    assert recovered_cb.consecutive_losses == 2

def test_date_transition_resets_breaker():
    cb = SessionChopCircuitBreaker(max_consecutive_losses=2)
    cb.record_trade_exit("2026-10-14", -5.0, "STOP_LOSS_HIT")
    cb.record_trade_exit("2026-10-14", -10.0, "STOP_LOSS_HIT")
    assert cb.evaluate_entry_permission("2026-10-14")[0] is False
    
    # Next day
    ok, reason = cb.evaluate_entry_permission("2026-10-15")
    assert ok is True
    assert reason == "PERMITTED"
    assert cb.consecutive_losses == 0

def test_deterministic_replay_produces_identical_results():
    seq = [
        ("2026-10-14", 4.75, "WIN"),
        ("2026-10-14", -1.0, "STOP_LOSS_HIT"),
        ("2026-10-14", 2.0, "WIN"),
        ("2026-10-14", -5.0, "STOP_LOSS_HIT"),
        ("2026-10-14", -10.0, "STOP_LOSS_HIT"),
        ("2026-10-14", 15.0, "TARGET_HIT"),
    ]
    
    cb1 = SessionChopCircuitBreaker(max_consecutive_losses=2)
    cb2 = SessionChopCircuitBreaker(max_consecutive_losses=2)
    
    results1 = []
    results2 = []
    
    for d, pnl, rsn in seq:
        ok1, _ = cb1.evaluate_entry_permission(d)
        cb1.record_trade_exit(d, pnl, rsn)
        results1.append(ok1)
        
        ok2, _ = cb2.evaluate_entry_permission(d)
        cb2.record_trade_exit(d, pnl, rsn)
        results2.append(ok2)
        
    assert results1 == results2
    assert results1 == [True, True, True, True, True, False]
