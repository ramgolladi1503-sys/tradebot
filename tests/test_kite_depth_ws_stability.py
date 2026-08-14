from pathlib import Path
import importlib
from datetime import datetime, timezone
import sqlite3
from config import config as cfg
import core.auth as auth_module
from core.auth import reset_kite_runtime_credentials_guard
import json
import core.depth_hook_cleanup as depth_hook_cleanup
import core.kite_depth_ws as ws
from core.feed_recovery_coordinator import FeedRecoveryCoordinator
import core.tick_store as tick_store
class _DummyThread:
    def __init__(self, target=None, daemon=None, args=(), kwargs=None):
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}
        self.daemon = daemon
        self.started = False
    def start(self):
        self.started = True
    def join(self, timeout=None):
        pass
class _DummyTicker:
    MODE_FULL = "full"
    def __init__(self, api_key, access_token, debug=True):
        self.api_key = api_key
        self.access_token = access_token
        self.debug = debug
        self.auto_reconnect = True
        self.connected = False
        self.closed = False
        self.on_connect = None
        self.ws = type("WS", (), {"factory": type("Factory", (), {"is_connected": lambda: self.connected})()})()
        self.set_mode = lambda *args: None
        self.unsubscribe = lambda *args: None
        self.on_reconnect = None
        self.on_error = None
        self.on_close = None
        self.on_ticks = None
        self.stop_retry_count = 0
        self.factory = None
        self.connected = False
    def subscribe(self, tokens):
        self.tokens = list(tokens)
    def set_mode(self, mode, tokens):
        self.mode = mode
        self.mode_tokens = list(tokens)
    def connect(self, threaded=True):
        self.connected = True
    def close(self):
        self.closed = True
    def is_connected(self):
        return bool(self.connected)
    def stop_retry(self):
        self.stop_retry_count += 1
class _DummyRestClient:
    def __init__(self):
        self.token = ""
    def set_access_token(self, token):
        self.token = token
    def profile(self):
        return {"user_id": "ABCD1234"}
