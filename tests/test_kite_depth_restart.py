import core.kite_depth_ws as ws
from core.auth import reset_kite_runtime_credentials_guard
import core.incidents as incidents
import core.storage as storage
from core.feed_recovery_coordinator import FeedRecoveryCoordinator
from config import config as cfg
import json
import pytest

@pytest.fixture(autouse=True)
def mock_check_socket_health(monkeypatch):
    monkeypatch.setattr("core.feed.ws_mutation_queue._check_socket_health", lambda ws: (True, True, None))

from types import SimpleNamespace


@pytest.fixture(autouse=True)
def _reset_ws_runtime_state(monkeypatch):
    for name, value in {
        "_KITE_TICKER": None,
        "_WATCHDOG_THREAD": None,
        "_WATCHDOG_STOP": None,
        "_LAST_TOKENS": [],
        "_LAST_DESIRED_TOKENS": None,
        "_STALE_STRIKES": 0,
        "_WARMUP_PENDING": False,
        "_STOP_REQUESTED": False,
        "_RESTART_ASYNC_THREAD": None,
        "_LAST_WS_TICK_EPOCH": 0.0,
        "_LAST_FEED_HEALTH_STATE": None,
        "_RECONNECT_BLOCKED_REASON": "",
        "_RECONNECT_BLOCKED_SINCE_EPOCH": 0.0,
        "_LAST_INTERNAL_RETRY_SUPPRESSION_STATE": {},
        "_REACTOR_NOT_RESTARTABLE_DETECTED": False,
        "_RECOVERY_IN_PROGRESS": False,
        "_WS1006_RECOVERABLE_ATTEMPTS": 0,
        "_WS1006_RECOVERABLE_LAST_ATTEMPT_EPOCH": 0.0,
        "_WS1006_RECOVERABLE_LAST_REASON": "",
        "_AUTH_REQUIRED_LATCH": False,
        "_AUTH_REQUIRED_LOGGED": False,
        "_LAST_DISCONNECTED_CODE": None,
        "_LAST_DISCONNECTED_REASON": "",
        "_SYMBOL_LAST_LTP_TS": {},
        "_SYMBOL_LAST_DEPTH_TS": {},
        "_SYMBOL_LAST_OPTION_TICK_TS": {},
        "_LAST_MSG_TS_BY_TOKEN": {},
        "_LAST_OPTION_TOKEN_INCIDENT_TS": {},
        "_LAST_OPTION_COUNTS_BY_SYMBOL": {},
        "_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL": {},
        "_TOKEN_TO_SYMBOL": {},
        "_UNDERLYING_TOKENS": set(),
        "_UNDERLYING_TOKEN_TO_SYMBOL": {},
        "_DEPTH_WS_LOCK_ACQUIRED": False,
        "_DEPTH_WS_START_EPOCH": 0.0,
        "_LAST_FEED_TICK_LOG_MINUTE": None,
        "_INTENDED_TOKEN_COUNT": 0,
        "_RUNTIME_STATE": "STOPPED",
        "_LAST_RUNTIME_ERROR": "",
        "_LAST_FULL_RESTART_EPOCH": 0.0,
        "_FULL_RESTARTS": [],
        "_FEED_HEALTH_DURATION_STATE": None,
    }.items():
        monkeypatch.setattr(ws, name, value, raising=False)
    monkeypatch.setattr(ws, "feed_breaker_tripped", lambda: False, raising=False)
    monkeypatch.setattr(ws, "_FEED_RECOVERY_COORDINATOR", FeedRecoveryCoordinator(), raising=False)
    monkeypatch.setattr(ws.kite_client, "_next_expiry_cache", {}, raising=False)
    monkeypatch.setattr(ws.kite_client, "next_available_expiry", lambda *args, **kwargs: None, raising=False)
    monkeypatch.setattr(ws.kite_client, "resolve_option_tokens_window", lambda *args, **kwargs: [], raising=False)
    monkeypatch.setattr(
        ws,
        "get_feed_health_monitor",
        lambda: SimpleNamespace(set_reconnect_handler=lambda handler: None),
        raising=True,
    )
    monkeypatch.setattr(incidents, "create_incident", lambda *args, **kwargs: "inc-test", raising=True)
    monkeypatch.setattr(storage, "emit_sla_violation_event", lambda *args, **kwargs: None, raising=True)
    class _NoopThread:
        def __init__(self, *args, **kwargs):
            self.daemon = kwargs.get("daemon", False)
            self.name = kwargs.get("name", "noop-thread")

        def start(self):
            return None

        def is_alive(self):
            return False

        def join(self, timeout=None):  # pragma: no cover - no-op helper
            return None

    monkeypatch.setattr(ws.threading, "Thread", _NoopThread, raising=True)
    ws._reset_feed_restart_verification(reason="unit_test_reset")


def _read_feed_runtime_latest(tmp_path):
    return json.loads((tmp_path / "logs" / "feed_runtime_latest.json").read_text(encoding="utf-8"))


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


