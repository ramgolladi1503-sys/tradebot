import pytest
from core.feed_runtime import build_canonical_feed_truth_state
from core.recovery_state_machine import evaluate_feed_state, RecoveryState, is_fatal_state
from core.runtime_status_overlay import derive_feed_ok
from config import config as cfg
import time

def test_recovery_state_machine_starting():
    payload = {"runtime_state": "BOOTING", "ws_connected": False, "market_open": True}
    state = evaluate_feed_state(payload)
    assert state == RecoveryState.STARTING
    assert not is_fatal_state(state)

def test_feed_runtime_startup_grace_no_restart(monkeypatch):
    monkeypatch.setattr(cfg, "FEED_NO_PROGRESS_TIMEOUT_SEC", 15.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_STARTUP_GRACE_SEC", 30.0, raising=False)
    
    now = time.time()
    payload = {
        "ws_connected": True,
        "runtime_state": "BOOTING",
        "latest_ltp_age_sec": 20.0,  # > 15 timeout
        "max_ltp_age_sec": 15.0,
        "start_epoch": now - 10.0,  # inside 30s grace
        "updated_at_epoch": now,
        "feed_ok_hysteresis_state": {"consecutive_bad": 3, "consecutive_good": 0, "feed_ok": False}
    }
    
    state = build_canonical_feed_truth_state(payload)
    # Inside grace, it should not trigger a hard breach, but should emit startup_no_ticks
    assert state.process_restart_required is False
    assert state.reason_code == "startup_no_ticks"

def test_feed_runtime_no_progress_breach(monkeypatch):
    monkeypatch.setattr(cfg, "FEED_NO_PROGRESS_TIMEOUT_SEC", 15.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_OK_MIN_BAD_CYCLES", 3, raising=False)
    
    payload = {
        "ws_connected": True,
        "runtime_state": "HEALTHY",
        "latest_ltp_age_sec": 16.0,
        "max_ltp_age_sec": 10.0,
        "feed_ok_hysteresis_state": {"consecutive_bad": 3, "consecutive_good": 0, "feed_ok": False}
    }
    
    state = build_canonical_feed_truth_state(payload)
    assert state.process_restart_required is True
    assert state.reason_code == "freshness_hard_breach"

def test_feed_runtime_ws_drop_immediate_fail():
    payload = {
        "ws_connected": False,
        "runtime_state": "SUBSCRIBE_FAILED",
        "ws_error_code": 1006,
        "process_restart_required": True
    }
    state = build_canonical_feed_truth_state(payload)
    assert state.process_restart_required is True
    assert state.reason_code == "terminal_ws_drop"

def test_feed_runtime_startup_grace_missing_start_epoch(monkeypatch):
    monkeypatch.setattr(cfg, "FEED_NO_PROGRESS_TIMEOUT_SEC", 15.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_STARTUP_GRACE_SEC", 30.0, raising=False)
    
    payload = {
        "ws_connected": True,
        "runtime_state": "BOOTING",
        "latest_ltp_age_sec": 20.0,  # > 15 timeout
        "max_ltp_age_sec": 15.0,
        "feed_ok_hysteresis_state": {"consecutive_bad": 3, "consecutive_good": 0, "feed_ok": False}
    }
    
    state = build_canonical_feed_truth_state(payload)
    # Missing start_epoch means we don't expire grace immediately, we stay in grace.
    assert state.process_restart_required is False
    assert state.reason_code == "startup_no_ticks"

def test_recovery_state_machine_down_is_not_fatal():
    payload = {"state_machine": {"state": "DOWN", "reason": "no_ws_messages"}}
    state = evaluate_feed_state(payload)
    assert state == RecoveryState.DOWN
    # DOWN should not be fatal alone
    assert not is_fatal_state(state)

def test_recovery_state_machine_process_restart_is_fatal():
    payload = {"state_machine": {"state": "DOWN", "reason": "no_ws_messages"}, "process_restart_required": True}
    state = evaluate_feed_state(payload)
    # Process restart required should elevate it to FATAL
    assert state == RecoveryState.FATAL
    assert is_fatal_state(state)
