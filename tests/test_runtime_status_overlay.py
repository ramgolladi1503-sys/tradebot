import pytest
from core.runtime_status_overlay import classify_runtime_feed_health, derive_effective_ws_connected

def test_classify_runtime_feed_health_ok():
    payload = {
        "ts_epoch": 1000.0,
        "runtime_state": "HEALTHY",
        "ws_connected": True,
        "effective_ws_connected": True,
        "market_open": True,
        "last_tick_age_sec": 1.0,
        "feed_ok_hysteresis_state": {"feed_ok": True},
    }
    decision = classify_runtime_feed_health(payload)
    assert decision.feed_ok is True

def test_classify_runtime_feed_health_startup_grace():
    payload = {
        "ts_epoch": 1000.0,
        "start_epoch": 990.0,
        "runtime_state": "BOOTING",
        "ws_connected": True,
        "effective_ws_connected": True,
        "market_open": True,
        "last_tick_age_sec": 6.0,
        "feed_ok_hysteresis_state": {"feed_ok": False},
    }
    decision = classify_runtime_feed_health(payload)
    assert decision.feed_ok is False
    assert "runtime_state_unsafe" in decision.reasons

def test_derive_effective_ws_connected():
    payload = {
        "ws_connected": True,
        "state_machine": {"state": "HEALTHY"},
    }
    assert derive_effective_ws_connected(payload) is True

    payload = {
        "ws_connected": False,
    }
    assert derive_effective_ws_connected(payload) is False

def test_classify_invalid_payload():
    decision = classify_runtime_feed_health(None)
    assert decision.feed_ok is False
    assert "invalid_payload" in decision.reasons
