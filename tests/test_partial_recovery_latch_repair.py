from __future__ import annotations

import core.kite_depth_ws as ws


def _reset_state(monkeypatch):
    monkeypatch.setattr(ws, "_RECONNECT_BLOCKED_REASON", "", raising=False)
    monkeypatch.setattr(ws, "_RECONNECT_BLOCKED_SINCE_EPOCH", 0.0, raising=False)
    monkeypatch.setattr(ws, "_REACTOR_NOT_RESTARTABLE_DETECTED", False, raising=False)
    monkeypatch.setattr(ws, "_RUNTIME_STATE", "DEGRADED_LOCAL", raising=False)
    monkeypatch.setattr(ws, "_LAST_RUNTIME_ERROR", "partial_recovery", raising=False)
    monkeypatch.setattr(ws, "_PARTIAL_RECOVERY_VERIFICATION", {}, raising=False)
    monkeypatch.setattr(ws, "_SOCKET_GENERATION", 1, raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 100.0, raising=False)
    monkeypatch.setattr(ws, "_PENDING_SUBSCRIBE_TOKENS", set(), raising=False)
    monkeypatch.setattr(ws, "_PENDING_UNSUBSCRIBE_TOKENS", set(), raising=False)
    monkeypatch.setattr(ws, "_PENDING_MODE_FULL_TOKENS", set(), raising=False)
    monkeypatch.setattr(ws, "_RECOVERY_STABLE_CYCLES", 2, raising=False)
    monkeypatch.setattr(ws, "_CORE_FEED_FRESH_QUORUM", 0.5, raising=False)
    monkeypatch.setattr(ws, "_ws_connected_state", lambda: True)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)


def _run_partial(monkeypatch, state, last_by_token, now=100.0):
    return ws._maybe_trigger_silent_reconnect(
        now_epoch=now,
        current_tokens={101, 102, 103},
        underlying_tokens={101},
        last_global_msg_epoch=now,
        last_msg_by_token=last_by_token,
        state=state,
        index_threshold_sec=5.0,
        option_threshold_sec=5.0,
        confirm_needed=3,
        backoff_min_sec=1.0,
        backoff_max_sec=1.0,
        force_full_restart_after_sec=None,
        restart_cb=lambda **kwargs: (_ for _ in ()).throw(AssertionError("restart is unsafe here")),
    )


def test_partial_activity_does_not_latch_terminal_recovery(monkeypatch):
    _reset_state(monkeypatch)
    ws._set_reconnect_blocked_reason("partial_recovery")
    state = {"confirm_hits": 0, "last_reconnect_epoch": 0.0}

    _run_partial(monkeypatch, state, {101: 100.0, 102: 100.0, 103: 50.0})

    assert ws._RECONNECT_BLOCKED_REASON == ""
    assert ws._RUNTIME_STATE == "VERIFYING_RECOVERY"
    assert ws._LAST_RUNTIME_ERROR == "partial_activity_verification_pending"
    assert ws._reconnect_recovery_blocked_active() is False


def test_confirmed_reactor_failure_remains_terminal(monkeypatch):
    _reset_state(monkeypatch)
    ws._set_reconnect_blocked_reason("partial_recovery")
    monkeypatch.setattr(ws, "_REACTOR_NOT_RESTARTABLE_DETECTED", True, raising=False)
    state = {"confirm_hits": 0, "last_reconnect_epoch": 0.0}

    _run_partial(monkeypatch, state, {101: 100.0, 102: 100.0, 103: 50.0})

    assert ws._RECONNECT_BLOCKED_REASON == "partial_recovery"
    assert ws._reconnect_recovery_blocked_active() is True


def test_stable_fresh_batches_clear_error_and_recovery_latch(monkeypatch):
    _reset_state(monkeypatch)
    ws._set_reconnect_blocked_reason("partial_recovery")
    state = {"confirm_hits": 0, "last_reconnect_epoch": 0.0}
    full = {101: 100.0, 102: 100.0, 103: 100.0}

    _run_partial(monkeypatch, state, full)
    _run_partial(monkeypatch, state, full)

    assert ws._RUNTIME_STATE == "LIVE"
    assert ws._LAST_RUNTIME_ERROR == ""
    assert ws._RECONNECT_BLOCKED_REASON == ""
    assert ws._reconnect_recovery_blocked_active() is False