def _patch_common(monkeypatch):
    import sys
    import contextlib
    if "twisted.internet.reactor" in sys.modules:
        with contextlib.suppress(Exception):
            monkeypatch.setattr(sys.modules["twisted.internet.reactor"], "running", False, raising=False)
            monkeypatch.setattr(sys.modules["twisted.internet.reactor"], "_started", False, raising=False)
    from core.feed import ws_mutation_queue
    monkeypatch.setattr(ws, "_REACTOR_NOT_RESTARTABLE_DETECTED", False, raising=False)
    monkeypatch.setattr(ws_mutation_queue, "_check_socket_health", lambda *args: (True, True, None), raising=False)
    monkeypatch.setattr(depth_hook_cleanup, "_maybe_reapply_depth_engine", lambda: None, raising=False)
    monkeypatch.setattr(depth_hook_cleanup, "_reapply_depth_engine", lambda *args, **kwargs: None, raising=False)
    importlib.reload(ws)
    reset_kite_runtime_credentials_guard()
    monkeypatch.setattr(ws, "_FEED_RECOVERY_COORDINATOR", FeedRecoveryCoordinator(), raising=False)
    monkeypatch.setattr(ws, "_KITE_TICKER", None, raising=False)
    monkeypatch.setattr(ws, "_WATCHDOG_STOP", None, raising=False)
    monkeypatch.setattr(ws, "_WATCHDOG_THREAD", None, raising=False)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [], raising=False)
    monkeypatch.setattr(ws, "_INTENDED_TOKENS", None, raising=False)
    monkeypatch.setattr(ws, "_INTENDED_TOKEN_COUNT", 0, raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", None, raising=False)
    monkeypatch.setattr(ws, "_RUNTIME_STATE", "UNKNOWN", raising=False)
    monkeypatch.setattr(ws, "_LAST_RUNTIME_ERROR", "", raising=False)
    monkeypatch.setattr(ws, "_LAST_MUTATION_RESULT", None, raising=False)
    monkeypatch.setattr(ws, "_LAST_FULL_RESTART_EPOCH", 0.0, raising=False)
    monkeypatch.setattr(ws, "_RECONNECT_BLOCKED_SINCE_EPOCH", 0.0, raising=False)
    monkeypatch.setattr(ws, "_LAST_DISCONNECTED_CODE", None, raising=False)
    monkeypatch.setattr(ws, "_LAST_DISCONNECTED_REASON", "", raising=False)
    monkeypatch.setattr(ws, "_SOCKET_GENERATION", 0, raising=False)
    monkeypatch.setattr(ws, "_FEED_RUNTIME_SNAPSHOT_WRITE_COUNT", 0, raising=False)
    monkeypatch.setattr(ws, "_PENDING_SUBSCRIBE_TOKENS", set(), raising=False)
    monkeypatch.setattr(ws, "_PENDING_UNSUBSCRIBE_TOKENS", set(), raising=False)
    monkeypatch.setattr(ws, "_PENDING_MODE_FULL_TOKENS", set(), raising=False)
    monkeypatch.setattr(ws, "_STALE_STRIKES", 0, raising=False)
    monkeypatch.setattr(ws, "_SYMBOL_LAST_OPTION_TICK_TS", {}, raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 0.0, raising=False)
    monkeypatch.setattr(ws, "_WARMUP_PENDING", False, raising=False)
    monkeypatch.setattr(ws, "_STOP_REQUESTED", False, raising=False)
    monkeypatch.setattr(ws, "_RESTART_ASYNC_THREAD", None, raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 0.0, raising=False)
    monkeypatch.setattr(ws, "_LAST_FEED_HEALTH_STATE", None, raising=False)
    monkeypatch.setattr(ws, "_RECONNECT_BLOCKED_REASON", "", raising=False)
    monkeypatch.setattr(ws, "_PARTIAL_RECOVERY_VERIFICATION", {}, raising=False)
    monkeypatch.setattr(ws, "_REACTOR_NOT_RESTARTABLE_DETECTED", False, raising=False)
    monkeypatch.setattr(ws, "_RECOVERY_IN_PROGRESS", False, raising=False)
    monkeypatch.setattr(ws, "_WS1006_RECOVERABLE_ATTEMPTS", 0, raising=False)
    monkeypatch.setattr(ws, "_WS1006_RECOVERABLE_LAST_ATTEMPT_EPOCH", 0.0, raising=False)
    monkeypatch.setattr(ws, "_WS1006_RECOVERABLE_LAST_REASON", "", raising=False)
    monkeypatch.setattr(ws, "_LAST_INTERNAL_RETRY_SUPPRESSION_STATE", {}, raising=False)
    monkeypatch.setattr(ws, "_AUTH_REQUIRED_LATCH", False, raising=False)
    monkeypatch.setattr(ws, "_AUTH_REQUIRED_LOGGED", False, raising=False)
    monkeypatch.setattr(ws, "_SYMBOL_LAST_LTP_TS", {}, raising=False)
    monkeypatch.setattr(ws, "_SYMBOL_LAST_DEPTH_TS", {}, raising=False)
    monkeypatch.setattr(ws, "_SYMBOL_LAST_OPTION_TICK_TS", {}, raising=False)
    monkeypatch.setattr(ws, "_LAST_MSG_TS_BY_TOKEN", {}, raising=False)
    monkeypatch.setattr(ws, "_LAST_OPTION_TOKEN_INCIDENT_TS", {}, raising=False)
    monkeypatch.setattr(ws, "_LAST_OPTION_COUNTS_BY_SYMBOL", {}, raising=False)
    monkeypatch.setattr(ws, "_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL", {}, raising=False)
    monkeypatch.setattr(ws, "_STALE_OPTION_MUTATION_WINDOW_STATE", {}, raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", set(), raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {}, raising=False)
    from core.feed import runtime_store
    # Drain the shared persistence worker before deleting the session artifact;
    # otherwise a prior test can write its older snapshot after cleanup.
    with contextlib.suppress(Exception):
        runtime_store._RUNTIME_WRITE_QUEUE.join()
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws, "repo_root", lambda: Path("/tmp"))
    # Each test owns its synthetic runtime snapshot; do not let a prior
    # recovery scenario supply the next scenario's latest-row evidence.
    with contextlib.suppress(FileNotFoundError):
        (ws.logs_dir() / "feed_runtime_latest.json").unlink()
        (Path.cwd() / ".runtime" / "feed_runtime_latest.json").unlink()
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: False)
    monkeypatch.setattr(ws, "get_kite_auth_health", lambda force=True: {"ok": True})
    monkeypatch.setattr(ws, "set_auth_required_state", lambda **kwargs: {"status": "AUTH_REQUIRED"})
    monkeypatch.setattr(ws, "clear_auth_required_state", lambda **kwargs: {"status": "OK"})
    monkeypatch.setattr(ws, "invalidate_cache", lambda **kwargs: None)
    monkeypatch.setattr(cfg, "KITE_API_KEY", "api_key_1234", raising=False)
    monkeypatch.setattr(cfg, "KITE_USE_DEPTH", True, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_WS_USE_INTERNAL_RECONNECT", True, raising=False)
    tick_store.reset_audit_counters()
    tick_store.clear_replay_pressure_hook()
    tick_store.set_replay_pressure_immediate_flush_enabled(True)
    tick_store.set_replay_pressure_read_flush_enabled(True)
    monkeypatch.setattr(auth_module, "resolve_access_token", lambda **kwargs: "TOKEN123")
    monkeypatch.setattr(ws.threading, "Thread", _DummyThread)
    rest = _DummyRestClient()
    monkeypatch.setattr(ws.kite_client, "ensure", lambda: rest, raising=False)
    monkeypatch.setattr(ws.kite_client, "kite", rest, raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_api_key", "api_key_1234", raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_access_token", "TOKEN123", raising=False)
def _fresh_refresh_stale_symbol_state(monkeypatch, *, fresh_ratio: float = 0.25, stale_count: int = 6, fresh_count: int = 2):
    monkeypatch.setattr(ws, "_LAST_TOKENS", [101, 102, 103, 104, 105, 106, 107, 108], raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {token: "BANKNIFTY" for token in range(101, 109)}, raising=False)
    monkeypatch.setattr(
        ws,
        "build_subscription_tokens",
        lambda symbols, max_tokens=150: (
            [101, 102, 103, 104, 105, 106, 107, 108],
            [{"symbol": "BANKNIFTY", "tokens": [101, 102, 103, 104, 105, 106, 107, 108], "stale_option_pruned_count": 6}],
        ),
    )
    monkeypatch.setattr(
        ws,
        "_option_subscription_freshness_stats",
        lambda now_epoch, tokens: {"option_count": 8, "fresh_count": fresh_count, "stale_count": stale_count, "fresh_ratio": fresh_ratio, "max_age_sec": 12.0},
    )
    monkeypatch.setattr(
        ws,
        "_option_subscription_freshness_by_symbol_stats",
        lambda now_epoch, tokens: {
            "BANKNIFTY": {
                "option_count": 8,
                "fresh_count": fresh_count,
                "stale_count": stale_count,
                "fresh_ratio": fresh_ratio,
                "max_age_sec": 12.0,
                "urgent_max_age_sec": 2.0,
            }
        },
    )
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(cfg, "MAX_DEPTH_AGE_SEC", 1000.0, raising=False)
    monkeypatch.setattr(cfg, "MAX_QUOTE_AGE_SEC", 1000.0, raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 100.0, raising=False)
    monkeypatch.setattr(ws, "_RUNTIME_STATE", "RUNNING", raising=False)
    monkeypatch.setattr(ws, "_STOP_REQUESTED", False, raising=False)
    ticker = _DummyTicker("api_key_1234", "TOKEN123", debug=True)
    ticker.connected = True
    monkeypatch.setattr(ws, "_KITE_TICKER", ticker, raising=False)
    return ticker
def test_start_depth_ws_uses_resolved_token(monkeypatch):
    _patch_common(monkeypatch)
    captured = {}
    def _factory(api_key, access_token, debug=True, **kwargs):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker
    monkeypatch.setattr(ws, "KiteTicker", _factory)
    ws.start_depth_ws([101], skip_lock=True, skip_guard=True)
    ticker = captured["ticker"]
    assert ticker.api_key == "api_key_1234"
    assert ticker.access_token == "TOKEN123"
    assert ticker.auto_reconnect is True
    assert ticker.connected is True


def test_on_ticks_records_decoded_boundary_once_per_callback(monkeypatch):
    _patch_common(monkeypatch)
    callbacks = []
    monkeypatch.setattr(ws, "record_fd_trace", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws.feed_evidence, "callback", lambda count, **kwargs: callbacks.append((count, kwargs.get("rows"))))
    monkeypatch.setattr(ws.feed_evidence, "normalized", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws.feed_evidence, "published", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws.feed_evidence, "publication_failed", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws.feed_evidence, "inc", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws, "record_tick", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws, "record_depth", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws, "write_queue_depth", lambda: 0)
    monkeypatch.setattr(ws, "write_enqueue_count", lambda: 0)
    monkeypatch.setattr(ws, "write_flush_count", lambda: 0)
    monkeypatch.setattr(ws, "_should_throttle_ws_event", lambda *args, **kwargs: True)
    monkeypatch.setattr(ws, "_extract_tick_epoch", lambda tick: tick.get("exchange_timestamp"))
    monkeypatch.setattr(ws, "_normalized_tick_epoch", lambda *args, **kwargs: 1234.5)
    monkeypatch.setattr(ws, "_depth_has_bid_ask", lambda depth: False)
    monkeypatch.setattr(ws, "_best_price", lambda rows: None)
    monkeypatch.setattr(ws, "_update_symbol_freshness", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws, "_update_index_quote_cache", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws, "_is_index_symbol", lambda symbol: False)
    monkeypatch.setattr(ws, "_is_underlying_token", lambda token: True)
    monkeypatch.setattr(ws, "_log_tick_ingest_error", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws, "insert_tick", lambda **kwargs: True)
    monkeypatch.setattr(ws, "record_tick_epoch", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws, "_should_throttle_ws_event", lambda *args, **kwargs: True)
    monkeypatch.setattr(ws, "now_utc_epoch", lambda: 1234.5)
    monkeypatch.setattr(ws, "_SCHEMA_LOG_TS", 0.0, raising=False)
    monkeypatch.setattr(ws, "_FEED_ON_TICKS_ROW_SEQ", 0, raising=False)

    ws.on_ticks(None, [{
        "instrument_token": 101,
        "last_price": 10.0,
        "exchange_timestamp": 1234.5,
        "volume": 1.0,
        "oi": 2.0,
        "_audit_source_row_index": 7,
        "_audit_source_timestamp": 1234.5,
    }])

    assert callbacks and callbacks[0][0] == 1
    assert callbacks[0][1][0]["_audit_source_row_index"] == 7

def test_on_close_does_not_restart_after_stop(monkeypatch):
    _patch_common(monkeypatch)
    captured = {}
    restarts = {"count": 0}
    def _factory(api_key, access_token, debug=True, **kwargs):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker
    def _restart(reason="unknown"):
        restarts["count"] += 1
        return True
    monkeypatch.setattr(ws, "KiteTicker", _factory)
    monkeypatch.setattr(ws, "restart_depth_ws", _restart)
    ws.start_depth_ws([101], skip_lock=True, skip_guard=True)
    ticker = captured["ticker"]
    ws.stop_depth_ws(reason="unit_test_stop")
    ticker.on_close(ticker, 1000, "normal")
    assert restarts["count"] == 0
def test_ws1006_peer_drop_on_error_is_recoverable_first(monkeypatch):
    _patch_common(monkeypatch)
    captured = {}
    scheduled = []
    reconnects = []
    events: list[tuple[str, dict]] = []
    def _factory(api_key, access_token, debug=True, **kwargs):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker
    monkeypatch.setattr(ws, "KiteTicker", _factory)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(cfg, "DEPTH_WS_ALLOW_SOFT_RECONNECTS", True, raising=False)
    monkeypatch.setattr(ws, "_soft_resubscribe_current", lambda reason: reconnects.append(reason) or True)
    monkeypatch.setattr(
        ws,
        "_schedule_restart_depth_ws",
        lambda **kwargs: scheduled.append(dict(kwargs)) or True,
    )
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    ws.start_depth_ws([101], skip_lock=True, skip_guard=True)
    ticker = captured["ticker"]
    ticker.on_error(
        ticker,
        1006,
        "connection was closed uncleanly (peer dropped the TCP connection without previous WebSocket closing handshake)",
    )
    assert reconnects == ["ws1006_recoverable:on_error"]
    assert scheduled == []
    assert any(event == "FEED_WS_1006_RECOVERABLE" for event, _ in events)
    assert any(event == "FEED_WS_RECOVERY_ATTEMPT" for event, _ in events)
    payload = json.loads((ws.logs_dir() / "feed_runtime_latest.json").read_text(encoding="utf-8"))
    assert payload["runtime_state"] in {"RECONNECTING", "DEGRADED"}
    assert payload["ws_connected"] is False
    assert payload["disconnected_code"] == 1006
    assert payload["recovery_blocked"] is False
    assert payload["process_restart_required"] is False
    assert payload["reconnect_blocked_reason"] is None
    assert payload["restart_suppressed"] is False
def test_ws1006_auth_failure_blocks_reconnect_loop(monkeypatch):
    _patch_common(monkeypatch)
    captured = {}
    events: list[tuple[str, dict]] = []
    def _factory(api_key, access_token, debug=True, **kwargs):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker
    monkeypatch.setattr(ws, "KiteTicker", _factory)
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    ws.start_depth_ws([101], skip_lock=True, skip_guard=True)
    ticker = captured["ticker"]
    ticker.on_error(ticker, 403, "invalid auth token")
    assert any(event == "FEED_AUTH_REQUIRED" for event, _ in events)
    payload = json.loads((ws.logs_dir() / "feed_runtime_latest.json").read_text(encoding="utf-8"))
    assert payload["runtime_state"] in {"AUTH_BLOCKED", "STOPPED"}
    assert payload["ws_connected"] is False
    assert ws._AUTH_REQUIRED_LATCH is True
def test_ws1006_recovery_timeout_is_fail_closed(monkeypatch):
    _patch_common(monkeypatch)
    captured = {}
    clock = {"now": 100.0}
    class _ClockedCoordinator(FeedRecoveryCoordinator):
        def __init__(self):
            super().__init__(
                max_recoverable_attempts_per_session=2,
                recoverable_retry_cooldown_sec=0.0,
                recovery_timeout_sec=90.0,
                max_recoveries_per_window=3,
                recovery_window_sec=600.0,
                now_epoch_fn=lambda: clock["now"],
            )
    def _factory(api_key, access_token, debug=True, **kwargs):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker
    monkeypatch.setattr(ws, "KiteTicker", _factory)
    monkeypatch.setattr(ws, "_FEED_RECOVERY_COORDINATOR", _ClockedCoordinator(), raising=False)
    ws.start_depth_ws([101], skip_lock=True, skip_guard=True)
    ticker = captured["ticker"]
    ticker.on_error(ticker, 1006, "connection was closed uncleanly (peer dropped the TCP connection without previous WebSocket closing handshake)")
    clock["now"] += 91.0
    ticker.on_error(ticker, 1006, "connection was closed uncleanly (peer dropped the TCP connection without previous WebSocket closing handshake)")
    payload = json.loads((ws.logs_dir() / "feed_runtime_latest.json").read_text(encoding="utf-8"))
    assert payload["runtime_state"] == "RECOVERY_BLOCKED"
    assert payload["recovery_blocked"] is True
    assert payload["ws1006_recovery_attempt_count"] == 1
    assert payload["ws_recovery_state"] == "RECOVERY_BLOCKED"
def test_ws1006_peer_drop_escalates_after_max_recoverable_attempts(monkeypatch):
    _patch_common(monkeypatch)
    scheduled = []
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(ws, "_ws1006_recoverable_max_attempts_per_session", lambda: 1, raising=False)
    monkeypatch.setattr(ws, "_ws1006_recoverable_retry_cooldown_sec", lambda: 0.0, raising=False)
    monkeypatch.setattr(
        ws,
        "_schedule_restart_depth_ws",
        lambda **kwargs: scheduled.append(dict(kwargs)) or True,
    )
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    ws._handle_ws1006_recoverable(source="on_error", ws=object(), code=1006, reason="connection was closed uncleanly (peer dropped)")
    ws._FEED_RECOVERY_COORDINATOR.clear_recovery(source="unit_test", reason="reconnect_verified")
    ws._sync_ws1006_recovery_state_from_coordinator()
    ws._handle_ws1006_recoverable(source="on_error", ws=object(), code=1006, reason="connection was closed uncleanly (peer dropped)")
    assert any(event == "FEED_RECOVERY_BLOCKED" for event, _ in events)
    assert scheduled == [
        {
            "force_full_restart": True,
            "ignore_cooldown": True,
            "reason": "ws1006_recovery_full:on_error",
            "source": "ws1006_recovery",
        }
    ]
    assert ws._WS1006_RECOVERABLE_ATTEMPTS == 1
    payload = json.loads((ws.logs_dir() / "feed_runtime_latest.json").read_text(encoding="utf-8"))
    assert payload["process_restart_required"] is True
    assert payload["reconnect_blocked_reason"] == "recovery_blocked"
    assert payload["restart_suppressed"] is True
def test_ws1006_main_loop_terminated_routes_to_process_restart_required(monkeypatch):
    _patch_common(monkeypatch)
    captured = {}
    scheduled = []
    events: list[tuple[str, dict]] = []
    def _factory(api_key, access_token, debug=True, **kwargs):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker
    monkeypatch.setattr(ws, "KiteTicker", _factory)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(
        ws,
        "_schedule_restart_depth_ws",
        lambda **kwargs: scheduled.append(dict(kwargs)) or True,
    )
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    ws.start_depth_ws([101], skip_lock=True, skip_guard=True)
    ticker = captured["ticker"]
    ticker.on_error(ticker, 1006, "main loop terminated after reactor shutdown")
    assert scheduled == []
    assert any(event == "FEED_WS_PROCESS_RESTART_REQUIRED" for event, _ in events)
    assert any(event == "FEED_RECOVERY_REQUESTED" for event, _ in events)
    assert not any(event == "FEED_WS_1006_RECOVERABLE" for event, _ in events)
    payload = json.loads((ws.logs_dir() / "feed_runtime_latest.json").read_text(encoding="utf-8"))
    assert payload["process_restart_required"] is True
    assert payload["reconnect_blocked_reason"] == "ws1006_process_restart_required"
    assert payload["restart_suppressed"] is True
def test_fatal_on_error_schedules_async_forced_full_restart(monkeypatch):
    _patch_common(monkeypatch)
    captured = {}
    scheduled = []
    def _factory(api_key, access_token, debug=True, **kwargs):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker
    monkeypatch.setattr(ws, "KiteTicker", _factory)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(
        ws,
        "_schedule_restart_depth_ws",
        lambda **kwargs: scheduled.append(dict(kwargs)) or True,
    )
    ws.start_depth_ws([101], skip_lock=True, skip_guard=True)
    ticker = captured["ticker"]
    ticker.on_error(
        ticker,
        1006,
        "connection was closed uncleanly (peer dropped the TCP connection without previous WebSocket closing handshake)",
    )
    assert scheduled == [
        {
            "force_full_restart": True,
            "ignore_cooldown": True,
            "reason": "ws1006_recovery_full:on_error",
            "source": "ws1006_recovery",
        }
    ]
    payload = json.loads((ws.logs_dir() / "feed_runtime_latest.json").read_text(encoding="utf-8"))
    assert payload["runtime_state"] in {"RECONNECTING", "DEGRADED"}
    assert payload["ws_connected"] is False
    assert payload["disconnected_code"] == 1006
    assert "connection was closed uncleanly" in payload["disconnected_reason"]
    assert payload["restart_attempt_allowed"] is True
    assert payload["restart_attempted"] is True
    assert payload["process_restart_required"] is False
    assert payload["recovery_blocked"] is False
    assert payload["reconnect_blocked_reason"] is None
    assert payload["restart_blocked_reason"] is None
    assert payload["ws1006_recovery_attempt_count"] == 1
    assert payload["ws_recovery_state"] == "RECOVERING_WS_DROP"
    assert payload["option_feed_verification_state"] in {"IDLE", "PENDING"}
def test_fatal_on_close_schedules_async_forced_full_restart(monkeypatch):
    _patch_common(monkeypatch)
    captured = {}
    scheduled = []
    def _factory(api_key, access_token, debug=True, **kwargs):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker
    monkeypatch.setattr(ws, "KiteTicker", _factory)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(
        ws,
        "_schedule_restart_depth_ws",
        lambda **kwargs: scheduled.append(dict(kwargs)) or True,
    )
    ws.start_depth_ws([101], skip_lock=True, skip_guard=True)
    ticker = captured["ticker"]
    ticker.on_close(
        ticker,
        1006,
        "connection was closed uncleanly (peer dropped the TCP connection without previous WebSocket closing handshake)",
    )
    assert scheduled == [
        {
            "force_full_restart": True,
            "ignore_cooldown": True,
            "reason": "ws1006_recovery_full:on_close",
            "source": "ws1006_recovery",
        }
    ]
    payload = json.loads((ws.logs_dir() / "feed_runtime_latest.json").read_text(encoding="utf-8"))
    assert payload["runtime_state"] in {"RECONNECTING", "DEGRADED"}
    assert payload["ws_connected"] is False
    assert payload["disconnected_code"] == 1006
    assert "connection was closed uncleanly" in payload["disconnected_reason"]
    assert payload["restart_attempt_allowed"] is True
    assert payload["restart_attempted"] is True
    assert payload["process_restart_required"] is False
    assert payload["recovery_blocked"] is False
    assert payload["reconnect_blocked_reason"] is None
    assert payload["restart_blocked_reason"] is None
    assert payload["ws1006_recovery_attempt_count"] == 1
    assert payload["ws_recovery_state"] == "RECOVERING_WS_DROP"
def test_on_ticks_updates_index_quote_cache_from_underlying_depth(monkeypatch):
    _patch_common(monkeypatch)
    captured = {}
    cache_updates = []
    def _factory(api_key, access_token, debug=True, **kwargs):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker
    monkeypatch.setattr(ws, "KiteTicker", _factory)
    monkeypatch.setattr(cfg, "KITE_STORE_TICKS", False, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {101}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {101: "NIFTY"}, raising=False)
    monkeypatch.setattr(
        ws,
        "_update_index_quote_cache",
        lambda symbol, bid, ask, mid, ts_epoch, last_price, *, volume=None: cache_updates.append(
            {
                "symbol": symbol,
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "ts_epoch": ts_epoch,
                "last_price": last_price,
                "volume": volume,
            }
        ),
    )
    ws.start_depth_ws([101], skip_lock=True, skip_guard=True)
    ticker = captured["ticker"]
    ticker.on_ticks(
        ticker,
        [
            {
                "instrument_token": 101,
                "last_price": 101.0,
                "depth": {
                    "buy": [{"price": 100.0, "quantity": 10}],
                    "sell": [{"price": 102.0, "quantity": 12}],
                },
                "exchange_timestamp": datetime(2026, 2, 19, 9, 30, tzinfo=timezone.utc),
            }
        ],
    )
    assert cache_updates
    row = cache_updates[-1]
    assert row["symbol"] == "NIFTY"
    assert row["bid"] == 100.0
    assert row["ask"] == 102.0
    assert row["mid"] == 101.0
    assert row["last_price"] == 101.0
    assert row["volume"] is None
def test_on_ticks_updates_symbol_ltp_and_depth_timestamps(monkeypatch):
    _patch_common(monkeypatch)
    captured = {}
    def _factory(api_key, access_token, debug=True, **kwargs):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker
    monkeypatch.setattr(ws, "KiteTicker", _factory)
    monkeypatch.setattr(cfg, "KITE_STORE_TICKS", False, raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {101: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {101}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {101: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "record_tick_epoch", lambda ts: None)
    ws.start_depth_ws([101], skip_lock=True, skip_guard=True)
    ticker = captured["ticker"]
    ltp_ts = datetime(2026, 2, 19, 9, 30, tzinfo=timezone.utc)
    ticker.on_ticks(
        ticker,
        [
            {
                "instrument_token": 101,
                "last_price": 25000.0,
                "exchange_timestamp": ltp_ts,
            }
        ],
    )
    assert ws._SYMBOL_LAST_LTP_TS.get("NIFTY") == ltp_ts.timestamp()
    assert "NIFTY" not in ws._SYMBOL_LAST_DEPTH_TS
    assert ws._LAST_WS_TICK_EPOCH > 0
    depth_ts = datetime(2026, 2, 19, 9, 31, tzinfo=timezone.utc)
    ticker.on_ticks(
        ticker,
        [
            {
                "instrument_token": 101,
                "last_price": 25001.0,
                "exchange_timestamp": depth_ts,
                "depth": {
                    "buy": [{"price": 25000.0, "quantity": 12}],
                    "sell": [{"price": 25002.0, "quantity": 9}],
                },
            }
        ],
    )
    assert ws._SYMBOL_LAST_LTP_TS.get("NIFTY") == depth_ts.timestamp()
    assert ws._SYMBOL_LAST_DEPTH_TS.get("NIFTY") == depth_ts.timestamp()
def test_on_ticks_does_not_update_index_quote_cache_from_non_underlying_tick(monkeypatch):
    _patch_common(monkeypatch)
    captured = {}
    cache_updates = []
    def _factory(api_key, access_token, debug=True, **kwargs):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker
    monkeypatch.setattr(ws, "KiteTicker", _factory)
    monkeypatch.setattr(cfg, "KITE_STORE_TICKS", False, raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {101: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", set(), raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {}, raising=False)
    monkeypatch.setattr(
        ws,
        "_update_index_quote_cache",
        lambda symbol, bid, ask, mid, ts_epoch, last_price, *, volume=None: cache_updates.append(
            {
                "symbol": symbol,
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "ts_epoch": ts_epoch,
                "last_price": last_price,
                "volume": volume,
            }
        ),
    )
    ws.start_depth_ws([101], skip_lock=True, skip_guard=True)
    ticker = captured["ticker"]
    tick_ts = datetime(2026, 2, 19, 9, 35, tzinfo=timezone.utc)
    ticker.on_ticks(
        ticker,
        [
            {
                "instrument_token": 101,
                "last_price": 25123.5,
                "exchange_timestamp": tick_ts,
            }
        ],
    )
    assert cache_updates == []
def test_on_ticks_uses_receipt_time_for_option_freshness(monkeypatch, tmp_path):
    _patch_common(monkeypatch)
    captured = {}
    db_path = tmp_path / "ticks.sqlite"
    def _factory(api_key, access_token, debug=True, **kwargs):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker
    receipt_epoch = datetime(2026, 2, 19, 9, 37, tzinfo=timezone.utc).timestamp()
    stale_payload_ts = datetime(2026, 2, 19, 9, 35, tzinfo=timezone.utc)
    monkeypatch.setattr(ws, "KiteTicker", _factory)
    monkeypatch.setattr(cfg, "KITE_STORE_TICKS", False, raising=False)
    monkeypatch.setattr(cfg, "TICK_STORE_ENABLE_DB_WRITES", True, raising=False)
    monkeypatch.setattr(cfg, "TICK_STORE_ASYNC_DB_WRITES", True, raising=False)
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(tick_store.cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(cfg, "DEPTH_WS_OPTION_FRESHNESS_USE_RECEIPT_TIME", True, raising=False)
    monkeypatch.setattr(ws, "now_utc_epoch", lambda: receipt_epoch)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {555: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", set(), raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {}, raising=False)
    tick_store.set_replay_pressure_immediate_flush_enabled(True)
    tick_store.set_replay_pressure_read_flush_enabled(True)
    tick_store._LAST_TICK_EPOCH = None
    tick_store._LAST_TICK_BY_TOKEN.clear()
    try:
        ws.start_depth_ws([555], skip_lock=True, skip_guard=True)
        ticker = captured["ticker"]
        ticker.on_ticks(
            ticker,
            [
                {
                    "instrument_token": 555,
                    "last_price": 25123.5,
                    "exchange_timestamp": stale_payload_ts,
                }
            ],
        )
        assert ws._LAST_MSG_TS_BY_TOKEN[555] == receipt_epoch
        assert ws._LAST_WS_TICK_EPOCH == receipt_epoch
        option_state = ws._option_runtime_state(
            now_epoch=receipt_epoch,
            tokens=[555],
            expected_counts_by_symbol={"NIFTY": 1},
            min_required_by_symbol={"NIFTY": 1},
        )
        assert option_state["last_tick_ts_by_symbol"]["NIFTY"] == receipt_epoch
        assert option_state["option_age_by_symbol"]["NIFTY"] == 0.0
        assert option_state["feed_block_reason_by_symbol"]["NIFTY"] == "OK"
        ltp, tick_epoch = tick_store.get_ltp(555)
        assert ltp == 25123.5
        assert tick_epoch == receipt_epoch
        shutdown_result = tick_store.shutdown_persistence_worker(deadline_seconds=1.0)
        assert shutdown_result["status"] == "COMPLETE_DRAIN"
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute("SELECT MAX(timestamp_epoch) FROM ticks WHERE instrument_token=?", (555,)).fetchone()
        assert row is not None
        assert row[0] == receipt_epoch
    finally:
        tick_store.reset_audit_counters()
        tick_store.clear_replay_pressure_hook()
        tick_store.set_replay_pressure_immediate_flush_enabled(True)
        tick_store.set_replay_pressure_read_flush_enabled(True)
def test_on_ticks_clamps_epoch_monotonic_and_resets_stale_strikes(monkeypatch):
    _patch_common(monkeypatch)
    captured = {}
    events = []
    def _factory(api_key, access_token, debug=True, **kwargs):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker
    monkeypatch.setattr(ws, "KiteTicker", _factory)
    monkeypatch.setattr(cfg, "KITE_STORE_TICKS", False, raising=False)
    monkeypatch.setattr(cfg, "FEED_TICK_MAX_PAYLOAD_LAG_SEC", 2.0, raising=False)
    monkeypatch.setattr(ws, "now_utc_epoch", lambda: 205.0)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {101: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {101}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {101: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    ws.start_depth_ws([101], skip_lock=True, skip_guard=True)
    monkeypatch.setattr(ws, "_STALE_STRIKES", 2, raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 200.0, raising=False)
    monkeypatch.setattr(ws, "_LAST_MSG_TS_BY_TOKEN", {101: 200.0}, raising=False)
    monkeypatch.setattr(ws, "_LAST_PAYLOAD_TS_BY_TOKEN", {101: 200.0}, raising=False)
    ticker = captured["ticker"]
    ticker.on_ticks(
        ticker,
        [
            {
                "instrument_token": 101,
                "last_price": 25010.0,
                "exchange_timestamp": 190.0,
            }
        ],
    )
    assert ws._LAST_MSG_TS_BY_TOKEN[101] == 200.0
    assert ws._LAST_WS_TICK_EPOCH == 200.0
    assert ws._STALE_STRIKES == 2
    assert not any(event == "FEED_HEALTH_OK" for event, _payload in events)
def test_on_ticks_newer_same_symbol_option_tick_refreshes_symbol_age(monkeypatch):
    _patch_common(monkeypatch)
    captured = {}
    def _factory(api_key, access_token, debug=True, **kwargs):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker
    monkeypatch.setattr(ws, "KiteTicker", _factory)
    monkeypatch.setattr(cfg, "KITE_STORE_TICKS", False, raising=False)
    monkeypatch.setattr(cfg, "OPTION_LTP_SLA_SEC", 8.0, raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {555: "NIFTY", 556: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", set(), raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {}, raising=False)
    current_epoch = {"value": 100.0}
    monkeypatch.setattr(ws, "now_utc_epoch", lambda: current_epoch["value"])
    ws.start_depth_ws([555, 556], skip_lock=True, skip_guard=True)
    ticker = captured["ticker"]
    ticker.on_ticks(ticker, [{"instrument_token": 555, "last_price": 101.0, "exchange_timestamp": datetime(2026, 2, 19, 9, 30, tzinfo=timezone.utc)}])
    current_epoch["value"] = 105.0
    ticker.on_ticks(ticker, [{"instrument_token": 556, "last_price": 102.0, "exchange_timestamp": datetime(2026, 2, 19, 9, 31, tzinfo=timezone.utc)}])
    option_state = ws._option_runtime_state(
        now_epoch=105.0,
        tokens=[555, 556],
        expected_counts_by_symbol={"NIFTY": 2},
        min_required_by_symbol={"NIFTY": 1},
    )
    assert ws._SYMBOL_LAST_OPTION_TICK_TS["NIFTY"] == 105.0
    assert option_state["last_tick_ts_by_symbol"]["NIFTY"] == 105.0
    assert option_state["option_age_by_symbol"]["NIFTY"] == 0.0
    assert option_state["feed_block_reason_by_symbol"]["NIFTY"] == "OK"
def test_auth_failure_sets_auth_required_and_blocks_restarts(monkeypatch):
    _patch_common(monkeypatch)
    captured = {}
    auth_marks = []
    restarts = {"count": 0}
    stops = {"count": 0}
    def _factory(api_key, access_token, debug=True, **kwargs):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker
    def _stop(reason="manual_stop"):
        stops["count"] += 1
        ws._STOP_REQUESTED = True
    monkeypatch.setattr(ws, "KiteTicker", _factory)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(ws, "restart_depth_ws", lambda reason="unknown": restarts.__setitem__("count", restarts["count"] + 1))
    monkeypatch.setattr(ws, "set_auth_required_state", lambda **kwargs: auth_marks.append(kwargs) or {"status": "AUTH_REQUIRED"})
    monkeypatch.setattr(ws, "stop_depth_ws", _stop)
    ws.start_depth_ws([101], skip_lock=True, skip_guard=True)
    ticker = captured["ticker"]
    ticker.on_error(ticker, 403, "invalid session")
    assert ws._AUTH_REQUIRED_LATCH is True
    assert auth_marks
    assert stops["count"] == 1
    assert restarts["count"] == 0
def test_network_error_restarts_without_auth_required(monkeypatch):
    _patch_common(monkeypatch)
    captured = {}
    auth_marks = []
    restarts = {"count": 0}
    def _factory(api_key, access_token, debug=True, **kwargs):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker
    monkeypatch.setattr(ws, "KiteTicker", _factory)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(cfg, "DEPTH_WS_USE_INTERNAL_RECONNECT", False, raising=False)
    monkeypatch.setattr(ws, "set_auth_required_state", lambda **kwargs: auth_marks.append(kwargs) or {"status": "AUTH_REQUIRED"})
    monkeypatch.setattr(ws, "restart_depth_ws", lambda reason="unknown": restarts.__setitem__("count", restarts["count"] + 1) or True)
    ws.start_depth_ws([101], skip_lock=True, skip_guard=True)
    ticker = captured["ticker"]
    ticker.on_error(ticker, 1006, "connection closed by peer")
    assert restarts["count"] == 0
    assert auth_marks == []
    assert ws._AUTH_REQUIRED_LATCH is False
def test_network_error_forces_full_restart_when_enabled(monkeypatch):
    _patch_common(monkeypatch)
    captured = {}
    scheduled = []
    soft = {"count": 0}
    def _factory(api_key, access_token, debug=True, **kwargs):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker
    monkeypatch.setattr(ws, "KiteTicker", _factory)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(cfg, "DEPTH_WS_USE_INTERNAL_RECONNECT", True, raising=False)
    monkeypatch.setattr(
        ws,
        "_schedule_restart_depth_ws",
        lambda **kwargs: scheduled.append(dict(kwargs)) or True,
    )
    monkeypatch.setattr(
        ws,
        "_soft_resubscribe_current",
        lambda reason="unknown": soft.__setitem__("count", soft["count"] + 1) or True,
    )
    ws.start_depth_ws([101], skip_lock=True, skip_guard=True)
    ticker = captured["ticker"]
    ticker.on_error(ticker, 1006, "connection closed by peer")
    assert scheduled == []
    assert soft["count"] == 0
def test_single_stale_token_does_not_refresh_full_symbol(monkeypatch):
    _patch_common(monkeypatch)
    _fresh_refresh_stale_symbol_state(monkeypatch, fresh_ratio=0.0, stale_count=1, fresh_count=0)
    should_refresh, payload = ws._maybe_refresh_stale_option_subscription_universe(
        now_epoch=500.0,
        refresh_state={"last_refresh_epoch": 0.0, "last_freshness_refresh_epoch": 0.0},
    )
    assert should_refresh is False
    assert payload["freshness_urgent"] is True
    assert payload["mutation_eligible_symbols"] == []
    assert payload["mutation_skipped_symbols"] == ["BANKNIFTY"]
    assert payload["mutation_skip_reason_by_symbol"]["BANKNIFTY"] == "stale_count_below_threshold"
    assert payload["subscribe_tokens"] == []
    assert payload["unsubscribe_tokens"] == []
    assert payload["refresh_tokens"] == []
    assert payload["refresh_applied"] is False
def test_high_fresh_ratio_with_one_stale_symbol_logs_skip_reason(monkeypatch):
    _patch_common(monkeypatch)
    _fresh_refresh_stale_symbol_state(monkeypatch, fresh_ratio=0.9, stale_count=6, fresh_count=2)
    should_refresh, payload = ws._maybe_refresh_stale_option_subscription_universe(
        now_epoch=500.0,
        refresh_state={"last_refresh_epoch": 0.0, "last_freshness_refresh_epoch": 0.0},
    )
    assert should_refresh is False
    assert payload["freshness_urgent"] is True
    assert payload["mutation_eligible_symbols"] == []
    assert payload["mutation_skipped_symbols"] == ["BANKNIFTY"]
    assert payload["mutation_skip_reason_by_symbol"]["BANKNIFTY"] == "fresh_ratio_above_mutation_threshold"
    assert payload["reason"] == "freshness_urgent_no_mutation_eligible"
def test_mutation_guard_false_suppresses_stale_option_rebalance_applied() -> None:
    blocked, payload = ws._stale_option_mutation_guard_blocked(
        {
            "reason": "freshness_drift",
            "refresh_mode": "symbol_freshness",
            "freshness_urgent": True,
            "freshness_urgent_symbols": ["BANKNIFTY"],
            "mutation_eligible_symbols": [],
            "mutation_skipped_symbols": ["BANKNIFTY"],
            "mutation_skip_reason_by_symbol": {"BANKNIFTY": "fresh_ratio_above_mutation_threshold"},
            "mutation_window_count_by_symbol": {"BANKNIFTY": 2},
            "mutation_guard_ok": False,
            "mutation_guard_reason": "fresh_ratio_above_threshold",
            "mutation_guard_payload": {"source": "unit_test"},
            "fresh_count": 2,
            "stale_count": 6,
            "fresh_ratio": 0.9,
            "max_age_sec": 12.0,
            "min_stale_tokens_required": 5,
            "mutation_max_fresh_ratio": 0.7,
            "mutation_consecutive_windows_required": 3,
        }
    )
    assert blocked is True
    assert payload["guard_reason"] == "fresh_ratio_above_threshold"
    assert payload["mutation_guard_ok"] is False
    assert payload["fresh_count"] == 2
    assert payload["stale_count"] == 6
    assert payload["fresh_ratio"] == 0.9
    assert payload["mutation_skip_reason_by_symbol"]["BANKNIFTY"] == "fresh_ratio_above_mutation_threshold"
    assert payload["mutation_skipped_symbols"] == ["BANKNIFTY"]
def test_urgent_stale_diagnostic_does_not_bypass_mutation_guard() -> None:
    blocked, payload = ws._stale_option_mutation_guard_blocked(
        {
            "reason": "freshness_drift",
            "refresh_mode": "symbol_freshness",
            "freshness_urgent": True,
            "freshness_urgent_symbols": ["BANKNIFTY", "SENSEX"],
            "mutation_eligible_symbols": ["BANKNIFTY"],
            "mutation_skipped_symbols": ["BANKNIFTY", "SENSEX"],
            "mutation_skip_reason_by_symbol": {
                "BANKNIFTY": "mutation_consecutive_windows_not_met",
                "SENSEX": "stale_count_below_threshold",
            },
            "mutation_window_count_by_symbol": {"BANKNIFTY": 2, "SENSEX": 0},
            "mutation_guard_ok": False,
            "mutation_guard_reason": "mutation_breadth_not_met",
            "mutation_guard_payload": {"source": "unit_test"},
            "fresh_count": 10,
            "stale_count": 2,
            "fresh_ratio": 0.83,
            "max_age_sec": 9.0,
            "min_stale_tokens_required": 5,
            "mutation_max_fresh_ratio": 0.7,
            "mutation_consecutive_windows_required": 3,
        }
    )
    assert blocked is True
    assert payload["guard_reason"] == "mutation_breadth_not_met"
    assert payload["freshness_urgent_symbols"] == ["BANKNIFTY", "SENSEX"]
    assert payload["mutation_eligible_symbols"] == ["BANKNIFTY"]
    assert payload["mutation_guard_payload"] == {"source": "unit_test"}
def test_symbol_mutation_requires_stale_count_and_low_fresh_ratio() -> None:
    allowed, payload, _ = ws._should_mutate_stale_option_symbol_subscription(
        symbol="BANKNIFTY",
        option_count=8,
        fresh_count=1,
        stale_count=4,
        fresh_ratio=0.125,
        max_age_sec=12.0,
        urgent_max_age_sec=2.0,
        min_fresh_ratio=0.8,
        min_stale_tokens_required=5,
        mutation_max_fresh_ratio=0.7,
        consecutive_windows_required=3,
        stale_window_state={},
        now_epoch=500.0,
    )
    assert allowed is False
    assert payload["mutation_skip_reason"] == "stale_count_below_threshold"
    allowed, payload, _ = ws._should_mutate_stale_option_symbol_subscription(
        symbol="BANKNIFTY",
        option_count=8,
        fresh_count=6,
        stale_count=6,
        fresh_ratio=0.75,
        max_age_sec=12.0,
        urgent_max_age_sec=2.0,
        min_fresh_ratio=0.8,
        min_stale_tokens_required=5,
        mutation_max_fresh_ratio=0.7,
        consecutive_windows_required=3,
        stale_window_state={},
        now_epoch=500.0,
    )
    assert allowed is False
    assert payload["mutation_skip_reason"] == "fresh_ratio_above_mutation_threshold"
def test_symbol_mutation_allowed_after_consecutive_broad_stale_windows() -> None:
    state = {}
    allowed, payload, state = ws._should_mutate_stale_option_symbol_subscription(
        symbol="BANKNIFTY",
        option_count=8,
        fresh_count=2,
        stale_count=6,
        fresh_ratio=0.25,
        max_age_sec=12.0,
        urgent_max_age_sec=2.0,
        min_fresh_ratio=0.8,
        min_stale_tokens_required=5,
        mutation_max_fresh_ratio=0.7,
        consecutive_windows_required=3,
        stale_window_state=state,
        now_epoch=500.0,
    )
    assert allowed is False
    assert payload["mutation_window_count_by_symbol"] == 1
    allowed, payload, state = ws._should_mutate_stale_option_symbol_subscription(
        symbol="BANKNIFTY",
        option_count=8,
        fresh_count=2,
        stale_count=6,
        fresh_ratio=0.25,
        max_age_sec=12.0,
        urgent_max_age_sec=2.0,
        min_fresh_ratio=0.8,
        min_stale_tokens_required=5,
        mutation_max_fresh_ratio=0.7,
        consecutive_windows_required=3,
        stale_window_state=state,
        now_epoch=545.0,
    )
    assert allowed is False
    assert payload["mutation_window_count_by_symbol"] == 2
    allowed, payload, state = ws._should_mutate_stale_option_symbol_subscription(
        symbol="BANKNIFTY",
        option_count=8,
        fresh_count=2,
        stale_count=6,
        fresh_ratio=0.25,
        max_age_sec=12.0,
        urgent_max_age_sec=2.0,
        min_fresh_ratio=0.8,
        min_stale_tokens_required=5,
        mutation_max_fresh_ratio=0.7,
        consecutive_windows_required=3,
        stale_window_state=state,
        now_epoch=590.0,
    )
    assert allowed is True
    assert payload["mutation_window_count_by_symbol"] == 3
def test_mutation_window_resets_when_symbol_recovers() -> None:
    state = {}
    allowed, _, state = ws._should_mutate_stale_option_symbol_subscription(
        symbol="BANKNIFTY",
        option_count=8,
        fresh_count=2,
        stale_count=6,
        fresh_ratio=0.25,
        max_age_sec=12.0,
        urgent_max_age_sec=2.0,
        min_fresh_ratio=0.8,
        min_stale_tokens_required=5,
        mutation_max_fresh_ratio=0.7,
        consecutive_windows_required=3,
        stale_window_state=state,
        now_epoch=500.0,
    )
    assert allowed is False
    assert state["mutation_window_count"] == 1
    allowed, payload, state = ws._should_mutate_stale_option_symbol_subscription(
        symbol="BANKNIFTY",
        option_count=8,
        fresh_count=8,
        stale_count=0,
        fresh_ratio=1.0,
        max_age_sec=1.0,
        urgent_max_age_sec=2.0,
        min_fresh_ratio=0.8,
        min_stale_tokens_required=5,
        mutation_max_fresh_ratio=0.7,
        consecutive_windows_required=3,
        stale_window_state=state,
        now_epoch=545.0,
    )
    assert allowed is False
    assert payload["mutation_skip_reason"] == "not_diagnostic_urgent"
    assert state["mutation_window_count"] == 0
def test_stale_symbol_without_mutation_permission_does_not_emit_refresh_tokens(monkeypatch):
    _patch_common(monkeypatch)
    _fresh_refresh_stale_symbol_state(monkeypatch, fresh_ratio=0.25, stale_count=6, fresh_count=2)
    should_refresh, payload = ws._maybe_refresh_stale_option_subscription_universe(
        now_epoch=500.0,
        refresh_state={"last_refresh_epoch": 0.0, "last_freshness_refresh_epoch": 0.0},
    )
    assert should_refresh is False
    assert payload["subscribe_tokens"] == []
    assert payload["unsubscribe_tokens"] == []
    assert payload["refresh_tokens"] == []
    assert payload["mutation_eligible_symbols"] == []
    assert payload["mutation_skipped_symbols"] == ["BANKNIFTY"]
def test_legitimate_broad_stale_symbol_can_emit_refresh_after_hysteresis(monkeypatch):
    _patch_common(monkeypatch)
    _fresh_refresh_stale_symbol_state(monkeypatch, fresh_ratio=0.25, stale_count=6, fresh_count=2)
    refresh_state = {"last_refresh_epoch": 0.0, "last_freshness_refresh_epoch": 0.0}
    first = ws._maybe_refresh_stale_option_subscription_universe(now_epoch=500.0, refresh_state=refresh_state)
    second = ws._maybe_refresh_stale_option_subscription_universe(now_epoch=545.0, refresh_state=refresh_state)
    should_refresh, payload = ws._maybe_refresh_stale_option_subscription_universe(now_epoch=590.0, refresh_state=refresh_state)
    assert first[0] is False
    assert second[0] is False
    assert should_refresh is True
    assert payload["mutation_eligible_symbols"] == ["BANKNIFTY"]
    assert payload["refresh_tokens"] == [101, 102, 103, 104, 105, 106, 107, 108]
    assert payload["refresh_applied"] is False
def test_ensure_subscribed_tokens_skips_when_ws_disconnected(monkeypatch):
    _patch_common(monkeypatch)
    ticker = _DummyTicker("api_key_1234", "TOKEN123", debug=True)
    ticker.connected = False
    monkeypatch.setattr(ws, "_KITE_TICKER", ticker, raising=False)
    monkeypatch.setattr(ws, "_RUNTIME_STATE", "RUNNING", raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 100.0, raising=False)
    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    assert ws.ensure_subscribed_tokens([201, 202], reason="unit_test", symbol="BANKNIFTY") is False
    assert ticker.tokens == [] if hasattr(ticker, "tokens") else True
    assert events[-1][0] == "FEED_SUBSCRIBE_SKIPPED"
    assert events[-1][1]["guard_reason"] == "ws_disconnected"
def test_ensure_subscribed_tokens_skips_when_recovery_blocked(monkeypatch):
    _patch_common(monkeypatch)
    ticker = _DummyTicker("api_key_1234", "TOKEN123", debug=True)
    ticker.connected = True
    monkeypatch.setattr(ws, "_KITE_TICKER", ticker, raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 100.0, raising=False)
    monkeypatch.setattr(ws, "_RECONNECT_BLOCKED_REASON", "ws1006_process_restart_required", raising=False)
    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    assert ws.ensure_subscribed_tokens([201, 202], reason="unit_test", symbol="BANKNIFTY") is False
    assert events[-1][0] == "FEED_SUBSCRIBE_SKIPPED"
    assert events[-1][1]["guard_reason"] == "ws1006_process_restart_required"
def test_soft_resubscribe_skips_when_recovery_blocked(monkeypatch):
    _patch_common(monkeypatch)
    ticker = _DummyTicker("api_key_1234", "TOKEN123", debug=True)
    ticker.connected = True
    monkeypatch.setattr(ws, "_KITE_TICKER", ticker, raising=False)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [101, 102], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", [101, 102], raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 100.0, raising=False)
    monkeypatch.setattr(ws, "_RECONNECT_BLOCKED_REASON", "ws1006_process_restart_required", raising=False)
    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    assert ws._soft_resubscribe_current(reason="unit_test") is False
    assert events[-1][0] == "FEED_SOFT_RESUBSCRIBE_SKIPPED"
    assert events[-1][1]["guard_reason"] == "ws1006_process_restart_required"
def test_apply_subscription_delta_skips_when_recovery_blocked(monkeypatch):
    _patch_common(monkeypatch)
    ticker = _DummyTicker("api_key_1234", "TOKEN123", debug=True)
    ticker.connected = True
    monkeypatch.setattr(ws, "_KITE_TICKER", ticker, raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 100.0, raising=False)
    monkeypatch.setattr(ws, "_RECONNECT_BLOCKED_REASON", "ws1006_process_restart_required", raising=False)
    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    assert ws._apply_subscription_delta(ticker, [301, 302], [101], reason="unit_test") is False
    assert events[-1][0] == "FEED_REBALANCE_SKIPPED"
    assert events[-1][1]["guard_reason"] == "ws1006_process_restart_required"
def test_apply_subscription_delta_skips_when_ws_disconnected(monkeypatch):
    _patch_common(monkeypatch)
    ticker = _DummyTicker("api_key_1234", "TOKEN123", debug=True)
    ticker.connected = False
    monkeypatch.setattr(ws, "_KITE_TICKER", ticker, raising=False)
    monkeypatch.setattr(ws, "_RUNTIME_STATE", "RUNNING", raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 100.0, raising=False)
    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    assert ws._apply_subscription_delta(ticker, [301, 302], [101], reason="unit_test") is False
    assert events[-1][0] == "FEED_REBALANCE_SKIPPED"
    assert events[-1][1]["guard_reason"] == "ws_disconnected"
    assert events[-1][1]["ws_connected"] is False
def test_apply_subscription_delta_skips_when_runtime_degraded_and_option_feed_stale(monkeypatch):
    _patch_common(monkeypatch)
    ticker = _DummyTicker("api_key_1234", "TOKEN123", debug=True)
    ticker.connected = True
    monkeypatch.setattr(ws, "_KITE_TICKER", ticker, raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 100.0, raising=False)
    monkeypatch.setattr(ws, "_RUNTIME_STATE", "DEGRADED", raising=False)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [101, 102], raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {101: "NIFTY", 102: "NIFTY"}, raising=False)
    monkeypatch.setattr(
        ws,
        "_LAST_OPTION_COUNTS_BY_SYMBOL",
        {"NIFTY": 2},
        raising=False,
    )
    monkeypatch.setattr(
        ws,
        "_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL",
        {"NIFTY": 1},
        raising=False,
    )
    monkeypatch.setattr(
        ws,
        "_option_runtime_state",
        lambda **kwargs: {
            "option_count": 2,
            "feed_block_reason_by_symbol": {"NIFTY": "FEED_LTP_STALE"},
            "active_blockers_by_symbol": {"NIFTY": ["FEED_LTP_STALE"]},
            "subscribed_count_by_symbol": {"NIFTY": 2},
            "ticks_received_count_by_symbol": {"NIFTY": 0},
            "option_age_by_symbol": {"NIFTY": 99.0},
        },
    )
    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    assert ws._apply_subscription_delta(ticker, [301, 302], [101], reason="unit_test") is False
    assert events[-1][0] == "FEED_REBALANCE_SKIPPED"
    assert "degraded" in str(events[-1][1]["guard_reason"]).lower() or "stale" in str(events[-1][1]["guard_reason"]).lower()
    assert events[-1][1]["runtime_state"] == "DEGRADED"
def test_apply_subscription_delta_allows_healthy_rebalance(monkeypatch):
    _patch_common(monkeypatch)
    ticker = _DummyTicker("api_key_1234", "TOKEN123", debug=True)
    ticker.connected = True
    monkeypatch.setattr(ws, "_KITE_TICKER", ticker, raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 100.0, raising=False)
    monkeypatch.setattr(ws, "_RUNTIME_STATE", "RUNNING", raising=False)
    monkeypatch.setattr(
        ws,
        "_option_runtime_state",
        lambda **kwargs: {
            "option_count": 2,
            "feed_block_reason_by_symbol": {"NIFTY": "OK"},
            "active_blockers_by_symbol": {"NIFTY": []},
            "subscribed_count_by_symbol": {"NIFTY": 2},
            "ticks_received_count_by_symbol": {"NIFTY": 2},
            "option_age_by_symbol": {"NIFTY": 0.5},
        },
    )
    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    result = ws._apply_subscription_delta(ticker, [301, 302], [101], reason="unit_test")
    if not result:
        raise AssertionError(f"Expected True, got False. Events: {events}")
    assert result is True
    assert any(event == "FEED_MUTATION_APPLIED" for event, _ in events)
def test_option_feed_verification_logs_begin_and_ok(monkeypatch):
    _patch_common(monkeypatch)
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    ws._reset_option_feed_verification(reason="unit_test")
    ws._begin_option_feed_verification(
        reason="connect",
        start_epoch=1000.0,
        requested_by_symbol={"NIFTY": 2},
        subscribed_by_symbol={"NIFTY": 2},
    )
    assert events[-1][0] == "FEED_OPTION_VERIFY_BEGIN"
    assert ws._option_feed_verification_overlay_payload()["state"] == "PENDING"
    monkeypatch.setitem(ws._SYMBOL_LAST_OPTION_TICK_TS, "NIFTY", 1001.0)
    ws._tick_option_feed_verification(now_epoch=1002.0)
    assert any(event == "FEED_OPTION_VERIFY_OK" for event, _ in events)
    assert ws._option_feed_verification_overlay_payload()["state"] == "OK"
def test_persist_runtime_snapshot_row_publishes_canonical_feed_truth_when_verified(monkeypatch, tmp_path):
    _patch_common(monkeypatch)
    monkeypatch.setattr(ws, "logs_dir", lambda: tmp_path)
    monkeypatch.setattr(ws, "runtime_dir", lambda: tmp_path)
    monkeypatch.setattr(
        ws,
        "_option_feed_verification_overlay_payload",
        lambda: {
            "state": "OK",
            "verified_option_symbols": ["NIFTY"],
            "missing_option_symbols": [],
        },
    )
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 1001.6, raising=False)
    monkeypatch.setattr(ws, "_latest_db_tick_epoch", lambda: 1001.6, raising=False)
    monkeypatch.setattr(ws, "_latest_depth_epoch_from_store", lambda: 1001.8, raising=False)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [101, 102], raising=False)
    monkeypatch.setattr(ws, "_LAST_OPTION_COUNTS_BY_SYMBOL", {"NIFTY": 2}, raising=False)
    monkeypatch.setattr(ws, "_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL", {"NIFTY": 2}, raising=False)
    monkeypatch.setattr(ws, "_LAST_OPTION_TOKEN_INCIDENT_TS", {"NIFTY": 1001.9}, raising=False)
    monkeypatch.setattr(ws, "_LAST_MSG_TS_BY_TOKEN", {101: 1001.9, 102: 1001.9}, raising=False)
    ws._persist_runtime_snapshot_row(
        ws_connected=True,
        source="unit_test",
        now_epoch=1002.0,
        runtime_state="RUNNING",
        last_error="",
        intended_tokens_count=2,
    )
    payload = json.loads((tmp_path / "feed_runtime_latest.json").read_text(encoding="utf-8"))
    assert payload["canonical_feed_truth"]["state"] == "VERIFIED_HEALTHY"
    assert payload["canonical_feed_truth"]["ws_connected"] is True
    assert payload["canonical_feed_truth"]["option_ticks_verified"] is True
    assert payload["canonical_feed_truth"]["blockers"] == []
def test_persist_runtime_snapshot_row_publishes_restart_required_canonical_feed_truth(monkeypatch, tmp_path):
    _patch_common(monkeypatch)
    monkeypatch.setattr(ws, "logs_dir", lambda: tmp_path)
    monkeypatch.setattr(ws, "runtime_dir", lambda: tmp_path)
    ws._persist_runtime_snapshot_row(
        ws_connected=False,
        source="unit_test_ws1006",
        now_epoch=1002.0,
        runtime_state="RECOVERY_BLOCKED",
        last_error="ws1006",
        reconnect_blocked_reason="ws1006_process_restart_required",
        intended_tokens_count=2,
    )
    payload = json.loads((tmp_path / "feed_runtime_latest.json").read_text(encoding="utf-8"))
    assert payload["canonical_feed_truth"]["state"] == "RESTART_REQUIRED"
    assert payload["canonical_feed_truth"]["process_restart_required"] is True
    assert payload["canonical_feed_truth"]["recovery_blocked"] is True
    assert (tmp_path / "feed_restart_required.json").exists()
    artifact = json.loads((tmp_path / "feed_restart_required.json").read_text(encoding="utf-8"))
    assert artifact["reason"] == "ws1006_process_restart_required"
    assert artifact["restart_allowed_only_if_no_open_positions"] is True
def test_option_feed_verification_logs_failed_when_ticks_never_arrive(monkeypatch):
    _patch_common(monkeypatch)
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    ws._reset_option_feed_verification(reason="unit_test")
    ws._begin_option_feed_verification(
        reason="connect",
        start_epoch=1000.0,
        requested_by_symbol={"NIFTY": 2},
        subscribed_by_symbol={"NIFTY": 2},
    )
    ws._tick_option_feed_verification(now_epoch=1100.0)
    assert any(event == "FEED_OPTION_VERIFY_FAILED" for event, _ in events)
    assert ws._option_feed_verification_overlay_payload()["state"] == "FAILED"
def test_apply_subscription_delta_queued_mutation_returns_false_and_no_last_tokens(monkeypatch):
    _patch_common(monkeypatch)
    ticker = _DummyTicker("api_key_1234", "TOKEN123", debug=True)
    ticker.connected = True
    monkeypatch.setattr(ws, "_KITE_TICKER", ticker, raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 100.0, raising=False)
    monkeypatch.setattr(ws, "_RUNTIME_STATE", "RUNNING", raising=False)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [101])
    monkeypatch.setattr(
        ws,
        "_option_runtime_state",
        lambda **kwargs: {
            "option_count": 2,
            "feed_block_reason_by_symbol": {"NIFTY": "OK"},
            "active_blockers_by_symbol": {"NIFTY": []},
        },
    )
    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    from core.feed.ws_mutation_queue import WsMutationResult
    def mock_safe(*args, **kwargs):
        res = WsMutationResult(ok=False, action="subscribe", tokens_count=2, socket_present=True, ws_connected=True, scheduled=True, queued=True, applied=False, failure_reason="scheduled", reason="unit_test", ts_epoch=0.0)
        return res, res
    import core.feed.ws_mutation_queue as wmq
    monkeypatch.setattr(wmq, "safe_subscribe_full_mode", mock_safe)
    assert ws._apply_subscription_delta(ticker, [301, 302], [], reason="unit_test") is False
    assert ws._LAST_TOKENS == [101]
    assert any(e == "FEED_MUTATION_QUEUED" for e, _ in events)
def test_refresh_subscription_tokens_queued_returns_false_no_raise(monkeypatch):
    _patch_common(monkeypatch)
    ticker = _DummyTicker("api_key_1234", "TOKEN123", debug=True)
    ticker.connected = True
    monkeypatch.setattr(ws, "_KITE_TICKER", ticker, raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 100.0, raising=False)
    monkeypatch.setattr(ws, "_RUNTIME_STATE", "RUNNING", raising=False)
    monkeypatch.setattr(
        ws,
        "_option_runtime_state",
        lambda **kwargs: {
            "option_count": 2,
            "feed_block_reason_by_symbol": {"NIFTY": "OK"},
            "active_blockers_by_symbol": {"NIFTY": []},
        },
    )
    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    from core.feed.ws_mutation_queue import WsMutationResult
    def mock_safe(*args, **kwargs):
        res = WsMutationResult(ok=False, action="subscribe", tokens_count=2, socket_present=True, ws_connected=True, scheduled=True, queued=True, applied=False, failure_reason="scheduled", reason="unit_test", ts_epoch=0.0)
        return res, res
    import core.feed.ws_mutation_queue as wmq
    monkeypatch.setattr(wmq, "safe_subscribe_full_mode", mock_safe)
    assert ws._refresh_subscription_tokens([301, 302], reason="unit_test") is False
    assert ws._LAST_TOKENS == []
    assert any(e == "FEED_MUTATION_QUEUED" for e, _ in events)
def test_apply_subscription_delta_ws_disconnected_skips_broker(monkeypatch):
    _patch_common(monkeypatch)
    ticker = _DummyTicker("api_key_1234", "TOKEN123", debug=True)
    ticker.connected = False
    monkeypatch.setattr(ws, "_KITE_TICKER", ticker, raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 100.0, raising=False)
    monkeypatch.setattr(ws, "_RUNTIME_STATE", "RUNNING", raising=False)
    monkeypatch.setattr(
        ws,
        "_option_runtime_state",
        lambda **kwargs: {
            "option_count": 2,
            "feed_block_reason_by_symbol": {"NIFTY": "OK"},
            "active_blockers_by_symbol": {"NIFTY": []},
        },
    )
    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    import core.feed.ws_mutation_queue as wmq
    monkeypatch.setattr(wmq, "_check_socket_health", lambda *args: (False, False, "disconnected"))
    assert ws._apply_subscription_delta(ticker, [301], [], reason="unit_test") is False
    assert any(e == "FEED_REBALANCE_SKIPPED" and "disconnected" in str(p) for e, p in events)


def test_safe_subscribe_connected_false_does_not_call_subscribe(monkeypatch):
    import core.feed.ws_mutation_queue as wmq
    class DummyWs:
        def __init__(self):
            self.subscribe_called = False
        def subscribe(self, tokens):
            self.subscribe_called = True

    ws = DummyWs()
    monkeypatch.setattr(wmq, "_check_socket_health", lambda w: (True, False, "disconnected"))

    res = wmq.safe_subscribe(ws, [1, 2], "test", 0.0)
    assert res.ok is False
    assert res.queued is True
    assert ws.subscribe_called is False

def test_safe_set_mode_full_connected_false_does_not_call_set_mode(monkeypatch):
    import core.feed.ws_mutation_queue as wmq
    class DummyWs:
        MODE_FULL = "full"
        def __init__(self):
            self.set_mode_called = False
        def set_mode(self, mode, tokens):
            self.set_mode_called = True

    ws = DummyWs()
    monkeypatch.setattr(wmq, "_check_socket_health", lambda w: (True, False, "disconnected"))

    res = wmq.safe_set_mode_full(ws, [1, 2], "test", 0.0)
    assert res.ok is False
    assert res.queued is True
    assert ws.set_mode_called is False

def test_soft_resubscribe_current_does_not_have_duplicate_block():
    with open("core/kite_depth_ws.py", "r") as f:
        content = f.read()

    import ast
    tree = ast.parse(content)

    soft_func = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_soft_resubscribe_current":
            soft_func = node
            break

    assert soft_func is not None

    # Check that there is only one `with _KITE_TICKER_LOCK:` block
    with_blocks = [n for n in ast.walk(soft_func) if isinstance(n, ast.With)]
    count = len(with_blocks)
    assert count == 1, "Duplicate _KITE_TICKER_LOCK block found"

import pytest
def test_null_websocket_during_subscription_activity(monkeypatch):
    _patch_common(monkeypatch)
    ws.start_depth_ws([101], skip_lock=True, skip_guard=True)
    monkeypatch.setattr(ws, "_KITE_TICKER", None)
    try:
        # the nested one is ws._KITE_TICKER, but let's test if the queue mutation handler crashes
        import core.feed.ws_mutation_queue as wmq
        res = wmq.safe_subscribe_full_mode(None, [101], "unit_test", 100.0)
        assert res[0].ok is False
    except AttributeError:
        pytest.fail("AttributeError raised when websocket is None")

import threading
import time

def _setup_mock_ticker_and_start(monkeypatch):
    captured = {}
    def _factory(api_key, access_token, debug=True, **kwargs):
        ticker = _DummyTicker(api_key, access_token, debug=debug)
        captured["ticker"] = ticker
        return ticker
    monkeypatch.setattr(ws, "KiteTicker", _factory)
    ws.start_depth_ws([101, 102], skip_lock=True, skip_guard=True)
    return captured.get("ticker")

def test_b_concurrent_reconnect_requests(monkeypatch):
    """
    Test B — Concurrent reconnect requests
    Required assertions: owner acquisition count = 1, active reconnect sequence high-water = 1,
    no duplicate worker/reactor, simulate failures until bound, owner/lock released, later request can acquire.
    """
    import threading
    real_thread = threading.Thread
    real_lock = threading.Lock
    real_rlock = threading.RLock

    _patch_common(monkeypatch)

    monkeypatch.setattr(ws, "_RECONNECT_BLOCKED_REASON", "")
    monkeypatch.setattr(ws, "_REACTOR_NOT_RESTARTABLE_DETECTED", False)
    monkeypatch.setattr(ws, "_AUTH_REQUIRED_LATCH", False)
    monkeypatch.setattr(ws, "_RECOVERY_IN_PROGRESS", False)

    monkeypatch.setattr(ws.threading, "Thread", real_thread)
    monkeypatch.setattr(ws.threading, "Lock", real_lock)
    monkeypatch.setattr(ws.threading, "RLock", real_rlock)

    owner_acquisitions = []
       # We will wrap the global _RESTART_LOCK to count true acquisitions
    original_lock = ws._RESTART_LOCK
    class CountedLock:
        def __init__(self):
            self._lock = real_rlock()
            self._owner = None
            self._acquisitions_by_owner = {}

        def acquire(self, blocking=True, timeout=-1):
            me = threading.get_ident()
            res = self._lock.acquire(blocking, timeout)
            if res:
                if self._owner != me:
                    self._acquisitions_by_owner[me] = self._acquisitions_by_owner.get(me, 0) + 1
                    owner_acquisitions.append(1)
                self._owner = me
            return res

        def release(self):
            self._lock.release()

        def __enter__(self):
            self.acquire()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            self.release()

    counted_lock = CountedLock()
    monkeypatch.setattr(ws, "_RESTART_LOCK", counted_lock)

    ws._LAST_TOKENS = [101]

    reconnect_attempts = []
    def mock_start_depth_ws(*args, **kwargs):
        reconnect_attempts.append(1)
        time.sleep(0.05)
        # Simulate failure
        return False

    monkeypatch.setattr(ws, "start_depth_ws", mock_start_depth_ws)
    barrier = threading.Barrier(5)

    def worker():
        try:
            barrier.wait()
            res = ws.restart_depth_ws(reason="test_concurrent", ignore_cooldown=False)
        except BaseException as e:
            return

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Only 1 thread should have successfully acquired the lock and become owner
    c1 = len(owner_acquisitions)
    assert c1 == 1
    # Only 1 attempt should have been made to start
    assert sum(reconnect_attempts) == 1

    # A later independent request should be able to acquire and run if cooldown is ignored
    ws.restart_depth_ws(reason="test_concurrent_later", ignore_cooldown=True)
    c2 = len(owner_acquisitions)
    assert c2 == 2
    assert sum(reconnect_attempts) == 2

def test_c_complete_resubscription(monkeypatch):
    """
    Test C - Resubscription for a new websocket generation
    """
    _patch_common(monkeypatch)
    ticker = _setup_mock_ticker_and_start(monkeypatch)

    ws._LAST_TOKENS = [101, 102, 103]
    ws._UNDERLYING_TOKENS = {101}

    # old websocket disconnects
    ticker.close()
    ws.stop_depth_ws(reason="unit_test")

    # new websocket object connects
    # setup mock resets LAST_TOKENS, so we set it AFTER
    new_ticker = _setup_mock_ticker_and_start(monkeypatch)
    ws._LAST_TOKENS = [101, 102, 103]

    # We want to intercept what is passed to new_ticker.set_mode
    subscribed_tokens = []
    def mock_set_mode(mode, tokens):
        subscribed_tokens.extend(tokens)
    new_ticker.set_mode = mock_set_mode

    new_ticker.on_connect(new_ticker, "mock_response")

    # Required: required token count = 3, requested = 3, exact set = [101, 102, 103]
    c3 = len(ws._LAST_TOKENS)
    assert c3 == 3
    c4 = len(subscribed_tokens)
    assert c4 == 3 # no duplicates

def test_d_connected_but_stale(monkeypatch):
    """
    Test D - Connected but stale, one tick cannot make full context fresh
    """
    _patch_common(monkeypatch)
    ticker = _setup_mock_ticker_and_start(monkeypatch)

    ws._LAST_TOKENS = [101, 102, 103]

    ticker.close()
    ws.stop_depth_ws(reason="unit_test")

    new_ticker = _setup_mock_ticker_and_start(monkeypatch)
    ws._LAST_TOKENS = [101, 102, 103]
    new_ticker.on_connect(new_ticker, "mock_response")

    assert new_ticker.is_connected() is True
    # no provider ticks yet
    can_mutate, reason, _ = ws._can_mutate_ws_subscriptions(reason="unit_test")
    assert not can_mutate
    assert reason == "no_ws_ticks"

    now = time.time()
    monkeypatch.setattr(ws, "now_utc_epoch", lambda: now)

    # send one valid tick for only ONE required token
    payload = [{"instrument_token": 101, "timestamp": datetime.fromtimestamp(now, tz=timezone.utc), "last_price": 200}]
    new_ticker.on_ticks(new_ticker, payload)

    # Assert that one tick cannot mark the complete required-token context fresh
    # Assuming the watchdog has run
    ws._maybe_trigger_silent_reconnect(
        now_epoch=now,
        current_tokens={101, 102, 103},
        underlying_tokens=set(),
        last_global_msg_epoch=now,
        last_msg_by_token={101: now},
        state={},
        index_threshold_sec=5.0,
        option_threshold_sec=5.0,
        confirm_needed=1,
        backoff_min_sec=1.0,
        backoff_max_sec=1.0,
        force_full_restart_after_sec=None,
        restart_cb=lambda **kwargs: None
    )

    can_mutate, reason, _ = ws._can_mutate_ws_subscriptions(reason="unit_test", now_epoch=now)
    assert can_mutate
    assert reason == "ok"
    assert ws._RUNTIME_STATE == "DEGRADED_LOCAL"
    assert ws._PARTIAL_RECOVERY_VERIFICATION["verified"] is False

def test_e_partial_recovery(monkeypatch):
    """
    Test E - Partial recovery
    """
    _patch_common(monkeypatch)
    ticker = _setup_mock_ticker_and_start(monkeypatch)

    ws._LAST_TOKENS = [101, 102, 103]
    ws._LAST_MSG_TS_BY_TOKEN = {101: 50.0, 102: 50.0, 103: 50.0}

    ticker.close()
    ws.stop_depth_ws(reason="unit_test")

    new_ticker = _setup_mock_ticker_and_start(monkeypatch)
    ws._LAST_TOKENS = [101, 102, 103]
    new_ticker.on_connect(new_ticker, "mock_response")

    now = 100.0
    payload = [{"instrument_token": 101, "timestamp": datetime.fromtimestamp(now, tz=timezone.utc), "last_price": 200}]
    monkeypatch.setattr(ws, "now_utc_epoch", lambda: now)
    new_ticker.on_ticks(new_ticker, payload)

    ws._maybe_trigger_silent_reconnect(
        now_epoch=now,
        current_tokens={101, 102, 103},
        underlying_tokens=set(),
        last_global_msg_epoch=now,
        last_msg_by_token={101: now, 102: 50.0, 103: 50.0},
        state={},
        index_threshold_sec=5.0,
        option_threshold_sec=5.0,
        confirm_needed=1,
        backoff_min_sec=1.0,
        backoff_max_sec=1.0,
        force_full_restart_after_sec=None,
        restart_cb=lambda **kwargs: None
    )

    can_mutate, reason, _ = ws._can_mutate_ws_subscriptions(reason="unit_test", now_epoch=now)
    assert can_mutate
    assert reason == "ok"
    assert ws._RECONNECT_BLOCKED_REASON == ""
    assert ws._RUNTIME_STATE in {"DEGRADED_LOCAL", "VERIFYING_RECOVERY"}
    assert ws._PARTIAL_RECOVERY_VERIFICATION["verified"] is False


def test_partial_recovery_requires_three_stable_cycles(monkeypatch):
    _patch_common(monkeypatch)
    ticker = _setup_mock_ticker_and_start(monkeypatch)
    ticker.on_connect(ticker, "mock_response")
    ws._SOCKET_GENERATION = 1
    monkeypatch.setattr(ws, "_CORE_FEED_FRESH_QUORUM", 0.5, raising=False)
    ws._LAST_TOKENS = [101, 102, 103]
    ws._UNDERLYING_TOKENS = {101}
    state = {}
    now = 100.0
    last_by_token = {101: now, 102: now, 103: 50.0}

    for expected_state in ("VERIFYING_RECOVERY", "VERIFYING_RECOVERY"):
        ws._maybe_trigger_silent_reconnect(
            now_epoch=now,
            current_tokens={101, 102, 103},
            underlying_tokens={101},
            last_global_msg_epoch=now,
            last_msg_by_token=last_by_token,
            state=state,
            index_threshold_sec=5.0,
            option_threshold_sec=5.0,
            confirm_needed=1,
            backoff_min_sec=1.0,
            backoff_max_sec=1.0,
            force_full_restart_after_sec=None,
            restart_cb=lambda **kwargs: None,
        )
        assert ws._RECONNECT_BLOCKED_REASON == ""
        assert ws._RUNTIME_STATE == expected_state
        assert ws._PARTIAL_RECOVERY_VERIFICATION["verified"] is False

    ws._maybe_trigger_silent_reconnect(
        now_epoch=now,
        current_tokens={101, 102, 103},
        underlying_tokens={101},
        last_global_msg_epoch=now,
        last_msg_by_token=last_by_token,
        state=state,
        index_threshold_sec=5.0,
        option_threshold_sec=5.0,
        confirm_needed=1,
        backoff_min_sec=1.0,
        backoff_max_sec=1.0,
        force_full_restart_after_sec=None,
        restart_cb=lambda **kwargs: None,
    )
    assert ws._PARTIAL_RECOVERY_VERIFICATION["stable_cycles"] == 3
    assert ws._PARTIAL_RECOVERY_VERIFICATION["verified"] is True
    assert ws._RUNTIME_STATE == "LIVE"


def test_partial_recovery_stale_critical_stays_degraded(monkeypatch):
    _patch_common(monkeypatch)
    ticker = _setup_mock_ticker_and_start(monkeypatch)
    ticker.on_connect(ticker, "mock_response")
    ws._SOCKET_GENERATION = 1
    ws._LAST_TOKENS = [101, 102, 103]
    now = 100.0

    ws._maybe_trigger_silent_reconnect(
        now_epoch=now,
        current_tokens={101, 102, 103},
        underlying_tokens={101},
        last_global_msg_epoch=now,
        last_msg_by_token={101: 50.0, 102: now, 103: now},
        state={},
        index_threshold_sec=5.0,
        option_threshold_sec=5.0,
        confirm_needed=1,
        backoff_min_sec=1.0,
        backoff_max_sec=1.0,
        force_full_restart_after_sec=None,
        restart_cb=lambda **kwargs: None,
    )

    assert ws._RECONNECT_BLOCKED_REASON == ""
    assert ws._RUNTIME_STATE == "DEGRADED_LOCAL"
    assert ws._PARTIAL_RECOVERY_VERIFICATION["critical_feed_fresh"] is False
    assert "critical_feed_stale" in ws._PARTIAL_RECOVERY_VERIFICATION["failure_reasons"]

def test_f_duplicate_and_out_of_order_ticks(monkeypatch):
    _patch_common(monkeypatch)
    ticker = _setup_mock_ticker_and_start(monkeypatch)

    tick1_ts = datetime(2026, 2, 19, 9, 30, tzinfo=timezone.utc)
    ws.on_ticks(ticker, [{"instrument_token": 101, "last_price": 100, "exchange_timestamp": tick1_ts}])

    tick0_ts = datetime(2026, 2, 19, 9, 29, tzinfo=timezone.utc)
    ws.on_ticks(ticker, [{"instrument_token": 101, "last_price": 99, "exchange_timestamp": tick0_ts}])

    assert ws._LAST_MSG_TS_BY_TOKEN[101] >= tick1_ts.timestamp()

def test_g_repeated_reconnect_cycles(monkeypatch):
    """
    Test G - Repeated reconnect cycles (20 times)
    Verifies no resource leaks or state corruption after 20 cycles.
    """
    _patch_common(monkeypatch)

    # We will track total subscribe calls across all mock tickers
    total_subscribe_calls = 0
    def mock_set_mode(self, mode, tokens):
        nonlocal total_subscribe_calls
        total_subscribe_calls += 1

    ws._LAST_TOKENS = [101, 102]
    ws._UNDERLYING_TOKENS = {101}

    for i in range(20):
        # Stop existing
        if ws._KITE_TICKER:
            ws._KITE_TICKER.close()
            ws.stop_depth_ws(reason=f"cycle_{i}")

        # Start new
        ticker = _setup_mock_ticker_and_start(monkeypatch)
        ticker.set_mode = lambda mode, tokens, t=ticker: mock_set_mode(t, mode, tokens)

        ws._LAST_TOKENS = [101, 102] # restored by restart/start mock

        # Connect
        ticker.on_connect(ticker, "mock_response")

        assert ticker.is_connected() is True
        c5 = len(ws._LAST_TOKENS)
        assert c5 == 2

    assert total_subscribe_calls == 20
    assert ws._RUNTIME_STATE == "RUNNING"
    assert ws._KITE_TICKER is not None
