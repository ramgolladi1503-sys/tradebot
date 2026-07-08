from core.feed_state_model import FeedSnapshot, FeedLifecycleState, FeedOperationalState, FeedHysteresisState
from core.feed_state_engine import classify_feed_snapshot
import pytest
from unittest import mock

def _make_snapshot(**kwargs):
    h_state = kwargs.get("feed_ok_hysteresis_state")
    if h_state is not None:
        if isinstance(h_state, bool):
            kwargs["feed_ok_hysteresis_state"] = FeedHysteresisState(
                consecutive_good=3 if h_state else 0,
                consecutive_bad=0 if h_state else 3,
                feed_ok=h_state
            )
    defaults = {
        "ts_epoch": 1000.0,
        "start_epoch": 990.0,
        "runtime_state": "LIVE",
        "ws_connected": True,
        "effective_ws_connected": True,
        "market_open": True,
        "last_tick_age_sec": 1.0,
        "last_depth_age_sec": 1.0,
        "latest_ltp_age_sec": 1.0,
        "latest_option_tick_age_sec": 1.0,
        "subscribed_tokens_count": 10,
        "subscribed_option_tokens_count": 5,
        "missing_option_tokens_count": 0,
        "process_restart_required": False,
        "recovery_blocked": False,
        "recovery_state": "NONE",
        "feed_error_code": "",
        "feed_error_reason": "",
        "feed_ok_hysteresis_state": FeedHysteresisState(consecutive_good=3, consecutive_bad=0, feed_ok=True),
    }
    defaults.update(kwargs)
    return FeedSnapshot(**defaults)

def test_live_processing_ok():
    snapshot = _make_snapshot()
    verdict = classify_feed_snapshot(snapshot)
    assert verdict.lifecycle_state == FeedLifecycleState.LIVE
    assert verdict.operational_state == FeedOperationalState.LIVE
    assert verdict.feed_ok is True
    assert verdict.restart_required is False

def test_startup_grace():
    # BOOTING, start_epoch within 30s grace
    snapshot = _make_snapshot(
        runtime_state="BOOTING",
        ts_epoch=1000.0,
        start_epoch=980.0,
        feed_ok_hysteresis_state=False
    )
    with mock.patch("core.feed_state_engine._get_grace_sec", return_value=30.0):
        verdict = classify_feed_snapshot(snapshot)
        assert verdict.lifecycle_state == FeedLifecycleState.STARTING
        assert verdict.operational_state == FeedOperationalState.STARTING
        assert verdict.feed_ok is False
        assert verdict.restart_required is False
        assert "STARTUP" in verdict.reason_code

def test_missing_start_epoch_startup_grace():
    # Missing start_epoch should default age to 0, remaining in grace
    snapshot = _make_snapshot(
        runtime_state="BOOTING",
        ts_epoch=1000.0,
        start_epoch=None,
        feed_ok_hysteresis_state=False
    )
    with mock.patch("core.feed_state_engine._get_grace_sec", return_value=30.0):
        verdict = classify_feed_snapshot(snapshot)
        assert verdict.lifecycle_state == FeedLifecycleState.STARTING
        assert verdict.operational_state == FeedOperationalState.STARTING
        assert verdict.feed_ok is False
        assert verdict.restart_required is False

def test_startup_grace_expired():
    # BOOTING, but age > grace
    snapshot = _make_snapshot(
        runtime_state="BOOTING",
        ts_epoch=1000.0,
        start_epoch=950.0,
        feed_ok_hysteresis_state=False
    )
    with mock.patch("core.feed_state_engine._get_grace_sec", return_value=30.0):
        verdict = classify_feed_snapshot(snapshot)
        assert verdict.lifecycle_state == FeedLifecycleState.DEGRADED
        assert verdict.operational_state == FeedOperationalState.STARTING
        assert verdict.feed_ok is False
        assert verdict.restart_required is False
        assert "grace_expired" in verdict.blockers

def test_connected_but_silent():
    # ws_connected = True, but effective_ws_connected = False
    snapshot = _make_snapshot(
        ws_connected=True,
        effective_ws_connected=False,
        feed_ok_hysteresis_state=False
    )
    verdict = classify_feed_snapshot(snapshot)
    assert verdict.lifecycle_state == FeedLifecycleState.DEGRADED
    assert verdict.operational_state == FeedOperationalState.DEGRADED
    assert verdict.feed_ok is False
    assert verdict.restart_required is False
    assert "not_connected" in verdict.blockers

def test_process_restart_required_fatal():
    snapshot = _make_snapshot(process_restart_required=True)
    verdict = classify_feed_snapshot(snapshot)
    assert verdict.lifecycle_state == FeedLifecycleState.RESTART_REQUIRED
    assert verdict.operational_state == FeedOperationalState.DEAD
    assert verdict.feed_ok is False
    assert verdict.restart_required is True

def test_market_closed(monkeypatch):
    monkeypatch.setattr("core.feed_state_engine.market_feed_active", lambda: False)
    snapshot = _make_snapshot(market_open=False)
    verdict = classify_feed_snapshot(snapshot)
    assert verdict.lifecycle_state == FeedLifecycleState.MARKET_CLOSED
    assert verdict.feed_ok is False
    assert verdict.restart_required is False

def test_down_alone_is_non_fatal():
    snapshot = _make_snapshot(runtime_state="DOWN")
    verdict = classify_feed_snapshot(snapshot)
    assert verdict.lifecycle_state == FeedLifecycleState.DEGRADED
    assert verdict.operational_state == FeedOperationalState.DEAD
    assert verdict.feed_ok is False
    assert verdict.restart_required is False

def test_recovering_state():
    snapshot = _make_snapshot(recovery_state="RECOVERING")
    verdict = classify_feed_snapshot(snapshot)
    assert verdict.lifecycle_state == FeedLifecycleState.RECOVERING
    assert verdict.operational_state == FeedOperationalState.DEGRADED
    assert verdict.feed_ok is False
    assert verdict.restart_required is False

def test_auth_blocked():
    snapshot = _make_snapshot(feed_error_code="AUTH_BLOCKED")
    verdict = classify_feed_snapshot(snapshot)
    assert verdict.lifecycle_state == FeedLifecycleState.AUTH_BLOCKED
    assert verdict.operational_state == FeedOperationalState.DEAD
    assert verdict.feed_ok is False
    assert verdict.restart_required is True
