import core.kite_depth_ws as ws


def test_silent_feed_triggers_reconnect_when_no_events(monkeypatch):
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    restart_calls = []
    state = {"confirm_hits": 0, "last_reconnect_epoch": 0.0}

    triggered = ws._maybe_trigger_silent_reconnect(
        now_epoch=10.5,
        current_tokens={256265, 991001},
        underlying_tokens={256265},
        last_global_msg_epoch=7.0,
        last_msg_by_token={256265: 7.0, 991001: 7.0},
        state=state,
        index_threshold_sec=1.5,
        option_threshold_sec=3.0,
        confirm_needed=1,
        backoff_min_sec=1.0,
        backoff_max_sec=10.0,
        force_full_restart_after_sec=12.0,
        restart_cb=lambda **kwargs: restart_calls.append(kwargs) or True,
    )

    assert triggered is True
    assert len(restart_calls) == 1
    assert "silent_feed" in str(restart_calls[0].get("reason", ""))
    assert state["last_reconnect_epoch"] == 10.5
    assert restart_calls[0]["force_full_restart"] is False


def test_silent_feed_escalates_to_full_restart_after_age_threshold(monkeypatch):
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    restart_calls = []
    state = {"confirm_hits": 0, "last_reconnect_epoch": 0.0}

    triggered = ws._maybe_trigger_silent_reconnect(
        now_epoch=20.5,
        current_tokens={256265, 991001},
        underlying_tokens={256265},
        last_global_msg_epoch=7.0,
        last_msg_by_token={256265: 7.0, 991001: 7.0},
        state=state,
        index_threshold_sec=1.5,
        option_threshold_sec=3.0,
        confirm_needed=1,
        backoff_min_sec=1.0,
        backoff_max_sec=10.0,
        force_full_restart_after_sec=12.0,
        restart_cb=lambda **kwargs: restart_calls.append(kwargs) or True,
    )

    assert triggered is True
    assert len(restart_calls) == 1
    assert restart_calls[0]["force_full_restart"] is True
    assert "silent_feed" in str(restart_calls[0].get("reason", ""))


def test_delayed_but_within_threshold_does_not_reconnect(monkeypatch):
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    restart_calls = []
    state = {"confirm_hits": 0, "last_reconnect_epoch": 0.0}

    triggered = ws._maybe_trigger_silent_reconnect(
        now_epoch=10.0,
        current_tokens={256265, 991001},
        underlying_tokens={256265},
        last_global_msg_epoch=9.2,
        last_msg_by_token={256265: 9.2, 991001: 9.2},
        state=state,
        index_threshold_sec=1.5,
        option_threshold_sec=3.0,
        confirm_needed=1,
        backoff_min_sec=1.0,
        backoff_max_sec=10.0,
        restart_cb=lambda **kwargs: restart_calls.append(kwargs) or True,
    )

    assert triggered is False
    assert restart_calls == []


def test_watchdog_log_throttle_suppresses_identical_repeats(monkeypatch):
    monkeypatch.setattr(ws, "_WS_LOG_LAST_EMIT", {}, raising=False)

    first = ws._should_throttle_ws_event("FEED_WARMUP_WAIT", now_epoch=100.0, cooldown_sec=5.0)
    second = ws._should_throttle_ws_event("FEED_WARMUP_WAIT", now_epoch=102.0, cooldown_sec=5.0)
    third = ws._should_throttle_ws_event("FEED_WARMUP_WAIT", now_epoch=106.0, cooldown_sec=5.0)

    assert first is False
    assert second is True
    assert third is False