def test_start_depth_ws_marks_reactor_not_restartable_as_recovery_blocked(monkeypatch, tmp_path):
    db_path = tmp_path / "runtime.sqlite"
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)

    class ReactorNotRestartable(Exception):
        pass

    class _FakeTicker:
        MODE_FULL = "full"

        def connect(self, threaded=True):
            raise ReactorNotRestartable("reactor not restartable")

    class _RestClient:
        def profile(self):
            return {"user_id": "ABCD1234"}

    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(cfg, "KITE_USE_DEPTH", True, raising=False)
    monkeypatch.setattr(cfg, "KITE_API_KEY", "test_key", raising=False)
    monkeypatch.setattr(ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(ws, "KiteTicker", object(), raising=True)
    monkeypatch.setattr(ws, "get_kite_ticker", lambda **kwargs: _FakeTicker(), raising=True)
    monkeypatch.setattr(ws, "get_kite_auth_health", lambda force=True: {"ok": True}, raising=True)
    monkeypatch.setattr(ws.kite_client, "ensure", lambda: _RestClient(), raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_api_key", "kite_test_key", raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_access_token", "token1234", raising=False)
    monkeypatch.setattr(ws, "_ensure_depth_ws_lock", lambda: True, raising=True)

    assert ws.start_depth_ws([101, 202], skip_lock=True, skip_guard=True) is False

    payload = json.loads((logs_path / "feed_runtime_latest.json").read_text(encoding="utf-8"))
    assert payload["ws_connected"] is False
    assert payload["runtime_state"] == "RECOVERY_BLOCKED"
    assert payload["reconnect_blocked_reason"] == "reactor_not_restartable_process_restart_required"
    assert payload["recovery_action"] == "process_restart_required"
    assert payload["ws_reconnect_allowed"] is False
    assert payload["ws_reconnect_attempted"] is False
    assert payload["restart_suppressed"] is True
    assert payload["reactor_not_restartable_detected"] is True


def test_schedule_restart_depth_ws_suppresses_when_reactor_blocked(monkeypatch, tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(ws, "_RECONNECT_BLOCKED_REASON", "reactor_not_restartable_process_restart_required", raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    calls = {"thread": 0, "persist": 0}
    monkeypatch.setattr(
        ws,
        "_persist_runtime_snapshot_row",
        lambda **kwargs: calls.__setitem__("persist", calls["persist"] + 1),
    )

    original_thread = ws.threading.Thread

    class _FailThread(original_thread):
        def start(self):  # pragma: no cover - defensive
            calls["thread"] += 1
            raise AssertionError("restart thread should not start when recovery is blocked")

    monkeypatch.setattr(ws.threading, "Thread", _FailThread, raising=True)

    assert (
        ws._schedule_restart_depth_ws(
            reason="ws_error:1006",
            ignore_cooldown=True,
            force_full_restart=True,
            source="on_error",
        )
        is False
    )
    assert calls == {"thread": 0, "persist": 1}


def test_on_error_does_not_schedule_restart_when_reactor_blocked(monkeypatch, tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(ws, "_RECONNECT_BLOCKED_REASON", "", raising=False)
    monkeypatch.setattr(ws, "_STOP_REQUESTED", False, raising=False)
    monkeypatch.setattr(ws, "_WATCHDOG_STOP", None, raising=False)
    monkeypatch.setattr(ws, "_use_native_reconnect", lambda: True, raising=False)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    calls = {"schedule": 0, "persist": 0}
    monkeypatch.setattr(
        ws,
        "_schedule_restart_depth_ws",
        lambda **kwargs: calls.__setitem__("schedule", calls["schedule"] + 1) or True,
    )

    class _Ticker:
        pass

    def _make_ticker():
        class _FakeTicker:
            def connect(self, threaded=True):
                self.on_error(
                    self,
                    1006,
                    "connection was closed uncleanly (peer dropped the TCP connection without previous WebSocket closing handshake)",
                )

        fake = _FakeTicker()
        return fake

    monkeypatch.setattr(ws, "KiteTicker", object(), raising=True)
    monkeypatch.setattr(ws, "get_kite_ticker", lambda **kwargs: _make_ticker(), raising=True)
    monkeypatch.setattr(ws, "get_kite_auth_health", lambda force=True: {"ok": True}, raising=True)
    monkeypatch.setattr(ws.cfg, "KITE_API_KEY", "kite_test_key", raising=False)
    monkeypatch.setattr(ws.cfg, "KITE_ACCESS_TOKEN", "token1234", raising=False)
    monkeypatch.setattr(ws.kite_client, "ensure", lambda: type("_RestClient", (), {"profile": lambda self: {"user_id": "ABCD1234"}})(), raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_api_key", "kite_test_key", raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_access_token", "token1234", raising=False)
    monkeypatch.setattr(ws.kite_client, "next_available_expiry", lambda *args, **kwargs: None, raising=False)
    monkeypatch.setattr(ws, "_ensure_depth_ws_lock", lambda: True, raising=True)

    assert ws.start_depth_ws([101, 202], skip_lock=True, skip_guard=True) is False
    assert calls["schedule"] > 0
    payload = json.loads((logs_path / "feed_runtime_latest.json").read_text(encoding="utf-8"))
    assert payload["runtime_state"] in {"RECONNECTING", "DEGRADED", "SUBSCRIBE_FAILED"}
    assert payload["ws_connected"] is False
    assert payload["disconnected_code"] == 1006
    assert "connection was closed uncleanly" in payload["disconnected_reason"]
    assert payload["restart_attempt_allowed"] is True
    assert payload["restart_attempted"] is True
    assert payload["recovery_blocked"] is False
    assert payload["process_restart_required"] is False
    assert payload["reconnect_blocked_reason"] is None
    assert payload["restart_suppressed"] is False
    assert payload["ws_reconnect_allowed"] is False
    assert payload["ws_reconnect_attempted"] is True
    assert payload["ws_recovery_state"] == "RECOVERING_WS_DROP"
    ws.stop_depth_ws(reason="unit_test_cleanup")


def test_on_close_recoverable_ws1006_keeps_retry_path_open(monkeypatch, tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(ws, "_RECONNECT_BLOCKED_REASON", "", raising=False)
    monkeypatch.setattr(ws, "_STOP_REQUESTED", False, raising=False)
    monkeypatch.setattr(ws, "_WATCHDOG_STOP", None, raising=False)
    monkeypatch.setattr(ws, "_use_native_reconnect", lambda: True, raising=False)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    calls = {"schedule": 0, "persist": 0}
    monkeypatch.setattr(
        ws,
        "_schedule_restart_depth_ws",
        lambda **kwargs: calls.__setitem__("schedule", calls["schedule"] + 1) or True,
    )

    class _FakeTicker:
        def connect(self, threaded=True):
            self.on_close(
                self,
                1006,
                "connection was closed uncleanly (peer dropped the TCP connection without previous WebSocket closing handshake)",
            )

    monkeypatch.setattr(ws, "KiteTicker", object(), raising=True)
    monkeypatch.setattr(ws, "get_kite_ticker", lambda **kwargs: _FakeTicker(), raising=True)
    monkeypatch.setattr(ws, "get_kite_auth_health", lambda force=True: {"ok": True}, raising=True)
    monkeypatch.setattr(ws.cfg, "KITE_API_KEY", "kite_test_key", raising=False)
    monkeypatch.setattr(ws.cfg, "KITE_ACCESS_TOKEN", "token1234", raising=False)
    monkeypatch.setattr(ws.kite_client, "ensure", lambda: type("_RestClient", (), {"profile": lambda self: {"user_id": "ABCD1234"}})(), raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_api_key", "kite_test_key", raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_access_token", "token1234", raising=False)
    monkeypatch.setattr(ws.kite_client, "next_available_expiry", lambda *args, **kwargs: None, raising=False)
    monkeypatch.setattr(ws, "_ensure_depth_ws_lock", lambda: True, raising=True)

    assert ws.start_depth_ws([101, 202], skip_lock=True, skip_guard=True) is False
    assert calls["schedule"] > 0
    payload = json.loads((logs_path / "feed_runtime_latest.json").read_text(encoding="utf-8"))
    assert payload["runtime_state"] in {"RECONNECTING", "DEGRADED", "SUBSCRIBE_FAILED"}
    assert payload["ws_connected"] is False
    assert payload["disconnected_code"] == 1006
    assert "connection was closed uncleanly" in payload["disconnected_reason"]
    assert payload["restart_attempt_allowed"] is True
    assert payload["restart_attempted"] is True
    assert payload["recovery_blocked"] is False
    assert payload["process_restart_required"] is False
    assert payload["reconnect_blocked_reason"] is None
    assert payload["restart_suppressed"] is False
    assert payload["ws_reconnect_allowed"] is False
    assert payload["ws_reconnect_attempted"] is True
    assert payload["ws1006_recovery_attempt_count"] == 1
    assert payload["ws_recovery_state"] == "RECOVERING_WS_DROP"
    ws.stop_depth_ws(reason="unit_test_cleanup")


def test_ws1006_on_error_keeps_reconnect_path_open_first(monkeypatch, tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(ws, "_RECONNECT_BLOCKED_REASON", "", raising=False)
    monkeypatch.setattr(ws, "_STOP_REQUESTED", False, raising=False)
    monkeypatch.setattr(ws, "_WATCHDOG_STOP", None, raising=False)
    monkeypatch.setattr(ws, "_use_native_reconnect", lambda: True, raising=False)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    calls = {"schedule": 0}
    monkeypatch.setattr(
        ws,
        "_schedule_restart_depth_ws",
        lambda **kwargs: calls.__setitem__("schedule", calls["schedule"] + 1) or True,
    )

    class _Factory:
        def __init__(self):
            self.stop_trying_called = 0

        def stopTrying(self):
            self.stop_trying_called += 1

    class _FakeTicker:
        def __init__(self):
            self.auto_reconnect = True
            self.factory = _Factory()
            self.stop_retry_called = 0

        def stop_retry(self):
            self.stop_retry_called += 1

        def connect(self, threaded=True):
            self.on_error(
                self,
                1006,
                "connection was closed uncleanly (peer dropped the TCP connection without previous WebSocket closing handshake)",
            )

    fake_ticker = _FakeTicker()
    monkeypatch.setattr(ws, "KiteTicker", object(), raising=True)
    monkeypatch.setattr(ws, "get_kite_ticker", lambda **kwargs: fake_ticker, raising=True)
    monkeypatch.setattr(ws, "get_kite_auth_health", lambda force=True: {"ok": True}, raising=True)
    monkeypatch.setattr(ws.cfg, "KITE_API_KEY", "kite_test_key", raising=False)
    monkeypatch.setattr(ws.cfg, "KITE_ACCESS_TOKEN", "token1234", raising=False)
    monkeypatch.setattr(ws.kite_client, "ensure", lambda: type("_RestClient", (), {"profile": lambda self: {"user_id": "ABCD1234"}})(), raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_api_key", "kite_test_key", raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_access_token", "token1234", raising=False)
    monkeypatch.setattr(ws.kite_client, "next_available_expiry", lambda *args, **kwargs: None, raising=False)
    monkeypatch.setattr(ws, "_ensure_depth_ws_lock", lambda: True, raising=True)

    assert ws.start_depth_ws([101, 202], skip_lock=True, skip_guard=True) is False
    assert calls["schedule"] > 0
    assert fake_ticker.stop_retry_called == 0
    assert fake_ticker.factory.stop_trying_called == 0
    assert fake_ticker.auto_reconnect is True
    payload = json.loads((logs_path / "feed_runtime_latest.json").read_text(encoding="utf-8"))
    assert payload["runtime_state"] in {"RECONNECTING", "DEGRADED", "SUBSCRIBE_FAILED"}
    assert payload["reconnect_blocked_reason"] is None
    assert payload["process_restart_required"] is False
    assert payload["restart_suppressed"] is False
    assert payload.get("internal_retry_disabled") in {None, False}
    assert payload.get("stop_retry_called") in {None, False}
    assert payload.get("factory_stop_trying_called") in {None, False}
    assert payload.get("auto_reconnect_disabled") in {None, False}
    assert payload.get("internal_retry_reason") is None or "peer dropped" in payload.get("internal_retry_reason")


def test_ws1006_on_close_keeps_reconnect_path_open_first(monkeypatch, tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(ws, "_RECONNECT_BLOCKED_REASON", "", raising=False)
    monkeypatch.setattr(ws, "_STOP_REQUESTED", False, raising=False)
    monkeypatch.setattr(ws, "_WATCHDOG_STOP", None, raising=False)
    monkeypatch.setattr(ws, "_use_native_reconnect", lambda: True, raising=False)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    calls = {"schedule": 0}
    monkeypatch.setattr(
        ws,
        "_schedule_restart_depth_ws",
        lambda **kwargs: calls.__setitem__("schedule", calls["schedule"] + 1) or True,
    )

    class _Factory:
        def __init__(self):
            self.stop_trying_called = 0

        def stopTrying(self):
            self.stop_trying_called += 1

    class _FakeTicker:
        def __init__(self):
            self.auto_reconnect = True
            self.factory = _Factory()
            self.stop_retry_called = 0

        def stop_retry(self):
            self.stop_retry_called += 1

        def connect(self, threaded=True):
            self.on_close(
                self,
                1006,
                "connection was closed uncleanly (peer dropped the TCP connection without previous WebSocket closing handshake)",
            )

    fake_ticker = _FakeTicker()
    monkeypatch.setattr(ws, "KiteTicker", object(), raising=True)
    monkeypatch.setattr(ws, "get_kite_ticker", lambda **kwargs: fake_ticker, raising=True)
    monkeypatch.setattr(ws, "get_kite_auth_health", lambda force=True: {"ok": True}, raising=True)
    monkeypatch.setattr(ws.cfg, "KITE_API_KEY", "kite_test_key", raising=False)
    monkeypatch.setattr(ws.cfg, "KITE_ACCESS_TOKEN", "token1234", raising=False)
    monkeypatch.setattr(ws.kite_client, "ensure", lambda: type("_RestClient", (), {"profile": lambda self: {"user_id": "ABCD1234"}})(), raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_api_key", "kite_test_key", raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_access_token", "token1234", raising=False)
    monkeypatch.setattr(ws.kite_client, "next_available_expiry", lambda *args, **kwargs: None, raising=False)
    monkeypatch.setattr(ws, "_ensure_depth_ws_lock", lambda: True, raising=True)

    assert ws.start_depth_ws([101, 202], skip_lock=True, skip_guard=True) is False
    assert calls["schedule"] > 0
    assert fake_ticker.stop_retry_called == 0
    assert fake_ticker.factory.stop_trying_called == 0
    assert fake_ticker.auto_reconnect is True
    payload = json.loads((logs_path / "feed_runtime_latest.json").read_text(encoding="utf-8"))
    assert payload["runtime_state"] in {"RECONNECTING", "DEGRADED"}
    assert payload["reconnect_blocked_reason"] is None
    assert payload["process_restart_required"] is False
    assert payload["restart_suppressed"] is False
    assert payload.get("internal_retry_disabled") in {None, False}
    assert payload.get("stop_retry_called") in {None, False}
    assert payload.get("factory_stop_trying_called") in {None, False}
    assert payload.get("auto_reconnect_disabled") in {None, False}
    assert payload.get("internal_retry_reason") is None or "peer dropped" in payload.get("internal_retry_reason")


def test_terminal_recovery_internal_retry_suppression_is_safe_without_stop_retry(monkeypatch, tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(ws, "_RECONNECT_BLOCKED_REASON", "", raising=False)
    monkeypatch.setattr(ws, "_STOP_REQUESTED", False, raising=False)
    monkeypatch.setattr(ws, "_WATCHDOG_STOP", None, raising=False)
    monkeypatch.setattr(ws, "_use_native_reconnect", lambda: True, raising=False)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)

    class _FakeTicker:
        def __init__(self):
            self.auto_reconnect = True
            self.factory = None

        def connect(self, threaded=True):
            self.on_close(self, 1006, "connection was closed uncleanly (peer dropped)")

    fake_ticker = _FakeTicker()
    monkeypatch.setattr(ws, "KiteTicker", object(), raising=True)
    monkeypatch.setattr(ws, "get_kite_ticker", lambda **kwargs: fake_ticker, raising=True)
    monkeypatch.setattr(ws, "get_kite_auth_health", lambda force=True: {"ok": True}, raising=True)
    monkeypatch.setattr(ws.cfg, "KITE_API_KEY", "kite_test_key", raising=False)
    monkeypatch.setattr(ws.cfg, "KITE_ACCESS_TOKEN", "token1234", raising=False)
    monkeypatch.setattr(ws.kite_client, "ensure", lambda: type("_RestClient", (), {"profile": lambda self: {"user_id": "ABCD1234"}})(), raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_api_key", "kite_test_key", raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_access_token", "token1234", raising=False)
    monkeypatch.setattr(ws.kite_client, "next_available_expiry", lambda *args, **kwargs: None, raising=False)
    monkeypatch.setattr(ws, "_ensure_depth_ws_lock", lambda: True, raising=True)

    assert ws.start_depth_ws([101, 202], skip_lock=True, skip_guard=True) is False
    payload = json.loads((logs_path / "feed_runtime_latest.json").read_text(encoding="utf-8"))
    assert payload["runtime_state"] in {"RECONNECTING", "DEGRADED"}
    assert payload["reconnect_blocked_reason"] is None
    assert payload.get("internal_retry_disabled") in {None, False}
    assert payload.get("stop_retry_called") in {None, False}
    assert payload.get("factory_stop_trying_called") in {None, False}
    assert payload.get("auto_reconnect_disabled") in {None, False}
    assert payload["restart_suppressed"] is False


def test_ws1006_recovery_does_not_overlap_when_already_in_progress(monkeypatch, tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(ws, "_RECONNECT_BLOCKED_REASON", "", raising=False)
    monkeypatch.setattr(ws, "_STOP_REQUESTED", False, raising=False)
    monkeypatch.setattr(ws, "_WATCHDOG_STOP", None, raising=False)
    monkeypatch.setattr(ws, "_use_native_reconnect", lambda: True, raising=False)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(ws, "_soft_resubscribe_current", lambda reason: False, raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)

    calls = {"schedule": 0}
    monkeypatch.setattr(
        ws,
        "_schedule_restart_depth_ws",
        lambda **kwargs: calls.__setitem__("schedule", calls["schedule"] + 1) or True,
    )

    class _FakeTicker:
        def connect(self, threaded=True):
            self.on_error(self, 1006, "connection was closed uncleanly (peer dropped)")
            self.on_error(self, 1006, "connection was closed uncleanly (peer dropped)")

    fake_ticker = _FakeTicker()
    monkeypatch.setattr(ws, "KiteTicker", object(), raising=True)
    monkeypatch.setattr(ws, "get_kite_ticker", lambda **kwargs: fake_ticker, raising=True)
    monkeypatch.setattr(ws, "get_kite_auth_health", lambda force=True: {"ok": True}, raising=True)
    monkeypatch.setattr(ws.cfg, "KITE_API_KEY", "kite_test_key", raising=False)
    monkeypatch.setattr(ws.cfg, "KITE_ACCESS_TOKEN", "token1234", raising=False)
    monkeypatch.setattr(ws.kite_client, "ensure", lambda: type("_RestClient", (), {"profile": lambda self: {"user_id": "ABCD1234"}})(), raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_api_key", "kite_test_key", raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_access_token", "token1234", raising=False)
    monkeypatch.setattr(ws.kite_client, "next_available_expiry", lambda *args, **kwargs: None, raising=False)
    monkeypatch.setattr(ws, "_ensure_depth_ws_lock", lambda: True, raising=True)

    assert ws.start_depth_ws([101, 202], skip_lock=True, skip_guard=True) is False
    assert calls["schedule"] > 0
    payload = json.loads((logs_path / "feed_runtime_latest.json").read_text(encoding="utf-8"))
    assert payload["ws1006_recovery_attempt_count"] == 1
    assert payload["recovery_in_progress"] is True
    assert payload["ws_recovery_state"] == "RECOVERING_WS_DROP"


def test_recovery_blocked_followup_starting_factory_is_suppressed(monkeypatch, tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws, "_RECONNECT_BLOCKED_REASON", "ws1006_process_restart_required", raising=False)
    monkeypatch.setattr(ws, "_REACTOR_NOT_RESTARTABLE_DETECTED", False, raising=False)
    monkeypatch.setattr(ws, "_STOP_REQUESTED", False, raising=False)
    monkeypatch.setattr(ws, "_WATCHDOG_STOP", None, raising=False)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)

    calls = {"ticker": 0, "start": 0}

    class _FailTicker:
        def __init__(self, *args, **kwargs):
            calls["ticker"] += 1
            self.auto_reconnect = True

        def stop_retry(self):
            calls["start"] += 1

        def connect(self, threaded=True):  # pragma: no cover - defensive
            raise AssertionError("blocked recovery must not create a new ticker connect path")

    monkeypatch.setattr(ws, "KiteTicker", object(), raising=True)
    monkeypatch.setattr(ws, "get_kite_ticker", lambda **kwargs: _FailTicker(), raising=True)
    monkeypatch.setattr(ws, "get_kite_auth_health", lambda force=True: {"ok": True}, raising=True)
    monkeypatch.setattr(ws.cfg, "KITE_API_KEY", "kite_test_key", raising=False)
    monkeypatch.setattr(ws.cfg, "KITE_ACCESS_TOKEN", "token1234", raising=False)
    monkeypatch.setattr(ws.kite_client, "ensure", lambda: type("_RestClient", (), {"profile": lambda self: {"user_id": "ABCD1234"}})(), raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_api_key", "kite_test_key", raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_access_token", "token1234", raising=False)
    monkeypatch.setattr(ws.kite_client, "next_available_expiry", lambda *args, **kwargs: None, raising=False)
    monkeypatch.setattr(ws, "_ensure_depth_ws_lock", lambda: True, raising=True)

    assert ws.start_depth_ws([101, 202], skip_lock=True, skip_guard=True) is False
    assert calls == {"ticker": 0, "start": 0}
    payload = json.loads((logs_path / "feed_runtime_latest.json").read_text(encoding="utf-8"))
    assert payload["runtime_state"] == "RECOVERY_BLOCKED"
    assert payload["reconnect_blocked_reason"] == "ws1006_process_restart_required"
    assert payload["restart_suppressed"] is True


def test_restart_depth_ws_does_not_start_duplicate_recovery_when_coordinator_in_progress(monkeypatch):
    calls = {"stop": 0}
    events: list[tuple[str, dict]] = []
    coordinator = FeedRecoveryCoordinator(max_recoverable_attempts_per_session=2, recoverable_retry_cooldown_sec=0.0)
    coordinator.request_recovery(source="on_error", code=1006, reason="peer dropped")
    monkeypatch.setattr(ws, "_FEED_RECOVERY_COORDINATOR", coordinator, raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    monkeypatch.setattr(ws, "stop_depth_ws", lambda reason="manual_stop": calls.__setitem__("stop", calls["stop"] + 1))

    assert ws.restart_depth_ws(reason="duplicate_recovery_request") is False
    assert calls["stop"] == 0
    assert any(event == "FEED_RECOVERY_ALREADY_IN_PROGRESS" for event, _ in events)


def test_non_terminal_network_error_still_uses_existing_restart_behavior(monkeypatch):
    monkeypatch.setattr(ws, "_RECONNECT_BLOCKED_REASON", "", raising=False)
    monkeypatch.setattr(ws, "_REACTOR_NOT_RESTARTABLE_DETECTED", False, raising=False)
    monkeypatch.setattr(ws, "_STOP_REQUESTED", False, raising=False)
    monkeypatch.setattr(ws, "_WATCHDOG_STOP", None, raising=False)
    monkeypatch.setattr(ws, "_use_native_reconnect", lambda: False, raising=False)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    calls = {"restart": 0, "stop_retry": 0}

    class _Factory:
        def __init__(self):
            self.stop_trying_called = 0

        def stopTrying(self):
            self.stop_trying_called += 1

    class _FakeTicker:
        def __init__(self):
            self.auto_reconnect = True
            self.factory = _Factory()
            self.stop_retry_called = 0

        def stop_retry(self):
            self.stop_retry_called += 1

        def connect(self, threaded=True):
            self.on_error(self, 1006, "connection closed by peer")

    fake_ticker = _FakeTicker()
    monkeypatch.setattr(ws, "KiteTicker", object(), raising=True)
    monkeypatch.setattr(ws, "get_kite_ticker", lambda **kwargs: fake_ticker, raising=True)
    monkeypatch.setattr(ws, "get_kite_auth_health", lambda force=True: {"ok": True}, raising=True)
    monkeypatch.setattr(ws.cfg, "KITE_API_KEY", "kite_test_key", raising=False)
    monkeypatch.setattr(ws.cfg, "KITE_ACCESS_TOKEN", "token1234", raising=False)
    monkeypatch.setattr(ws.kite_client, "ensure", lambda: type("_RestClient", (), {"profile": lambda self: {"user_id": "ABCD1234"}})(), raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_api_key", "kite_test_key", raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_access_token", "token1234", raising=False)
    monkeypatch.setattr(ws.kite_client, "next_available_expiry", lambda *args, **kwargs: None, raising=False)
    monkeypatch.setattr(ws, "_ensure_depth_ws_lock", lambda: True, raising=True)
    monkeypatch.setattr(
        ws,
        "restart_depth_ws",
        lambda reason="unknown", ignore_cooldown=False, force_full_restart=False: calls.__setitem__("restart", calls["restart"] + 1) or True,
    )

    assert ws.start_depth_ws([101, 202], skip_lock=True, skip_guard=True) is False
    assert calls["restart"] == 0
    assert fake_ticker.stop_retry_called == 0
    assert fake_ticker.factory.stop_trying_called == 0


def test_recovery_blocked_snapshot_contains_process_restart_required(monkeypatch, tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(ws, "_restart_verification_enabled", lambda: False, raising=True)
    monkeypatch.setattr(ws, "_RECONNECT_BLOCKED_REASON", "reactor_not_restartable_process_restart_required", raising=False)
    monkeypatch.setattr(ws, "_REACTOR_NOT_RESTARTABLE_DETECTED", True, raising=False)
    payload = ws._emit_reconnect_recovery_blocked_snapshot(
        source="unit_test",
        reason="reactor_not_restartable",
    )
    assert payload["recovery_action"] == "process_restart_required"
    assert payload["reactor_not_restartable_detected"] is True
    snapshot = json.loads((logs_path / "feed_runtime_latest.json").read_text(encoding="utf-8"))
    assert snapshot["runtime_state"] == "RECOVERY_BLOCKED"
    assert snapshot["reconnect_blocked_reason"] == "reactor_not_restartable_process_restart_required"
    assert snapshot["restart_blocked_reason"] == "reactor_not_restartable_process_restart_required"
    assert snapshot["recovery_action"] == "process_restart_required"
    assert snapshot["process_restart_required"] is True
    assert snapshot["recovery_blocked"] is True
    assert snapshot["restart_attempt_allowed"] is False
    assert snapshot["restart_attempted"] is False
    assert snapshot["ws_reconnect_allowed"] is False
    assert snapshot["ws_reconnect_attempted"] is False


def test_restart_depth_ws_stops_retrying_when_reactor_recovery_is_blocked(monkeypatch):
    monkeypatch.setattr(ws, "_RECONNECT_BLOCKED_REASON", "reactor_not_restartable_process_restart_required", raising=False)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [101, 202], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", [101, 202], raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    calls = {"stop": 0, "start": 0, "persist": 0}
    monkeypatch.setattr(ws, "stop_depth_ws", lambda reason="manual_stop": calls.__setitem__("stop", calls["stop"] + 1))
    monkeypatch.setattr(ws, "start_depth_ws", lambda *args, **kwargs: calls.__setitem__("start", calls["start"] + 1))
    monkeypatch.setattr(ws, "_persist_runtime_snapshot_row", lambda **kwargs: calls.__setitem__("persist", calls["persist"] + 1))

    assert ws.restart_depth_ws(reason="unit_test_reactor_blocked") is False
    assert calls == {"stop": 0, "start": 0, "persist": 1}


def test_schedule_restart_depth_ws_does_not_spawn_duplicate_when_restart_is_already_running(monkeypatch):
    class _AliveRestartThread:
        def is_alive(self):
            return True

    monkeypatch.setattr(ws, "_RECONNECT_BLOCKED_REASON", "", raising=False)
    monkeypatch.setattr(ws, "_REACTOR_NOT_RESTARTABLE_DETECTED", False, raising=False)
    monkeypatch.setattr(ws, "_RESTART_ASYNC_THREAD", _AliveRestartThread(), raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws, "threading", ws.threading, raising=False)

    class _FailThread:
        def __init__(self, *args, **kwargs):
            raise AssertionError("duplicate restart thread must not be created")

    monkeypatch.setattr(ws.threading, "Thread", _FailThread, raising=True)

    assert (
        ws._schedule_restart_depth_ws(
            reason="unit_test_duplicate_restart",
            ignore_cooldown=True,
            force_full_restart=True,
            source="unit_test",
        )
        is True
    )


def test_reactor_terminal_state_blocks_followup_start_restart_and_schedule(monkeypatch, tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    reset_kite_runtime_credentials_guard()
    monkeypatch.setattr(ws, "_RECONNECT_BLOCKED_REASON", "reactor_not_restartable_process_restart_required", raising=False)
    monkeypatch.setattr(ws, "_REACTOR_NOT_RESTARTABLE_DETECTED", True, raising=False)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [101, 202], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", [101, 202], raising=False)
    class _StableRestClient:
        def profile(self):
            return {"user_id": "ABCD1234"}

    stable_rest_client = _StableRestClient()
    monkeypatch.setattr(ws.kite_client, "ensure", lambda: stable_rest_client, raising=False)
    monkeypatch.setattr(ws.kite_client, "_next_expiry_cache", {}, raising=False)
    monkeypatch.setattr(ws.kite_client, "next_available_expiry", lambda *args, **kwargs: None, raising=False)
    monkeypatch.setattr(ws.kite_client, "instruments", lambda *args, **kwargs: [], raising=False)
    monkeypatch.setattr(incidents, "create_incident", lambda *args, **kwargs: "incident-test", raising=False)
    monkeypatch.setattr(storage, "emit_sla_violation_event", lambda *args, **kwargs: None, raising=False)

    calls = {"start": 0, "schedule": 0, "thread": 0, "persist": 0}
    original_persist = ws._persist_runtime_snapshot_row
    monkeypatch.setattr(
        ws,
        "get_kite_ticker",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("reactor terminal state must not create a ticker")),
        raising=True,
    )
    monkeypatch.setattr(
        ws,
        "_persist_runtime_snapshot_row",
        lambda **kwargs: calls.__setitem__("persist", calls["persist"] + 1) or original_persist(**kwargs),
    )

    original_thread = ws.threading.Thread

    class _FailThread(original_thread):
        def start(self):  # pragma: no cover - defensive
            calls["thread"] += 1
            raise AssertionError("reactor terminal state must not start a restart thread")

    monkeypatch.setattr(ws.threading, "Thread", _FailThread, raising=True)

    assert ws.start_depth_ws([101, 202], skip_lock=True, skip_guard=True) is False

    monkeypatch.setattr(
        ws,
        "start_depth_ws",
        lambda *args, **kwargs: calls.__setitem__("start", calls["start"] + 1) or True,
        raising=True,
    )
    assert ws.restart_depth_ws(reason="unit_test_terminal_reactor") is False
    assert (
        ws._schedule_restart_depth_ws(
            reason="ws_error:1006",
            ignore_cooldown=True,
            force_full_restart=True,
            source="unit_test",
        )
        is False
    )
    assert calls == {"start": 0, "schedule": 0, "thread": 0, "persist": 3}
    payload = json.loads((logs_path / "feed_runtime_latest.json").read_text(encoding="utf-8"))
    assert payload["runtime_state"] == "RECOVERY_BLOCKED"
    assert payload["state_machine"]["state"] == "DOWN"
    assert payload["state_machine"]["reason"] == "reactor_not_restartable_process_restart_required"
    assert payload["reconnect_blocked_reason"] == "reactor_not_restartable_process_restart_required"
    assert payload["recovery_action"] == "process_restart_required"
    assert payload["reactor_not_restartable_detected"] is True
    assert payload["restart_suppressed"] is True


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


def test_silent_reconnect_emits_rca_bucket_for_breaker_blocked_recovery(monkeypatch):
    monkeypatch.setattr(ws, "feed_breaker_tripped", lambda: True, raising=False)
    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload=None, **kwargs: events.append((event, payload)))

    state = {"confirm_hits": 0, "last_reconnect_epoch": 0.0}
    triggered = ws._maybe_trigger_silent_reconnect(
        now_epoch=20.0,
        current_tokens={123, 456},
        underlying_tokens={123},
        last_global_msg_epoch=1.0,
        last_msg_by_token={123: 1.0, 456: 1.0},
        state=state,
        index_threshold_sec=5.0,
        option_threshold_sec=8.0,
        confirm_needed=1,
        backoff_min_sec=1.0,
        backoff_max_sec=10.0,
        force_full_restart_after_sec=100.0,
        restart_cb=lambda **kwargs: None,
    )

    assert triggered is True
    assert any(event == "FEED_SILENCE_RCA" for event, _payload in events)
    rca_payload = next(payload for event, payload in events if event == "FEED_SILENCE_RCA")
    assert rca_payload["silence_bucket"] == "breaker_blocked_recovery"
    assert rca_payload["feed_breaker_open"] is True


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
        connected = True

        def is_connected(self):
            return True

    def mock_safe_subscribe_full_mode(ws_obj, tokens, reason, now_epoch, on_applied_callback=None):
            calls["subscribe"].append(list(tokens))
            calls["set_mode"].append(list(tokens))
            if on_applied_callback: on_applied_callback()
            res = type("WsMutationResult", (), {"ok": True, "applied": True, "queued": False, "failure_reason": ""})()
            return res, res
        
    monkeypatch.setattr("core.feed.ws_mutation_queue.safe_subscribe_full_mode", mock_safe_subscribe_full_mode)

    monkeypatch.setattr(ws, "_KITE_TICKER", _DummyTicker(), raising=False)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [1, 2, 3], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", list(range(1, 40)), raising=False)
    monkeypatch.setattr(ws, "_RUNTIME_STATE", "RUNNING", raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 100.0, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {1, 2, 3}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {1: "NIFTY", 2: "BANKNIFTY", 3: "SENSEX"}, raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    monkeypatch.setenv("FEED_USE_DESIRED_TOKENS", "1")

    assert ws._soft_resubscribe_current(reason="unit_test") is True
    assert calls["subscribe"] == [list(range(1, 40))]
    assert calls["set_mode"] == [list(range(1, 40))]
    assert events[-1][0] == "FEED_MUTATION_APPLIED"
    assert events[-1][1]["desired_tokens_count"] == 39
    assert events[-1][1]["desired_option_tokens_count"] == 36
    assert events[-1][1]["resubscribe_tokens_count"] == 39


def test_soft_resubscribe_uses_last_tokens_when_flag_disabled(monkeypatch):
    calls = {"subscribe": [], "set_mode": []}
    events = []

    class _DummyTicker:
        MODE_FULL = "full"
        connected = True

        def is_connected(self):
            return True

    def mock_safe_subscribe_full_mode(ws_obj, tokens, reason, now_epoch, on_applied_callback=None):
            calls["subscribe"].append(list(tokens))
            calls["set_mode"].append(list(tokens))
            if on_applied_callback: on_applied_callback()
            res = type("WsMutationResult", (), {"ok": True, "applied": True, "queued": False, "failure_reason": ""})()
            return res, res
        
    monkeypatch.setattr("core.feed.ws_mutation_queue.safe_subscribe_full_mode", mock_safe_subscribe_full_mode)

    monkeypatch.setattr(ws, "_KITE_TICKER", _DummyTicker(), raising=False)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [11, 22, 33, 44], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", list(range(1, 40)), raising=False)
    monkeypatch.setattr(ws, "_RUNTIME_STATE", "RUNNING", raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 100.0, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {11, 22, 33}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {11: "NIFTY", 22: "BANKNIFTY", 33: "SENSEX"}, raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    monkeypatch.delenv("FEED_USE_DESIRED_TOKENS", raising=False)

    assert ws._soft_resubscribe_current(reason="unit_test_flag_off") is True
    assert calls["subscribe"] == [[11, 22, 33, 44]]
    assert calls["set_mode"] == [[11, 22, 33, 44]]
    assert events[-1][0] == "FEED_MUTATION_APPLIED"
    assert events[-1][1]["desired_tokens_count"] == 39
    assert events[-1][1]["fallback_option_tokens_count"] == 1
    assert events[-1][1]["auto_recover_missing_options"] is False
    assert events[-1][1]["resubscribe_tokens_count"] == 4


def test_soft_resubscribe_auto_recovers_desired_tokens_when_current_is_underlyings_only(monkeypatch):
    calls = {"subscribe": [], "set_mode": []}
    events = []

    class _DummyTicker:
        MODE_FULL = "full"
        connected = True

        def is_connected(self):
            return True

    def mock_safe_subscribe_full_mode(ws_obj, tokens, reason, now_epoch, on_applied_callback=None):
            calls["subscribe"].append(list(tokens))
            calls["set_mode"].append(list(tokens))
            if on_applied_callback: on_applied_callback()
            res = type("WsMutationResult", (), {"ok": True, "applied": True, "queued": False, "failure_reason": ""})()
            return res, res
        
    monkeypatch.setattr("core.feed.ws_mutation_queue.safe_subscribe_full_mode", mock_safe_subscribe_full_mode)

    monkeypatch.setattr(ws, "_KITE_TICKER", _DummyTicker(), raising=False)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [11, 22, 33], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", list(range(1, 40)), raising=False)
    monkeypatch.setattr(ws, "_RUNTIME_STATE", "RUNNING", raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 100.0, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {11, 22, 33}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {11: "NIFTY", 22: "BANKNIFTY", 33: "SENSEX"}, raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    monkeypatch.delenv("FEED_USE_DESIRED_TOKENS", raising=False)

    assert ws._soft_resubscribe_current(reason="unit_test_auto_recover") is True
    assert calls["subscribe"] == [list(range(1, 40))]
    assert calls["set_mode"] == [list(range(1, 40))]
    assert events[-1][0] == "FEED_MUTATION_APPLIED"
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

    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
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

    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
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


def test_restart_verification_pending_when_start_handoff_succeeds_but_no_connect_or_ticks(monkeypatch, tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(cfg, "FEED_RUNTIME_STATUS_OVERLAY_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "FEED_RESTART_VERIFY_TIMEOUT_SEC", 5.0, raising=False)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)

    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    ws._reset_feed_restart_verification(reason="unit_test_setup")

    monkeypatch.setattr(ws, "_LAST_TOKENS", [1, 101], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", [1, 101], raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {1}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {1: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {1: "NIFTY", 101: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_LAST_OPTION_COUNTS_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(ws, "_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(ws, "_LAST_MSG_TS_BY_TOKEN", {}, raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 0.0, raising=False)
    monkeypatch.setattr(ws, "_DEPTH_WS_START_EPOCH", 1000.0, raising=False)
    monkeypatch.setattr(ws, "_RUNTIME_STATE", "RUNNING", raising=False)
    monkeypatch.setattr(ws, "_AUTH_REQUIRED_LATCH", False, raising=False)
    monkeypatch.setattr(ws, "_STOP_REQUESTED", False, raising=False)
    monkeypatch.setattr(ws, "_FULL_RESTARTS", [], raising=False)
    monkeypatch.setattr(ws, "_LAST_FULL_RESTART_EPOCH", 0.0, raising=False)
    monkeypatch.setattr(ws, "_STALE_STRIKES", 0, raising=False)
    monkeypatch.setattr(ws, "feed_breaker_tripped", lambda: False)
    monkeypatch.setattr(ws.feed_restart_guard, "allow_restart", lambda **kwargs: True)
    monkeypatch.setattr(cfg, "DEPTH_WS_USE_INTERNAL_RECONNECT", False, raising=False)
    monkeypatch.setattr(cfg, "FEED_FULL_RESTART_COOLDOWN_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_MAX_FULL_RESTARTS_PER_HOUR", 6, raising=False)
    monkeypatch.setattr(ws.time, "time", lambda: 1000.0)

    monkeypatch.setattr(ws, "_persist_runtime_snapshot_row", lambda **kwargs: None)
    monkeypatch.setattr(ws, "stop_depth_ws", lambda reason="manual_stop": None)

    def _start(tokens, profile_verified=False, **kwargs):
        ws._DEPTH_WS_START_EPOCH = 1000.0
        return True

    monkeypatch.setattr(ws, "start_depth_ws", _start)

    assert ws.restart_depth_ws(reason="ws_error:1006", ignore_cooldown=True, force_full_restart=True) is True

    ws._write_feed_runtime_snapshot(
        now_epoch=1000.0,
        ws_connected=None,
        subscribed_tokens_count=2,
        intended_tokens_count=2,
        last_db_tick_epoch=None,
        last_db_tick_age_sec=None,
        last_ws_tick_epoch=None,
        last_tick_age_sec=None,
        last_depth_epoch=None,
        last_depth_age_sec=None,
        market_open=True,
        state_machine={"state": "LIVE", "reason": "ticks_flowing"},
        runtime_state="RUNNING",
        last_error="",
    )

    payload = _read_feed_runtime_latest(tmp_path)
    assert payload["runtime_state"] == "RESTART_VERIFY_PENDING"
    assert "FEED_RESTART_VERIFIED_OK" not in [event for event, _payload in events]
    ws._reset_feed_restart_verification(reason="unit_test_teardown")


def test_restart_verification_emits_verified_ok_only_after_connect_subscribe_and_option_tick(monkeypatch, tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(cfg, "FEED_RUNTIME_STATUS_OVERLAY_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "FEED_RESTART_VERIFY_TIMEOUT_SEC", 5.0, raising=False)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)

    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    ws._reset_feed_restart_verification(reason="unit_test_setup")

    monkeypatch.setattr(ws, "_LAST_TOKENS", [1, 101], raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {1}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {1: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {1: "NIFTY", 101: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_LAST_OPTION_COUNTS_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(ws, "_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(ws, "_LAST_MSG_TS_BY_TOKEN", {101: 1001.0}, raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 1001.0, raising=False)
    monkeypatch.setattr(ws, "_DEPTH_WS_START_EPOCH", 1000.0, raising=False)
    monkeypatch.setattr(ws, "_ws_connected_state", lambda: True, raising=False)
    monkeypatch.setattr(ws, "_RUNTIME_STATE", "RUNNING", raising=False)

    ws._begin_feed_restart_verification(reason="ws_error:1006", start_epoch=1000.0, now_epoch=1000.0)
    ws._record_feed_restart_verify_connect(now_epoch=1000.5)
    ws._record_feed_restart_verify_subscribe(now_epoch=1000.6)

    ws._write_feed_runtime_snapshot(
        now_epoch=1001.0,
        ws_connected=True,
        subscribed_tokens_count=2,
        intended_tokens_count=2,
        last_db_tick_epoch=None,
        last_db_tick_age_sec=None,
        last_ws_tick_epoch=1001.0,
        last_tick_age_sec=0.0,
        last_depth_epoch=None,
        last_depth_age_sec=None,
        market_open=True,
        state_machine={"state": "LIVE", "reason": "ticks_flowing"},
        runtime_state="RUNNING",
        last_error="",
    )

    payload = _read_feed_runtime_latest(tmp_path)
    assert payload["runtime_state"] == "RUNNING"
    assert "FEED_RESTART_VERIFIED_OK" in [event for event, _payload in events]
    ws._reset_feed_restart_verification(reason="unit_test_teardown")


def test_restart_verification_timeout_emits_failed_and_blocks(monkeypatch, tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(cfg, "FEED_RUNTIME_STATUS_OVERLAY_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "FEED_RESTART_VERIFY_TIMEOUT_SEC", 1.0, raising=False)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)

    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    ws._reset_feed_restart_verification(reason="unit_test_setup")

    monkeypatch.setattr(ws, "_LAST_TOKENS", [1, 101], raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {1}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {1: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {1: "NIFTY", 101: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_LAST_OPTION_COUNTS_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(ws, "_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(ws, "_LAST_MSG_TS_BY_TOKEN", {}, raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 0.0, raising=False)
    monkeypatch.setattr(ws, "_DEPTH_WS_START_EPOCH", 1000.0, raising=False)
    monkeypatch.setattr(ws, "_RUNTIME_STATE", "RUNNING", raising=False)

    ws._begin_feed_restart_verification(reason="ws_error:1006", start_epoch=1000.0, now_epoch=1000.0)

    ws._write_feed_runtime_snapshot(
        now_epoch=1002.0,
        ws_connected=None,
        subscribed_tokens_count=2,
        intended_tokens_count=2,
        last_db_tick_epoch=None,
        last_db_tick_age_sec=None,
        last_ws_tick_epoch=None,
        last_tick_age_sec=None,
        last_depth_epoch=None,
        last_depth_age_sec=None,
        market_open=True,
        state_machine={"state": "LIVE", "reason": "ticks_flowing"},
        runtime_state="RUNNING",
        last_error="",
    )

    payload = _read_feed_runtime_latest(tmp_path)
    assert payload["runtime_state"] == "RESTART_VERIFY_FAILED"
    assert "FEED_RESTART_VERIFY_FAILED" in [event for event, _payload in events]
    ws._reset_feed_restart_verification(reason="unit_test_teardown")


def test_restart_verification_failed_state_can_recover_after_fresh_proof(monkeypatch, tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(cfg, "FEED_RUNTIME_STATUS_OVERLAY_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "FEED_RESTART_VERIFY_TIMEOUT_SEC", 1.0, raising=False)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)

    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    ws._reset_feed_restart_verification(reason="unit_test_setup")

    monkeypatch.setattr(ws, "_LAST_TOKENS", [1, 101], raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {1}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {1: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {1: "NIFTY", 101: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_LAST_OPTION_COUNTS_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(ws, "_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(ws, "_LAST_MSG_TS_BY_TOKEN", {101: 1003.0}, raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 1003.0, raising=False)
    monkeypatch.setattr(ws, "_DEPTH_WS_START_EPOCH", 1000.0, raising=False)
    monkeypatch.setattr(ws, "_ws_connected_state", lambda: True, raising=False)
    monkeypatch.setattr(ws, "_RUNTIME_STATE", "RUNNING", raising=False)

    ws._begin_feed_restart_verification(reason="ws_error:1006", start_epoch=1000.0, now_epoch=1000.0)
    monkeypatch.setattr(ws, "_FEED_RESTART_VERIFY_STATE", "FAILED", raising=False)
    monkeypatch.setattr(ws, "_FEED_RESTART_VERIFY_FAILURE_DETAIL", "timeout", raising=False)

    ws._write_feed_runtime_snapshot(
        now_epoch=1003.0,
        ws_connected=True,
        subscribed_tokens_count=2,
        intended_tokens_count=2,
        last_db_tick_epoch=None,
        last_db_tick_age_sec=None,
        last_ws_tick_epoch=1003.0,
        last_tick_age_sec=0.0,
        last_depth_epoch=None,
        last_depth_age_sec=None,
        market_open=True,
        state_machine={"state": "LIVE", "reason": "ticks_flowing"},
        runtime_state="RUNNING",
        last_error="",
    )
    recovered_payload = _read_feed_runtime_latest(tmp_path)
    assert recovered_payload["runtime_state"] == "RUNNING"
    assert "FEED_RESTART_VERIFIED_OK" in [event for event, _payload in events]
    ws._reset_feed_restart_verification(reason="unit_test_teardown")


def test_restart_verification_clears_ws1006_recovery_blocked_metadata_on_success(monkeypatch, tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(cfg, "FEED_RUNTIME_STATUS_OVERLAY_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "FEED_RESTART_VERIFY_TIMEOUT_SEC", 5.0, raising=False)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)

    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    ws._reset_feed_restart_verification(reason="unit_test_setup")

    monkeypatch.setattr(ws, "_LAST_TOKENS", [1, 101], raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {1}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {1: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {1: "NIFTY", 101: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_LAST_OPTION_COUNTS_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(ws, "_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(ws, "_LAST_MSG_TS_BY_TOKEN", {101: 1001.0}, raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 1001.0, raising=False)
    monkeypatch.setattr(ws, "_DEPTH_WS_START_EPOCH", 1000.0, raising=False)
    monkeypatch.setattr(ws, "_RUNTIME_STATE", "RECOVERY_BLOCKED", raising=False)
    monkeypatch.setattr(ws, "_RECONNECT_BLOCKED_REASON", "ws1006_process_restart_required", raising=False)

    ws._begin_feed_restart_verification(reason="ws_error:1006", start_epoch=1000.0, now_epoch=1000.0)
    ws._record_feed_restart_verify_connect(now_epoch=1000.5)
    ws._record_feed_restart_verify_subscribe(now_epoch=1000.6)

    monkeypatch.setattr(
        ws,
        "_restart_verification_proof",
        lambda now_epoch: (True, "ok", {"source": "unit_test"}),
    )

    ws._tick_feed_restart_verification(now_epoch=1001.0)

    assert ws._reconnect_recovery_blocked_active() is False
    assert "FEED_RECONNECT_RECOVERY_CLEARED" in [event for event, _payload in events]
    ws._persist_runtime_snapshot_row(
        ws_connected=True,
        source="unit_test_recovered_ticks",
        now_epoch=1001.0,
        runtime_state="RUNNING",
        last_error="",
    )
    payload = json.loads((logs_path / "feed_runtime_latest.json").read_text(encoding="utf-8"))
    assert payload["reconnect_blocked_reason"] in {"", None}
    assert payload["runtime_state"] == "RUNNING"
    assert payload["state_machine"]["state"] == "LIVE"
    assert payload["state_machine"]["reason"] == "ticks_flowing"
    ws._reset_feed_restart_verification(reason="unit_test_teardown")


def test_restart_verification_does_not_call_broker_or_order_paths(monkeypatch, tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(cfg, "FEED_RUNTIME_STATUS_OVERLAY_ENABLE", False, raising=False)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    ws._reset_feed_restart_verification(reason="unit_test_setup")

    monkeypatch.setattr(ws.kite_client, "ensure", lambda: (_ for _ in ()).throw(AssertionError("broker_called")), raising=False)

    monkeypatch.setattr(ws, "_LAST_TOKENS", [1, 101], raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {1}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {1: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {1: "NIFTY", 101: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_LAST_OPTION_COUNTS_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(ws, "_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(ws, "_LAST_MSG_TS_BY_TOKEN", {101: 1001.0}, raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 1001.0, raising=False)
    monkeypatch.setattr(ws, "_DEPTH_WS_START_EPOCH", 1000.0, raising=False)
    monkeypatch.setattr(ws, "_RUNTIME_STATE", "RUNNING", raising=False)

    ws._begin_feed_restart_verification(reason="ws_error:1006", start_epoch=1000.0, now_epoch=1000.0)
    ws._record_feed_restart_verify_connect(now_epoch=1000.5)
    ws._record_feed_restart_verify_subscribe(now_epoch=1000.6)

    ws._write_feed_runtime_snapshot(
        now_epoch=1001.0,
        ws_connected=True,
        subscribed_tokens_count=2,
        intended_tokens_count=2,
        last_db_tick_epoch=None,
        last_db_tick_age_sec=None,
        last_ws_tick_epoch=1001.0,
        last_tick_age_sec=0.0,
        last_depth_epoch=None,
        last_depth_age_sec=None,
        market_open=True,
        state_machine={"state": "LIVE", "reason": "ticks_flowing"},
        runtime_state="RUNNING",
        last_error="",
    )
    ws._reset_feed_restart_verification(reason="unit_test_teardown")


def test_tick_stalled_watchdog_cycle_escalates_to_forced_full_restart(monkeypatch):
    monkeypatch.setattr(ws, "_STALE_STRIKES", 1, raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 0.0, raising=False)
    monkeypatch.setattr(ws, "_latest_db_tick_epoch", lambda: 90.0)

    calls = {"kwargs": None}

    def _restart_cb(**kwargs):
        calls["kwargs"] = dict(kwargs)
        return True

    hb = ws._run_db_tick_watchdog_cycle(
        now_epoch=100.0,
        market_open=True,
        stale_restart_sec=5.0,
        reset_sec=0.0,
        strikes_to_restart=2,
        restart_cb=_restart_cb,
    )

    assert hb["restarted"] is True
    assert calls["kwargs"]["reason"] == "tick_stalled"
    assert calls["kwargs"]["ignore_cooldown"] is True
    assert calls["kwargs"]["force_full_restart"] is True


def test_hard_feed_dead_no_ticks_ignores_cooldown_and_forces_full_restart(monkeypatch):
    monkeypatch.setattr(ws, "_LAST_TOKENS", [123, 456], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", [123, 456], raising=False)
    monkeypatch.setattr(ws, "_FULL_RESTARTS", [], raising=False)
    monkeypatch.setattr(ws, "_LAST_FULL_RESTART_EPOCH", 1000.0, raising=False)
    monkeypatch.setattr(ws, "_AUTH_REQUIRED_LATCH", False, raising=False)
    monkeypatch.setattr(ws, "_STOP_REQUESTED", False, raising=False)
    monkeypatch.setattr(ws, "_STALE_STRIKES", 0, raising=False)
    monkeypatch.setattr(ws, "feed_breaker_tripped", lambda: False)
    monkeypatch.setattr(ws.feed_restart_guard, "allow_restart", lambda **kwargs: True)
    monkeypatch.setattr(cfg, "FEED_FULL_RESTART_COOLDOWN_SEC", 9999.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_MAX_FULL_RESTARTS_PER_HOUR", 6, raising=False)

    class _ConnectedTicker:
        def is_connected(self):
            return True

    monkeypatch.setattr(ws, "_KITE_TICKER", _ConnectedTicker(), raising=False)
    monkeypatch.setattr(cfg, "DEPTH_WS_USE_INTERNAL_RECONNECT", True, raising=False)

    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))

    calls = {"stop": 0, "start": 0, "soft": 0}
    monkeypatch.setattr(
        ws,
        "stop_depth_ws",
        lambda reason="manual_stop": calls.__setitem__("stop", calls["stop"] + 1),
    )
    monkeypatch.setattr(
        ws,
        "start_depth_ws",
        lambda tokens, profile_verified=False, **kwargs: calls.__setitem__("start", calls["start"] + 1) or True,
    )
    monkeypatch.setattr(
        ws,
        "_soft_resubscribe_current",
        lambda reason: calls.__setitem__("soft", calls["soft"] + 1) or True,
    )
    monkeypatch.setattr(ws.time, "time", lambda: 1001.0)

    assert (
        ws.restart_depth_ws(
            reason="no_ticks_age=11.0s",
            ignore_cooldown=True,
            force_full_restart=True,
        )
        is True
    )
    assert calls["stop"] == 1
    assert calls["start"] == 1
    assert calls["soft"] == 0
    assert "FEED_RESTART_FORCE_FULL_PATH" in [event for event, _payload in events]


def test_hard_feed_dead_depth_stale_ignores_cooldown_and_forces_full_restart(monkeypatch):
    monkeypatch.setattr(ws, "_LAST_TOKENS", [123, 456], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", [123, 456], raising=False)
    monkeypatch.setattr(ws, "_FULL_RESTARTS", [], raising=False)
    monkeypatch.setattr(ws, "_LAST_FULL_RESTART_EPOCH", 1000.0, raising=False)
    monkeypatch.setattr(ws, "_AUTH_REQUIRED_LATCH", False, raising=False)
    monkeypatch.setattr(ws, "_STOP_REQUESTED", False, raising=False)
    monkeypatch.setattr(ws, "_STALE_STRIKES", 0, raising=False)
    monkeypatch.setattr(ws, "feed_breaker_tripped", lambda: False)
    monkeypatch.setattr(ws.feed_restart_guard, "allow_restart", lambda **kwargs: True)
    monkeypatch.setattr(cfg, "FEED_FULL_RESTART_COOLDOWN_SEC", 9999.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_MAX_FULL_RESTARTS_PER_HOUR", 6, raising=False)

    class _ConnectedTicker:
        def is_connected(self):
            return True

    monkeypatch.setattr(ws, "_KITE_TICKER", _ConnectedTicker(), raising=False)
    monkeypatch.setattr(cfg, "DEPTH_WS_USE_INTERNAL_RECONNECT", True, raising=False)

    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))

    calls = {"stop": 0, "start": 0, "soft": 0}
    monkeypatch.setattr(
        ws,
        "stop_depth_ws",
        lambda reason="manual_stop": calls.__setitem__("stop", calls["stop"] + 1),
    )
    monkeypatch.setattr(
        ws,
        "start_depth_ws",
        lambda tokens, profile_verified=False, **kwargs: calls.__setitem__("start", calls["start"] + 1) or True,
    )
    monkeypatch.setattr(
        ws,
        "_soft_resubscribe_current",
        lambda reason: calls.__setitem__("soft", calls["soft"] + 1) or True,
    )
    monkeypatch.setattr(ws.time, "time", lambda: 1001.0)

    assert (
        ws.restart_depth_ws(
            reason="depth_stale_age=9.9s",
            ignore_cooldown=True,
            force_full_restart=True,
        )
        is True
    )
    assert calls["stop"] == 1
    assert calls["start"] == 1
    assert calls["soft"] == 0
    assert "FEED_RESTART_FORCE_FULL_PATH" in [event for event, _payload in events]


def test_market_open_option_subscriptions_missing_forces_full_restart(monkeypatch):
    monkeypatch.setattr(ws, "_LAST_TOKENS", [123, 456], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", [123, 456], raising=False)
    monkeypatch.setattr(ws, "_FULL_RESTARTS", [], raising=False)
    monkeypatch.setattr(ws, "_LAST_FULL_RESTART_EPOCH", 0.0, raising=False)
    monkeypatch.setattr(ws, "_AUTH_REQUIRED_LATCH", False, raising=False)
    monkeypatch.setattr(ws, "_STOP_REQUESTED", False, raising=False)
    monkeypatch.setattr(ws, "_STALE_STRIKES", 0, raising=False)
    monkeypatch.setattr(ws, "feed_breaker_tripped", lambda: False)
    monkeypatch.setattr(ws.feed_restart_guard, "allow_restart", lambda **kwargs: True)
    monkeypatch.setattr(cfg, "FEED_FULL_RESTART_COOLDOWN_SEC", 9999.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_MAX_FULL_RESTARTS_PER_HOUR", 6, raising=False)

    class _ConnectedTicker:
        def is_connected(self):
            return True

    monkeypatch.setattr(ws, "_KITE_TICKER", _ConnectedTicker(), raising=False)
    monkeypatch.setattr(cfg, "DEPTH_WS_USE_INTERNAL_RECONNECT", True, raising=False)

    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))

    calls = {"stop": 0, "start": 0}
    monkeypatch.setattr(
        ws,
        "stop_depth_ws",
        lambda reason="manual_stop": calls.__setitem__("stop", calls["stop"] + 1),
    )
    monkeypatch.setattr(
        ws,
        "start_depth_ws",
        lambda tokens, profile_verified=False, **kwargs: calls.__setitem__("start", calls["start"] + 1) or True,
    )

    def _soft(reason):
        raise AssertionError("soft_path_used_for_hard_feed_dead_restart")

    monkeypatch.setattr(ws, "_soft_resubscribe_current", _soft)
    monkeypatch.setattr(ws.time, "time", lambda: 1001.0)

    assert (
        ws.restart_depth_ws(
            reason="market_open_option_subscriptions_missing",
            ignore_cooldown=True,
            force_full_restart=True,
        )
        is True
    )
    assert calls == {"stop": 1, "start": 1}
    assert "FEED_RESTART_FORCE_FULL_PATH" in [event for event, _payload in events]


def test_repeated_hard_restarts_trip_storm_breaker(monkeypatch):
    monkeypatch.setattr(ws, "_LAST_TOKENS", [123, 456], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", [123, 456], raising=False)
    monkeypatch.setattr(ws, "_AUTH_REQUIRED_LATCH", False, raising=False)
    monkeypatch.setattr(ws, "_STOP_REQUESTED", False, raising=False)
    monkeypatch.setattr(ws, "_STALE_STRIKES", 0, raising=False)
    monkeypatch.setattr(ws, "_LAST_FULL_RESTART_EPOCH", 0.0, raising=False)
    monkeypatch.setattr(ws, "_FULL_RESTARTS", [900.0, 901.0], raising=False)
    monkeypatch.setattr(ws, "feed_breaker_tripped", lambda: False)
    monkeypatch.setattr(ws.feed_restart_guard, "allow_restart", lambda **kwargs: True)
    monkeypatch.setattr(cfg, "FEED_FULL_RESTART_COOLDOWN_SEC", 9999.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_MAX_FULL_RESTARTS_PER_HOUR", 99, raising=False)
    monkeypatch.setattr(cfg, "FEED_RESTART_STORM_TRIP", 2, raising=False)

    calls = {"breaker": 0, "risk": 0}
    monkeypatch.setattr(ws, "trip_feed_breaker", lambda **kwargs: calls.__setitem__("breaker", calls["breaker"] + 1))
    monkeypatch.setattr(ws.risk_halt, "set_halt", lambda *_a, **_k: calls.__setitem__("risk", calls["risk"] + 1))

    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    monkeypatch.setattr(ws.time, "time", lambda: 902.0)

    assert (
        ws.restart_depth_ws(
            reason="no_ticks_age=20.0s",
            ignore_cooldown=True,
            force_full_restart=True,
        )
        is False
    )
    assert "FEED_RESTART_STORM_TRIP" in [event for event, _payload in events]
    assert calls["breaker"] == 1
    assert calls["risk"] == 1


def test_auth_required_latch_blocks_hard_restart(monkeypatch):
    monkeypatch.setattr(ws, "_AUTH_REQUIRED_LATCH", True, raising=False)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [123, 456], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", [123, 456], raising=False)

    calls = {"stop": 0, "start": 0}
    monkeypatch.setattr(
        ws,
        "stop_depth_ws",
        lambda reason="manual_stop": calls.__setitem__("stop", calls["stop"] + 1),
    )
    monkeypatch.setattr(
        ws,
        "start_depth_ws",
        lambda tokens, profile_verified=False, **kwargs: calls.__setitem__("start", calls["start"] + 1) or True,
    )

    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))

    assert (
        ws.restart_depth_ws(
            reason="depth_stale_age=99.0s",
            ignore_cooldown=True,
            force_full_restart=True,
        )
        is False
    )
    assert calls == {"stop": 0, "start": 0}
    assert "FEED_RESTART_BLOCKED_AUTH_REQUIRED" in [event for event, _payload in events]


def test_storm_breaker_trips_on_velocity(monkeypatch):
    from core import kite_depth_ws as ws
    from config import config as cfg

    monkeypatch.setattr(ws, "_LAST_TOKENS", [123, 456], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", [123, 456], raising=False)
    monkeypatch.setattr(ws, "_AUTH_REQUIRED_LATCH", False, raising=False)
    monkeypatch.setattr(ws, "_STOP_REQUESTED", False, raising=False)
    monkeypatch.setattr(ws, "_STALE_STRIKES", 0, raising=False)
    monkeypatch.setattr(ws, "_LAST_FULL_RESTART_EPOCH", 0.0, raising=False)
    
    # 4 restarts within 5 minutes (300s). e.g., 0, 100, 200, 250.
    # Current time = 299
    monkeypatch.setattr(ws, "_FULL_RESTARTS", [0.0, 100.0, 200.0, 250.0], raising=False)
    monkeypatch.setattr(ws, "feed_breaker_tripped", lambda: False)
    monkeypatch.setattr(ws.feed_restart_guard, "allow_restart", lambda **kwargs: True)
    
    monkeypatch.setattr(cfg, "FEED_FULL_RESTART_COOLDOWN_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_MAX_FULL_RESTARTS_PER_HOUR", 99, raising=False)
    monkeypatch.setattr(cfg, "FEED_RESTART_STORM_TRIP", 4, raising=False)
    monkeypatch.setattr(cfg, "FEED_RESTART_STORM_WINDOW_SEC", 300.0, raising=False)

    calls = {"breaker": 0, "risk": 0}
    monkeypatch.setattr(ws, "trip_feed_breaker", lambda **kwargs: calls.__setitem__("breaker", calls["breaker"] + 1))
    monkeypatch.setattr(ws.risk_halt, "set_halt", lambda *_a, **_k: calls.__setitem__("risk", calls["risk"] + 1))

    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    monkeypatch.setattr(ws.time, "time", lambda: 299.0)

    # 5th restart attempt should fail because there are already 4 in the 300s window.
    assert ws.restart_depth_ws(reason="velocity_trip", ignore_cooldown=True, force_full_restart=True) is False
    assert "FEED_RESTART_STORM_TRIP" in [event for event, _payload in events]
    assert calls["breaker"] == 1


def test_storm_breaker_allows_restarts_over_long_window(monkeypatch):
    from core import kite_depth_ws as ws
    from config import config as cfg

    monkeypatch.setattr(ws, "_LAST_TOKENS", [123, 456], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", [123, 456], raising=False)
    monkeypatch.setattr(ws, "_AUTH_REQUIRED_LATCH", False, raising=False)
    monkeypatch.setattr(ws, "_STOP_REQUESTED", False, raising=False)
    monkeypatch.setattr(ws, "_STALE_STRIKES", 0, raising=False)
    monkeypatch.setattr(ws, "_LAST_FULL_RESTART_EPOCH", 0.0, raising=False)
    
    # 6 restarts, but spread out over 2 hours (120 minutes)
    monkeypatch.setattr(ws, "_FULL_RESTARTS", [0.0, 1000.0, 2000.0, 3000.0, 4000.0, 5000.0], raising=False)
    monkeypatch.setattr(ws, "feed_breaker_tripped", lambda: False)
    monkeypatch.setattr(ws.feed_restart_guard, "allow_restart", lambda **kwargs: True)
    
    monkeypatch.setattr(cfg, "FEED_FULL_RESTART_COOLDOWN_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_MAX_FULL_RESTARTS_PER_HOUR", 99, raising=False)
    monkeypatch.setattr(cfg, "FEED_RESTART_STORM_TRIP", 4, raising=False)
    monkeypatch.setattr(cfg, "FEED_RESTART_STORM_WINDOW_SEC", 300.0, raising=False)

    calls = {"breaker": 0, "risk": 0}
    monkeypatch.setattr(ws, "trip_feed_breaker", lambda **kwargs: calls.__setitem__("breaker", calls["breaker"] + 1))
    monkeypatch.setattr(ws.risk_halt, "set_halt", lambda *_a, **_k: calls.__setitem__("risk", calls["risk"] + 1))

    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    
    # Current time is 5010.
    # In the last 300 seconds (4710 to 5010), there is only 1 restart (5000.0).
    monkeypatch.setattr(ws.time, "time", lambda: 5010.0)

    # We mock stop and start to return True to ensure it proceeds past the gates
    monkeypatch.setattr(ws, "stop_depth_ws", lambda **kwargs: True)
    monkeypatch.setattr(ws, "start_depth_ws", lambda **kwargs: True)

    ws.restart_depth_ws(reason="long_window", ignore_cooldown=True, force_full_restart=True)
    assert "FEED_RESTART_STORM_TRIP" not in [event for event, _payload in events]
    assert calls["breaker"] == 0
    assert "FEED_FULL_RESTART_BEGIN" in [event for event, _payload in events]


def test_hourly_cap_rate_limits_safely(monkeypatch):
    from core import kite_depth_ws as ws
    from config import config as cfg

    monkeypatch.setattr(ws, "_LAST_TOKENS", [123, 456], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", [123, 456], raising=False)
    monkeypatch.setattr(ws, "_AUTH_REQUIRED_LATCH", False, raising=False)
    monkeypatch.setattr(ws, "_STOP_REQUESTED", False, raising=False)
    monkeypatch.setattr(ws, "_STALE_STRIKES", 0, raising=False)
    monkeypatch.setattr(ws, "_LAST_FULL_RESTART_EPOCH", 0.0, raising=False)
    
    # 6 restarts, spread out within an hour
    monkeypatch.setattr(ws, "_FULL_RESTARTS", [0.0, 500.0, 1000.0, 1500.0, 2000.0, 2500.0], raising=False)
    monkeypatch.setattr(ws, "feed_breaker_tripped", lambda: False)
    monkeypatch.setattr(ws.feed_restart_guard, "allow_restart", lambda **kwargs: True)
    
    monkeypatch.setattr(cfg, "FEED_FULL_RESTART_COOLDOWN_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_MAX_FULL_RESTARTS_PER_HOUR", 6, raising=False)
    monkeypatch.setattr(cfg, "FEED_RESTART_STORM_TRIP", 4, raising=False)
    monkeypatch.setattr(cfg, "FEED_RESTART_STORM_WINDOW_SEC", 300.0, raising=False)

    calls = {"breaker": 0, "risk": 0}
    monkeypatch.setattr(ws, "trip_feed_breaker", lambda **kwargs: calls.__setitem__("breaker", calls["breaker"] + 1))
    monkeypatch.setattr(ws.risk_halt, "set_halt", lambda *_a, **_k: calls.__setitem__("risk", calls["risk"] + 1))

    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    
    # Current time is 2510.
    # In the last 300s (2210 to 2510), there is only 1 restart (2500.0), so storm breaker doesn't trip.
    # But total in last hour (3600s) is 6, which >= max_per_hour (6).
    monkeypatch.setattr(ws.time, "time", lambda: 2510.0)

    assert ws.restart_depth_ws(reason="hourly_cap", ignore_cooldown=True, force_full_restart=True) is False
    assert "FEED_RESTART_STORM_TRIP" not in [event for event, _payload in events]
    assert calls["breaker"] == 0
    assert "FEED_RESTART_RATE_LIMIT_HOURLY" in [event for event, _payload in events]

def test_feed_recovery_coordinator_singleton_identity_preserved_across_reset():
    from core.feed_recovery_coordinator import get_feed_recovery_coordinator
    import core.kite_depth_ws
    
    coord1 = get_feed_recovery_coordinator()
    coord2 = core.kite_depth_ws.get_feed_recovery_coordinator()
    
    assert coord1 is coord2
    
    coord1.reset()
    
    coord3 = get_feed_recovery_coordinator()
    coord4 = core.kite_depth_ws.get_feed_recovery_coordinator()
    
    assert coord1 is coord3
    assert coord1 is coord4
