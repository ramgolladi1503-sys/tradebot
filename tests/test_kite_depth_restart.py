import core.kite_depth_ws as ws
from config import config as cfg


def test_restart_skips_without_cached_tokens(monkeypatch):
    monkeypatch.setattr(ws, "_LAST_TOKENS", [], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", [], raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    calls = {"stop": 0, "start": 0, "persist": 0}
    monkeypatch.setattr(
        ws,
        "stop_depth_ws",
        lambda reason="manual_stop": calls.__setitem__("stop", calls["stop"] + 1),
    )
    monkeypatch.setattr(
        ws,
        "start_depth_ws",
        lambda tokens, profile_verified=False, **kwargs: calls.__setitem__("start", calls["start"] + 1),
    )
    monkeypatch.setattr(
        ws,
        "_persist_runtime_snapshot_row",
        lambda **kwargs: calls.__setitem__("persist", calls["persist"] + 1),
    )
    assert ws.restart_depth_ws(reason="unit_test_no_tokens") is False
    assert calls == {"stop": 0, "start": 0, "persist": 0}


def test_restart_skips_without_tokens_even_with_stale_ticker(monkeypatch):
    monkeypatch.setattr(ws, "_LAST_TOKENS", [], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", [], raising=False)
    monkeypatch.setattr(ws, "_KITE_TICKER", object(), raising=False)
    monkeypatch.setattr(cfg, "DEPTH_WS_USE_INTERNAL_RECONNECT", True, raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    calls = {"stop": 0, "start": 0, "persist": 0, "soft": 0}
    monkeypatch.setattr(
        ws,
        "stop_depth_ws",
        lambda reason="manual_stop": calls.__setitem__("stop", calls["stop"] + 1),
    )
    monkeypatch.setattr(
        ws,
        "start_depth_ws",
        lambda tokens, profile_verified=False, **kwargs: calls.__setitem__("start", calls["start"] + 1),
    )
    monkeypatch.setattr(
        ws,
        "_persist_runtime_snapshot_row",
        lambda **kwargs: calls.__setitem__("persist", calls["persist"] + 1),
    )
    monkeypatch.setattr(
        ws,
        "_soft_resubscribe_current",
        lambda reason: calls.__setitem__("soft", calls["soft"] + 1) or True,
    )

    assert ws.restart_depth_ws(reason="unit_test_no_tokens_stale_ticker") is False
    assert calls == {"stop": 0, "start": 0, "persist": 0, "soft": 0}


def test_stop_depth_ws_noop_without_ticker_or_watchdog(monkeypatch):
    monkeypatch.setattr(ws, "_KITE_TICKER", None, raising=False)
    monkeypatch.setattr(ws, "_WATCHDOG_THREAD", None, raising=False)
    monkeypatch.setattr(ws, "_WATCHDOG_STOP", None, raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    calls = {"persist": 0, "close": 0, "join_thread": 0, "join_ticker": 0}
    monkeypatch.setattr(
        ws,
        "_persist_runtime_snapshot_row",
        lambda **kwargs: calls.__setitem__("persist", calls["persist"] + 1),
    )
    monkeypatch.setattr(
        ws,
        "_close_ticker_instance",
        lambda ticker: calls.__setitem__("close", calls["close"] + 1),
    )
    monkeypatch.setattr(
        ws,
        "_join_thread_safe",
        lambda thread, timeout: calls.__setitem__("join_thread", calls["join_thread"] + 1),
    )
    monkeypatch.setattr(
        ws,
        "_join_ticker_threads",
        lambda ticker, timeout: calls.__setitem__("join_ticker", calls["join_ticker"] + 1),
    )

    ws.stop_depth_ws(reason="unit_test_noop")

    assert calls == {"persist": 0, "close": 0, "join_thread": 0, "join_ticker": 0}


def test_restart_respects_cooldown(monkeypatch):
    monkeypatch.setattr(ws, "_LAST_TOKENS", [123, 456], raising=False)
    monkeypatch.setattr(ws, "_FULL_RESTARTS", [], raising=False)
    monkeypatch.setattr(ws, "_LAST_FULL_RESTART_EPOCH", 0.0, raising=False)
    monkeypatch.setattr(ws, "_STALE_STRIKES", 0, raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws, "feed_breaker_tripped", lambda: False)
    monkeypatch.setattr(ws.feed_restart_guard, "allow_restart", lambda **kwargs: True)
    monkeypatch.setattr(cfg, "FEED_FULL_RESTART_COOLDOWN_SEC", 9999.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_MAX_FULL_RESTARTS_PER_HOUR", 6, raising=False)

    calls = {"start": 0, "stop": 0}

    def _start(tokens, profile_verified=False, **kwargs):
        calls["start"] += 1

    def _stop(reason="manual_stop"):
        calls["stop"] += 1

    monkeypatch.setattr(ws, "start_depth_ws", _start)
    monkeypatch.setattr(ws, "stop_depth_ws", _stop)

    assert ws.restart_depth_ws(reason="first") is True
    assert calls["start"] == 1
    assert calls["stop"] == 1

    # Immediate second restart should be blocked by cooldown.
    assert ws.restart_depth_ws(reason="second") is False
    assert calls["start"] == 1
    assert calls["stop"] == 1


def test_restart_ignore_cooldown_allows_immediate_restart(monkeypatch):
    monkeypatch.setattr(ws, "_LAST_TOKENS", [123, 456], raising=False)
    monkeypatch.setattr(ws, "_FULL_RESTARTS", [], raising=False)
    monkeypatch.setattr(ws, "_LAST_FULL_RESTART_EPOCH", 0.0, raising=False)
    monkeypatch.setattr(ws, "_STALE_STRIKES", 0, raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws, "feed_breaker_tripped", lambda: False)
    monkeypatch.setattr(ws.feed_restart_guard, "allow_restart", lambda **kwargs: True)
    monkeypatch.setattr(cfg, "FEED_FULL_RESTART_COOLDOWN_SEC", 9999.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_MAX_FULL_RESTARTS_PER_HOUR", 6, raising=False)

    calls = {"start": 0, "stop": 0}

    def _start(tokens, profile_verified=False, **kwargs):
        calls["start"] += 1

    def _stop(reason="manual_stop"):
        calls["stop"] += 1

    monkeypatch.setattr(ws, "start_depth_ws", _start)
    monkeypatch.setattr(ws, "stop_depth_ws", _stop)

    assert ws.restart_depth_ws(reason="first") is True
    assert ws.restart_depth_ws(reason="second_blocked") is False
    assert ws.restart_depth_ws(reason="third_ignored", ignore_cooldown=True) is True
    assert calls["start"] == 2
    assert calls["stop"] == 2


def test_ws_fault_1006_bypasses_restart_cooldown_policy():
    assert ws._should_ignore_restart_cooldown_for_ws_fault(code=1006, reason_text="") is True
    assert ws._should_ignore_restart_cooldown_for_ws_fault(code="1006", reason_text="") is True
    assert ws._should_ignore_restart_cooldown_for_ws_fault(code=1011, reason_text="") is False


def test_market_open_transition_resets_restart_guard(monkeypatch):
    calls = []
    monkeypatch.setattr(
        ws.feed_restart_guard,
        "reset",
        lambda reason="manual_reset": calls.append(reason),
    )

    state = ws._maybe_reset_restart_guard_on_market_open(
        market_open_now=False,
        market_was_open=None,
    )
    assert state is False
    assert calls == []

    state = ws._maybe_reset_restart_guard_on_market_open(
        market_open_now=True,
        market_was_open=None,
    )
    assert state is True
    assert calls == ["market_open_transition"]

    state = ws._maybe_reset_restart_guard_on_market_open(
        market_open_now=True,
        market_was_open=False,
    )
    assert state is True
    assert calls == ["market_open_transition", "market_open_transition"]


def test_restart_uses_soft_path_when_internal_reconnect_enabled(monkeypatch):
    monkeypatch.setattr(ws, "_LAST_TOKENS", [123, 456], raising=False)
    class _ConnectedTicker:
        def is_connected(self):
            return True

    monkeypatch.setattr(ws, "_KITE_TICKER", _ConnectedTicker(), raising=False)
    monkeypatch.setattr(ws, "_AUTH_REQUIRED_LATCH", False, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_WS_USE_INTERNAL_RECONNECT", True, raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 100.0, raising=False)
    monkeypatch.setattr(ws.time, "time", lambda: 101.0)

    calls = {"soft": 0}
    monkeypatch.setattr(
        ws,
        "_soft_resubscribe_current",
        lambda reason: calls.__setitem__("soft", calls["soft"] + 1) or True,
    )
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)

    assert ws.restart_depth_ws(reason="unit_soft_path") is True
    assert calls["soft"] == 1


def test_restart_skips_soft_path_when_ws_tick_is_stale_even_if_socket_connected(monkeypatch):
    monkeypatch.setattr(ws, "_LAST_TOKENS", [123, 456], raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 10.0, raising=False)
    monkeypatch.setattr(ws, "_AUTH_REQUIRED_LATCH", False, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_WS_USE_INTERNAL_RECONNECT", True, raising=False)
    monkeypatch.setattr(cfg, "FEED_FULL_RESTART_COOLDOWN_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_MAX_FULL_RESTARTS_PER_HOUR", 6, raising=False)
    monkeypatch.setattr(cfg, "FEED_SOFT_RESUBSCRIBE_MAX_TICK_AGE_SEC", 2.0, raising=False)
    monkeypatch.setattr(ws, "feed_breaker_tripped", lambda: False)
    monkeypatch.setattr(ws.feed_restart_guard, "allow_restart", lambda **kwargs: True)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws.time, "time", lambda: 20.0)

    calls = {"soft": 0, "start": 0, "stop": 0}

    class _ConnectedTicker:
        def is_connected(self):
            return True

    monkeypatch.setattr(ws, "_KITE_TICKER", _ConnectedTicker(), raising=False)
    monkeypatch.setattr(
        ws,
        "_soft_resubscribe_current",
        lambda reason: calls.__setitem__("soft", calls["soft"] + 1) or True,
    )
    monkeypatch.setattr(
        ws,
        "start_depth_ws",
        lambda tokens, profile_verified=False, **kwargs: calls.__setitem__("start", calls["start"] + 1),
    )
    monkeypatch.setattr(
        ws,
        "stop_depth_ws",
        lambda reason="manual_stop": calls.__setitem__("stop", calls["stop"] + 1),
    )

    assert ws.restart_depth_ws(reason="feed_health:watchdog_down:no_ws_messages_for_10s") is True
    assert calls == {"soft": 0, "start": 1, "stop": 1}


def test_silent_reconnect_waits_for_relaxed_live_thresholds(monkeypatch):
    monkeypatch.setattr(cfg, "FEED_SILENT_INDEX_THRESHOLD_SEC", 5.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_SILENT_OPTION_THRESHOLD_SEC", 8.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_SILENT_CONFIRM_CYCLES", 3, raising=False)
    monkeypatch.setattr(cfg, "FEED_SILENT_FORCE_FULL_RESTART_SEC", 20.0, raising=False)

    calls = {"soft": 0, "start": 0, "stop": 0}
    def restart_cb(**kwargs):
        calls["start"] += 1

    state = {"confirm_hits": 0, "last_reconnect_epoch": 0.0}
    triggered = ws._maybe_trigger_silent_reconnect(
        now_epoch=20.0,
        current_tokens={123, 456},
        underlying_tokens={123},
        last_global_msg_epoch=16.0,
        last_msg_by_token={123: 16.0, 456: 16.0},
        state=state,
        index_threshold_sec=5.0,
        option_threshold_sec=8.0,
        confirm_needed=3,
        backoff_min_sec=1.0,
        backoff_max_sec=10.0,
        force_full_restart_after_sec=20.0,
        restart_cb=restart_cb,
    )

    assert triggered is False
    assert state["confirm_hits"] == 0
    assert calls == {"soft": 0, "start": 0, "stop": 0}


def test_restart_skips_soft_path_for_hard_feed_repair_reason(monkeypatch):
    monkeypatch.setattr(ws, "_LAST_TOKENS", [123, 456], raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 19.5, raising=False)
    monkeypatch.setattr(ws, "_AUTH_REQUIRED_LATCH", False, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_WS_USE_INTERNAL_RECONNECT", True, raising=False)
    monkeypatch.setattr(cfg, "FEED_FULL_RESTART_COOLDOWN_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_MAX_FULL_RESTARTS_PER_HOUR", 6, raising=False)
    monkeypatch.setattr(cfg, "FEED_SOFT_RESUBSCRIBE_MAX_TICK_AGE_SEC", 2.0, raising=False)
    monkeypatch.setattr(ws, "feed_breaker_tripped", lambda: False)
    monkeypatch.setattr(ws.feed_restart_guard, "allow_restart", lambda **kwargs: True)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws.time, "time", lambda: 20.0)

    calls = {"soft": 0, "start": 0, "stop": 0}

    class _ConnectedTicker:
        def is_connected(self):
            return True

    monkeypatch.setattr(ws, "_KITE_TICKER", _ConnectedTicker(), raising=False)
    monkeypatch.setattr(
        ws,
        "_soft_resubscribe_current",
        lambda reason: calls.__setitem__("soft", calls["soft"] + 1) or True,
    )
    monkeypatch.setattr(
        ws,
        "start_depth_ws",
        lambda tokens, profile_verified=False, **kwargs: calls.__setitem__("start", calls["start"] + 1),
    )
    monkeypatch.setattr(
        ws,
        "stop_depth_ws",
        lambda reason="manual_stop": calls.__setitem__("stop", calls["stop"] + 1),
    )

    assert ws.restart_depth_ws(reason="auto_repair:SENSEX:ltp_stale") is True
    assert calls == {"soft": 0, "start": 1, "stop": 1}


def test_restart_forces_full_path_when_explicitly_requested(monkeypatch):
    monkeypatch.setattr(ws, "_LAST_TOKENS", [123, 456], raising=False)
    class _ConnectedTicker:
        def is_connected(self):
            return True

    monkeypatch.setattr(ws, "_KITE_TICKER", _ConnectedTicker(), raising=False)
    monkeypatch.setattr(ws, "_AUTH_REQUIRED_LATCH", False, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_WS_USE_INTERNAL_RECONNECT", True, raising=False)
    monkeypatch.setattr(cfg, "FEED_FULL_RESTART_COOLDOWN_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_MAX_FULL_RESTARTS_PER_HOUR", 6, raising=False)
    monkeypatch.setattr(ws, "feed_breaker_tripped", lambda: False)
    monkeypatch.setattr(ws.feed_restart_guard, "allow_restart", lambda **kwargs: True)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)

    calls = {"soft": 0, "start": 0, "stop": 0}

    monkeypatch.setattr(
        ws,
        "_soft_resubscribe_current",
        lambda reason: calls.__setitem__("soft", calls["soft"] + 1) or True,
    )
    monkeypatch.setattr(
        ws,
        "start_depth_ws",
        lambda tokens, profile_verified=False, **kwargs: calls.__setitem__("start", calls["start"] + 1),
    )
    monkeypatch.setattr(
        ws,
        "stop_depth_ws",
        lambda reason="manual_stop": calls.__setitem__("stop", calls["stop"] + 1),
    )

    assert ws.restart_depth_ws(reason="unit_force_full_path", force_full_restart=True) is True
    assert calls == {"soft": 0, "start": 1, "stop": 1}


def test_restart_falls_back_to_full_restart_when_ticker_is_disconnected(monkeypatch):
    monkeypatch.setattr(ws, "_LAST_TOKENS", [123, 456], raising=False)
    monkeypatch.setattr(cfg, "DEPTH_WS_USE_INTERNAL_RECONNECT", True, raising=False)
    monkeypatch.setattr(cfg, "FEED_FULL_RESTART_COOLDOWN_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_MAX_FULL_RESTARTS_PER_HOUR", 6, raising=False)
    monkeypatch.setattr(ws, "feed_breaker_tripped", lambda: False)
    monkeypatch.setattr(ws.feed_restart_guard, "allow_restart", lambda **kwargs: True)
    monkeypatch.setattr(ws, "_AUTH_REQUIRED_LATCH", False, raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)

    calls = {"soft": 0, "start": 0, "stop": 0}

    class _DisconnectedTicker:
        def is_connected(self):
            return False

    monkeypatch.setattr(ws, "_KITE_TICKER", _DisconnectedTicker(), raising=False)
    monkeypatch.setattr(
        ws,
        "_soft_resubscribe_current",
        lambda reason: calls.__setitem__("soft", calls["soft"] + 1) or True,
    )
    monkeypatch.setattr(
        ws,
        "start_depth_ws",
        lambda tokens, profile_verified=False, **kwargs: calls.__setitem__("start", calls["start"] + 1),
    )
    monkeypatch.setattr(
        ws,
        "stop_depth_ws",
        lambda reason="manual_stop": calls.__setitem__("stop", calls["stop"] + 1),
    )

    assert ws.restart_depth_ws(reason="unit_restart_disconnected_ticker") is True
    assert calls == {"soft": 0, "start": 1, "stop": 1}


def test_soft_resubscribe_uses_desired_tokens_when_flag_enabled(monkeypatch):
    calls = {"subscribe": [], "set_mode": []}
    events = []

    class _DummyTicker:
        MODE_FULL = "full"

        def subscribe(self, tokens):
            calls["subscribe"].append(list(tokens))

        def set_mode(self, mode, tokens):
            assert mode == self.MODE_FULL
            calls["set_mode"].append(list(tokens))

    monkeypatch.setattr(ws, "_KITE_TICKER", _DummyTicker(), raising=False)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [1, 2, 3], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", list(range(1, 40)), raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {1, 2, 3}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {1: "NIFTY", 2: "BANKNIFTY", 3: "SENSEX"}, raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload: events.append((event, payload)))
    monkeypatch.setenv("FEED_USE_DESIRED_TOKENS", "1")

    assert ws._soft_resubscribe_current(reason="unit_test") is True
    assert calls["subscribe"] == [list(range(1, 40))]
    assert calls["set_mode"] == [list(range(1, 40))]
    assert events[-1][0] == "FEED_SOFT_RESUBSCRIBE_OK"
    assert events[-1][1]["desired_tokens_count"] == 39
    assert events[-1][1]["desired_option_tokens_count"] == 36
    assert events[-1][1]["resubscribe_tokens_count"] == 39


def test_soft_resubscribe_uses_last_tokens_when_flag_disabled(monkeypatch):
    calls = {"subscribe": [], "set_mode": []}
    events = []

    class _DummyTicker:
        MODE_FULL = "full"

        def subscribe(self, tokens):
            calls["subscribe"].append(list(tokens))

        def set_mode(self, mode, tokens):
            assert mode == self.MODE_FULL
            calls["set_mode"].append(list(tokens))

    monkeypatch.setattr(ws, "_KITE_TICKER", _DummyTicker(), raising=False)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [11, 22, 33, 44], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", list(range(1, 40)), raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {11, 22, 33}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {11: "NIFTY", 22: "BANKNIFTY", 33: "SENSEX"}, raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload: events.append((event, payload)))
    monkeypatch.delenv("FEED_USE_DESIRED_TOKENS", raising=False)

    assert ws._soft_resubscribe_current(reason="unit_test_flag_off") is True
    assert calls["subscribe"] == [[11, 22, 33, 44]]
    assert calls["set_mode"] == [[11, 22, 33, 44]]
    assert events[-1][0] == "FEED_SOFT_RESUBSCRIBE_OK"
    assert events[-1][1]["desired_tokens_count"] == 39
    assert events[-1][1]["fallback_option_tokens_count"] == 1
    assert events[-1][1]["auto_recover_missing_options"] is False
    assert events[-1][1]["resubscribe_tokens_count"] == 4


def test_soft_resubscribe_auto_recovers_desired_tokens_when_current_is_underlyings_only(monkeypatch):
    calls = {"subscribe": [], "set_mode": []}
    events = []

    class _DummyTicker:
        MODE_FULL = "full"

        def subscribe(self, tokens):
            calls["subscribe"].append(list(tokens))

        def set_mode(self, mode, tokens):
            assert mode == self.MODE_FULL
            calls["set_mode"].append(list(tokens))

    monkeypatch.setattr(ws, "_KITE_TICKER", _DummyTicker(), raising=False)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [11, 22, 33], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", list(range(1, 40)), raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {11, 22, 33}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {11: "NIFTY", 22: "BANKNIFTY", 33: "SENSEX"}, raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload: events.append((event, payload)))
    monkeypatch.delenv("FEED_USE_DESIRED_TOKENS", raising=False)

    assert ws._soft_resubscribe_current(reason="unit_test_auto_recover") is True
    assert calls["subscribe"] == [list(range(1, 40))]
    assert calls["set_mode"] == [list(range(1, 40))]
    assert events[-1][0] == "FEED_SOFT_RESUBSCRIBE_OK"
    assert events[-1][1]["fallback_option_tokens_count"] == 0
    assert events[-1][1]["auto_recover_missing_options"] is True
    assert events[-1][1]["token_source"] == "desired_auto_recovery"
    assert events[-1][1]["resubscribe_tokens_count"] == 39


def test_full_restart_uses_desired_tokens_when_flag_enabled(monkeypatch):
    monkeypatch.setattr(ws, "_LAST_TOKENS", [1, 2, 3], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", list(range(1, 40)), raising=False)
    monkeypatch.setattr(ws, "_FULL_RESTARTS", [], raising=False)
    monkeypatch.setattr(ws, "_LAST_FULL_RESTART_EPOCH", 0.0, raising=False)
    monkeypatch.setattr(ws, "_STALE_STRIKES", 0, raising=False)
    monkeypatch.setattr(ws, "_KITE_TICKER", None, raising=False)
    monkeypatch.setattr(ws, "_AUTH_REQUIRED_LATCH", False, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_WS_USE_INTERNAL_RECONNECT", False, raising=False)
    monkeypatch.setattr(cfg, "FEED_FULL_RESTART_COOLDOWN_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_MAX_FULL_RESTARTS_PER_HOUR", 6, raising=False)
    monkeypatch.setattr(ws, "feed_breaker_tripped", lambda: False)
    monkeypatch.setattr(ws.feed_restart_guard, "allow_restart", lambda **kwargs: True)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    monkeypatch.setenv("FEED_USE_DESIRED_TOKENS", "1")

    calls = {}
    monkeypatch.setattr(
        ws,
        "start_depth_ws",
        lambda tokens, profile_verified=False, **kwargs: calls.setdefault("tokens", list(tokens)),
    )
    monkeypatch.setattr(ws, "stop_depth_ws", lambda reason="manual_stop": None)

    assert ws.restart_depth_ws(reason="unit_full_restart") is True
    assert calls["tokens"] == list(range(1, 40))


def test_option_runtime_state_marks_live_symbol_fresh_without_cross_symbol_leak(monkeypatch):
    monkeypatch.setattr(cfg, "OPTION_LTP_SLA_SEC", 8.0, raising=False)
    monkeypatch.setattr(ws, "_SYMBOL_LAST_OPTION_TICK_TS", {}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {1, 2}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {1: "NIFTY", 2: "BANKNIFTY"}, raising=False)
    monkeypatch.setattr(
        ws,
        "_TOKEN_TO_SYMBOL",
        {
            1: "NIFTY",
            2: "BANKNIFTY",
            101: "NIFTY",
            102: "NIFTY",
            201: "BANKNIFTY",
        },
        raising=False,
    )
    monkeypatch.setattr(
        ws,
        "_LAST_MSG_TS_BY_TOKEN",
        {
            101: 100.0,
            102: 70.0,
        },
        raising=False,
    )

    state = ws._option_runtime_state(
        now_epoch=102.0,
        tokens=[1, 2, 101, 102],
        expected_counts_by_symbol={"NIFTY": 2, "BANKNIFTY": 1},
        min_required_by_symbol={"NIFTY": 1, "BANKNIFTY": 1},
    )

    assert state["subscribed_count_by_symbol"] == {"NIFTY": 2}
    assert state["ticks_received_count_by_symbol"] == {"NIFTY": 2}
    assert state["last_tick_ts_by_symbol"] == {"NIFTY": 100.0}
    assert state["option_age_by_symbol"]["NIFTY"] == 2.0
    assert state["feed_block_reason_by_symbol"]["NIFTY"] == "OK"
    assert state["feed_block_reason_by_symbol"]["BANKNIFTY"] == "NO_LIVE_OPTION_FEED"
    assert state["active_blockers_by_symbol"]["BANKNIFTY"] == ["NO_LIVE_OPTION_FEED"]


def test_option_runtime_state_distinguishes_no_token_no_live_and_stale(monkeypatch):
    monkeypatch.setattr(cfg, "OPTION_LTP_SLA_SEC", 8.0, raising=False)
    monkeypatch.setattr(ws, "_SYMBOL_LAST_OPTION_TICK_TS", {}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {1}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {1: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {1: "NIFTY", 101: "NIFTY"}, raising=False)

    monkeypatch.setattr(ws, "_LAST_MSG_TS_BY_TOKEN", {}, raising=False)
    no_token = ws._option_runtime_state(
        now_epoch=100.0,
        tokens=[1],
        expected_counts_by_symbol={"NIFTY": 0},
        min_required_by_symbol={"NIFTY": 1},
    )
    assert no_token["feed_block_reason_by_symbol"]["NIFTY"] == "NO_LIVE_OPTION_FEED"
    assert no_token["active_blockers_by_symbol"]["NIFTY"] == ["NO_LIVE_OPTION_FEED"]

    no_live = ws._option_runtime_state(
        now_epoch=100.0,
        tokens=[1, 101],
        expected_counts_by_symbol={"NIFTY": 1},
        min_required_by_symbol={"NIFTY": 1},
    )
    assert no_live["feed_block_reason_by_symbol"]["NIFTY"] == "NO_LIVE_OPTION_FEED"

    monkeypatch.setattr(ws, "_LAST_MSG_TS_BY_TOKEN", {101: 80.0}, raising=False)
    stale = ws._option_runtime_state(
        now_epoch=100.0,
        tokens=[1, 101],
        expected_counts_by_symbol={"NIFTY": 1},
        min_required_by_symbol={"NIFTY": 1},
    )
    assert stale["feed_block_reason_by_symbol"]["NIFTY"] == "NO_LIVE_OPTION_FEED"
    assert stale["active_blockers_by_symbol"]["NIFTY"] == ["NO_LIVE_OPTION_FEED", "STALE_OPTION_LTP"]

def test_restart_returns_false_when_start_fails_after_stop(monkeypatch):
    monkeypatch.setattr(ws, "_LAST_TOKENS", [123, 456], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", [123, 456], raising=False)
    monkeypatch.setattr(ws, "_FULL_RESTARTS", [], raising=False)
    monkeypatch.setattr(ws, "_LAST_FULL_RESTART_EPOCH", 0.0, raising=False)
    monkeypatch.setattr(ws, "_STALE_STRIKES", 0, raising=False)
    monkeypatch.setattr(ws, "_AUTH_REQUIRED_LATCH", False, raising=False)
    monkeypatch.setattr(ws, "_STOP_REQUESTED", False, raising=False)
    monkeypatch.setattr(cfg, "FEED_FULL_RESTART_COOLDOWN_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_MAX_FULL_RESTARTS_PER_HOUR", 6, raising=False)
    monkeypatch.setattr(ws, "feed_breaker_tripped", lambda: False)
    monkeypatch.setattr(ws.feed_restart_guard, "allow_restart", lambda **kwargs: True)

    events = []
    snapshots = []
    calls = {"stop": 0, "start": 0, "stop_requested_at_start": None}

    monkeypatch.setattr(ws, "_log_ws", lambda event, payload: events.append((event, payload)))
    monkeypatch.setattr(ws, "_persist_runtime_snapshot_row", lambda **kwargs: snapshots.append(kwargs))

    def _stop(reason="manual_stop"):
        calls["stop"] += 1
        ws._STOP_REQUESTED = True

    def _start(tokens, profile_verified=False, **kwargs):
        calls["start"] += 1
        calls["stop_requested_at_start"] = ws._STOP_REQUESTED
        return False

    monkeypatch.setattr(ws, "stop_depth_ws", _stop)
    monkeypatch.setattr(ws, "start_depth_ws", _start)

    assert ws.restart_depth_ws(
        reason="ws_error:1006",
        ignore_cooldown=True,
        force_full_restart=True,
    ) is False

    assert calls["stop"] == 1
    assert calls["start"] == 1
    assert calls["stop_requested_at_start"] is False
    assert "FEED_FULL_RESTART_OK" not in [event for event, _payload in events]
    assert "FEED_FULL_RESTART_FAILED_AFTER_STOP" in [event for event, _payload in events]
    assert any(row["runtime_state"] == "RESTARTING" for row in snapshots)
    assert any(row["runtime_state"] == "RESTART_FAILED" for row in snapshots)


def test_restart_writes_start_requested_before_ok_when_start_handoff_succeeds(monkeypatch):
    monkeypatch.setattr(ws, "_LAST_TOKENS", [123, 456], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", [123, 456], raising=False)
    monkeypatch.setattr(ws, "_FULL_RESTARTS", [], raising=False)
    monkeypatch.setattr(ws, "_LAST_FULL_RESTART_EPOCH", 0.0, raising=False)
    monkeypatch.setattr(ws, "_STALE_STRIKES", 0, raising=False)
    monkeypatch.setattr(ws, "_AUTH_REQUIRED_LATCH", False, raising=False)
    monkeypatch.setattr(ws, "_STOP_REQUESTED", False, raising=False)
    monkeypatch.setattr(cfg, "FEED_FULL_RESTART_COOLDOWN_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_MAX_FULL_RESTARTS_PER_HOUR", 6, raising=False)
    monkeypatch.setattr(ws, "feed_breaker_tripped", lambda: False)
    monkeypatch.setattr(ws.feed_restart_guard, "allow_restart", lambda **kwargs: True)

    events = []
    snapshots = []
    calls = {"stop": 0, "start": 0}

    monkeypatch.setattr(ws, "_log_ws", lambda event, payload: events.append((event, payload)))
    monkeypatch.setattr(ws, "_persist_runtime_snapshot_row", lambda **kwargs: snapshots.append(kwargs))

    def _stop(reason="manual_stop"):
        calls["stop"] += 1
        ws._STOP_REQUESTED = True

    def _start(tokens, profile_verified=False, **kwargs):
        calls["start"] += 1
        assert ws._STOP_REQUESTED is False
        return True

    monkeypatch.setattr(ws, "stop_depth_ws", _stop)
    monkeypatch.setattr(ws, "start_depth_ws", _start)

    assert ws.restart_depth_ws(
        reason="ws_error:1006",
        ignore_cooldown=True,
        force_full_restart=True,
    ) is True

    assert calls == {"stop": 1, "start": 1}
    event_names = [event for event, _payload in events]
    assert "FEED_FULL_RESTART_BEGIN" in event_names
    assert "FEED_FULL_RESTART_OK" in event_names
    assert any(row["source"] == "restart_depth_ws:begin:ws_error:1006" for row in snapshots)
    assert any(row["source"] == "restart_depth_ws:start_requested:ws_error:1006" for row in snapshots)
