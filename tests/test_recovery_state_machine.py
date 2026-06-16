import pytest
from core.recovery_state_machine import evaluate_feed_state, is_fatal_state, RecoveryState

def test_recovery_healthy():
    assert evaluate_feed_state({"runtime_state": "HEALTHY"}) == RecoveryState.HEALTHY
    assert evaluate_feed_state({"ws_lifecycle_state": "OPEN"}) == RecoveryState.HEALTHY

def test_websocket_drop_mid_trade():
    state = evaluate_feed_state({"ws_lifecycle_state": "DROPPED"})
    assert state == RecoveryState.WS_LOSS
    assert is_fatal_state(state) is False, "Mid-trade feed loss must be handled via background recovery, not orchestrator halt"

def test_ambiguous_restore_fails_closed():
    # If the payload is completely ambiguous or missing known states, it must fail closed
    state = evaluate_feed_state({"some_unknown_field": True})
    assert state == RecoveryState.FATAL
    assert is_fatal_state(state) is True

def test_fatal_feed_transitions():
    state = evaluate_feed_state({"runtime_state": "FEED_LIFECYCLE_FATAL"})
    assert state == RecoveryState.FATAL
    
    state = evaluate_feed_state({"recovery_blocked": True})
    assert state == RecoveryState.RECOVERY_BLOCKED
    assert is_fatal_state(state) is True
