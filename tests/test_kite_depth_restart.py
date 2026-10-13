import core.kite_depth_ws as ws
from core.auth import reset_kite_runtime_credentials_guard
import core.incidents as incidents
import core.storage as storage
from core.feed_recovery_coordinator import FeedRecoveryCoordinator
from config import config as cfg
import json
import pytest
import threading

_REAL_THREAD = threading.Thread


def _commit_test_option_ownership(contracts):
    """Model completed local subscribe + FULL-mode application for test tokens."""
    generation = ws._current_socket_generation()
    ws._OPTION_OWNERSHIP_BOOTSTRAP_GENERATION = generation
    ws._invalidate_applied_option_ownership(
        "test_restart_setup", socket_generation=generation
    )
    expected = sorted(int(token) for token in contracts)
    desired_revision = ws.record_desired_option_contracts(
        contracts, expected_tokens=expected, source="test_instrument_master"
    )
    base, invalidated = ws._begin_applied_option_mutation(
        "test_confirmed_subscription", affected_tokens=expected
    )
    assert ws._commit_applied_option_ownership(
        socket_generation=generation,
        desired_revision=desired_revision,
        base_snapshot=base,
        invalidated_revision=invalidated.revision,
        confirmed_tokens=expected,
        subscribe_tokens=expected,
        fresh_socket=True,
        provenance="test_local_api_success",
    )


def _ensure_test_restart_candidate():
    """Keep restart-policy tests focused on their policy gate, not raw caches."""
    tokens = list(ws._LAST_TOKENS or [])
    underlying = set(ws._UNDERLYING_TOKENS or set())
    option_tokens = [token for token in tokens if token not in underlying]
    if option_tokens:
        _record_validated_candidate(tokens, option_tokens)


def _record_validated_candidate(tokens, option_tokens, *, budget=123):
    contracts = {
        int(token): {
            "symbol": "NIFTY",
            "instrument_type": "CE" if index % 2 == 0 else "PE",
            "exchange": "NFO",
            "expiry": "2026-12-31",
            "strike": 25000 + index * 50,
        }
        for index, token in enumerate(option_tokens)
    }
    ws.record_desired_option_contracts(
        contracts, expected_tokens=list(option_tokens), source="test_validated_plan"
    )
    return ws.record_desired_subscription_candidate(
        tokens,
        option_tokens=list(option_tokens),
        configured_budget=budget,
        source="test_validated_plan",
        observation_required=False,
    )


@pytest.fixture(autouse=True)
def mock_check_socket_health(monkeypatch):
    monkeypatch.setattr("core.feed.ws_mutation_queue._check_socket_health", lambda ws: (True, True, None))

from types import SimpleNamespace


def test_stale_generation_callback_queues_old_ticker_close_once(monkeypatch):
    class _Ticker:
        def __init__(self):
            self.close_calls = 0

        def close(self):
            self.close_calls += 1

    old_ticker = _Ticker()
    active_ticker = _Ticker()
    queued_calls = []
    fake_reactor = SimpleNamespace(running=True, callFromThread=queued_calls.append)
    monkeypatch.setattr("twisted.internet.reactor", fake_reactor)
    monkeypatch.setattr(ws, "_KITE_TICKER", active_ticker)

    assert ws._request_stale_ticker_retirement(
        old_ticker, socket_generation=2, active_generation=8
    ) is True
    assert ws._request_stale_ticker_retirement(
        old_ticker, socket_generation=2, active_generation=8
    ) is False
    assert old_ticker.close_calls == 0
    assert active_ticker.close_calls == 0
    assert len(queued_calls) == 1

    queued_calls[0]()

    assert old_ticker.close_calls == 1
    assert active_ticker.close_calls == 0


def test_stale_ticker_close_is_skipped_if_it_becomes_active(monkeypatch):
    class _Ticker:
        def __init__(self):
            self.close_calls = 0

        def close(self):
            self.close_calls += 1

    old_ticker = _Ticker()
    queued_calls = []
    fake_reactor = SimpleNamespace(running=True, callFromThread=queued_calls.append)
    monkeypatch.setattr("twisted.internet.reactor", fake_reactor)
    monkeypatch.setattr(ws, "_KITE_TICKER", _Ticker())

    assert ws._request_stale_ticker_retirement(
        old_ticker, socket_generation=2, active_generation=8
    ) is True
    monkeypatch.setattr(ws, "_KITE_TICKER", old_ticker)

    queued_calls[0]()

    assert old_ticker.close_calls == 0


def test_ticker_ownership_lock_covers_identity_check_and_close(monkeypatch):
    close_started = threading.Event()
    release_close = threading.Event()
    activation_attempted = threading.Event()
    activation_completed = threading.Event()

    class _Ticker:
        def __init__(self, *, block_close=False):
            self.close_calls = 0
            self.block_close = block_close

        def close(self):
            self.close_calls += 1
            if self.block_close:
                close_started.set()
                assert release_close.wait(timeout=2.0)

    old_ticker = _Ticker(block_close=True)
    queued_calls = []
    fake_reactor = SimpleNamespace(running=True, callFromThread=queued_calls.append)
    monkeypatch.setattr("twisted.internet.reactor", fake_reactor)
    monkeypatch.setattr(ws, "_KITE_TICKER", _Ticker())

    assert ws._request_stale_ticker_retirement(
        old_ticker, socket_generation=2, active_generation=8
    ) is True

    close_thread = _REAL_THREAD(target=queued_calls[0])
    close_thread.start()
    assert close_started.wait(timeout=2.0)

    def _activate_old_ticker():
        activation_attempted.set()
        with ws._KITE_TICKER_LOCK:
            ws._KITE_TICKER = old_ticker
        activation_completed.set()

    activation_thread = _REAL_THREAD(target=_activate_old_ticker)
    activation_thread.start()
    try:
        assert activation_attempted.wait(timeout=2.0)
        assert not activation_completed.wait(timeout=0.05)
    finally:
        release_close.set()
        close_thread.join(timeout=2.0)
        activation_thread.join(timeout=2.0)

    assert not close_thread.is_alive()
    assert not activation_thread.is_alive()
    assert activation_completed.is_set()
    assert old_ticker.close_calls == 1


def test_active_ticker_is_never_queued_for_stale_retirement(monkeypatch):
    active_ticker = SimpleNamespace(close_calls=0)
    queued_calls = []
    fake_reactor = SimpleNamespace(running=True, callFromThread=queued_calls.append)
    monkeypatch.setattr("twisted.internet.reactor", fake_reactor)
    monkeypatch.setattr(ws, "_KITE_TICKER", active_ticker)

    assert ws._request_stale_ticker_retirement(
        active_ticker, socket_generation=8, active_generation=9
    ) is False
    assert queued_calls == []
    assert active_ticker.close_calls == 0


def test_stale_ticker_retirement_fails_closed_without_running_reactor(monkeypatch):
    class _Ticker:
        def __init__(self):
            self.close_calls = 0

        def close(self):
            self.close_calls += 1

    old_ticker = _Ticker()
    queued_calls = []
    fake_reactor = SimpleNamespace(running=False, callFromThread=queued_calls.append)
    monkeypatch.setattr("twisted.internet.reactor", fake_reactor)
    monkeypatch.setattr(ws, "_KITE_TICKER", _Ticker())
    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload: events.append(event))

    assert ws._request_stale_ticker_retirement(
        old_ticker, socket_generation=2, active_generation=8
    ) is False

    assert old_ticker.close_calls == 0
    assert queued_calls == []
    assert not hasattr(old_ticker, "_tradebot_stale_retirement_queued")
    assert "FEED_STALE_GENERATION_RETIREMENT_ERROR" in events


@pytest.fixture(autouse=True)
def _reset_ws_runtime_state(monkeypatch):
    # These tests exercise ordinary production-feed restart policy unless a
    # test opts into observer mode explicitly.
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", False, raising=False)
    generation = ws._current_socket_generation()
    ws.invalidate_desired_subscription_candidate("test_isolation")
    ws.reset_market_event_graph_observation_plan_state()
    ws.record_desired_option_contracts(
        {}, expected_tokens=[], source="test_isolation"
    )
    ws._invalidate_applied_option_ownership(
        "test_isolation", socket_generation=generation
    )
    ws._OPTION_OWNERSHIP_BOOTSTRAP_GENERATION = 0
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
        "_CALLBACK_UNREADY_REASON": "",
        "_LAST_FULL_RESTART_EPOCH": 0.0,
        "_FULL_RESTARTS": [],
        "_FEED_HEALTH_DURATION_STATE": None,
        "_LAST_RESTART_VERIFY_BLOCK_LOG_EPOCH": 0.0,
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


def test_socket_factory_failure_does_not_poison_callback_owner_and_retry_succeeds(monkeypatch, tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)

    class _RestClient:
        def profile(self):
            return {"user_id": "ABCD1234"}

    class _FakeTicker:
        def connect(self, threaded=True):
            assert threaded is True

    calls = {"factory": 0}

    def ticker_factory(**_kwargs):
        calls["factory"] += 1
        if calls["factory"] == 1:
            raise RuntimeError("transient factory failure")
        return _FakeTicker()

    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "runtime.sqlite"), raising=False)
    monkeypatch.setattr(cfg, "KITE_USE_DEPTH", True, raising=False)
    monkeypatch.setattr(cfg, "KITE_API_KEY", "test_key", raising=False)
    monkeypatch.setattr(ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(ws, "KiteTicker", object(), raising=True)
    monkeypatch.setattr(ws, "get_kite_ticker", ticker_factory, raising=True)
    monkeypatch.setattr(ws, "get_kite_auth_health", lambda force=True: {"ok": True}, raising=True)
    monkeypatch.setattr(ws.kite_client, "ensure", lambda: _RestClient(), raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_api_key", "kite_test_key", raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_access_token", "token1234", raising=False)
    monkeypatch.setattr(ws, "_ensure_depth_ws_lock", lambda: True, raising=True)
    monkeypatch.setattr(ws, "_log_ws", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ws, "_persist_runtime_snapshot_row", lambda **_kwargs: None)
    monkeypatch.setattr(ws.lifecycle, "register", lambda *_args, **_kwargs: None)

    with pytest.raises(RuntimeError, match="transient factory failure"):
        ws.start_depth_ws([101], skip_lock=True, skip_guard=True)

    assert ws._CALLBACK_UNREADY_REASON == ""
    assert ws._RUNTIME_STATE == "SUBSCRIBE_FAILED"
    assert ws._CALLBACK_COORDINATOR.state.value == "running"
    assert ws.start_depth_ws([101], skip_lock=True, skip_guard=True) is True
    assert calls["factory"] == 2
    assert ws._CALLBACK_UNREADY_REASON == ""


@pytest.mark.parametrize("state", ["PENDING", "FAILED"])
def test_restart_verification_state_blocks_restart_before_side_effects(monkeypatch, state):
    events = []
    calls = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    monkeypatch.setattr(ws, "_LAST_TOKENS", [1, 2], raising=False)
    monkeypatch.setattr(ws, "_resubscribe_token_selection", lambda: calls.append("resolve"))
    monkeypatch.setattr(ws, "append_feed_forensic_event", lambda *a, **k: calls.append("forensic"))
    monkeypatch.setattr(ws, "stop_depth_ws", lambda **_kwargs: calls.append("stop"))
    monkeypatch.setattr(ws, "start_depth_ws", lambda *a, **k: calls.append("start"))
    monkeypatch.setattr(ws, "_persist_runtime_snapshot_row", lambda **_kwargs: calls.append("snapshot"))
    monkeypatch.setattr(ws, "_restart_verification_enabled", lambda: True)

    with ws._RESTART_VERIFY_LOCK:
        ws._FEED_RESTART_VERIFY_STATE = state
        ws._FEED_RESTART_VERIFY_REASON = "prior_restart"
        ws._FEED_RESTART_VERIFY_FAILURE_DETAIL = "verification_timeout" if state == "FAILED" else ""
        ws._FEED_RESTART_VERIFY_DEADLINE_EPOCH = 1234.0

    _ensure_test_restart_candidate()
    assert ws.restart_depth_ws(reason="retry", ignore_cooldown=True, force_full_restart=True) is False
    assert ws._schedule_restart_depth_ws(
        reason="watchdog_retry", ignore_cooldown=True, force_full_restart=True, source="test"
    ) is False
    assert calls == []
    blocked = [(event, payload) for event, payload in events if event == "FEED_RESTART_BLOCKED_BY_VERIFICATION"]
    assert blocked
    assert blocked[0][1]["verification_state"] == state
    assert blocked[0][1]["read_only"] is True
    assert blocked[0][1]["is_order_action"] is False
    assert blocked[0][1]["broker_api_called"] is False
    assert blocked[0][1]["allowed_for_live_execution"] is False


def test_restart_verification_block_preserves_auth_latch_priority(monkeypatch):
    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append(event))
    monkeypatch.setattr(ws, "_AUTH_REQUIRED_LATCH", True, raising=False)
    monkeypatch.setattr(ws, "_restart_verification_enabled", lambda: True)
    with ws._RESTART_VERIFY_LOCK:
        ws._FEED_RESTART_VERIFY_STATE = "PENDING"

    _ensure_test_restart_candidate()
    assert ws.restart_depth_ws(reason="auth_latched") is False
    assert "FEED_RESTART_BLOCKED_AUTH_REQUIRED" in events
    assert "FEED_RESTART_BLOCKED_BY_VERIFICATION" not in events


def test_failed_restart_verification_can_recover_from_fresh_proof(monkeypatch):
    monkeypatch.setattr(ws, "_restart_verification_enabled", lambda: True)
    monkeypatch.setattr(ws, "_restart_verification_live_recovery_proof", lambda _now: (True, "live_recovery_ok", {}))
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    with ws._SOCKET_GENERATION_LOCK:
        monkeypatch.setattr(ws, "_SOCKET_GENERATION", 30, raising=False)
    with ws._RESTART_VERIFY_LOCK:
        ws._FEED_RESTART_VERIFY_STATE = "FAILED"
        ws._FEED_RESTART_VERIFY_SOCKET_GENERATION = 30
        ws._FEED_RESTART_VERIFY_REASON = "previous_attempt"
        ws._FEED_RESTART_VERIFY_START_EPOCH = 100.0
        ws._FEED_RESTART_VERIFY_DEADLINE_EPOCH = 110.0
        ws._FEED_RESTART_VERIFY_CONNECT_EPOCH = 100.1
        ws._FEED_RESTART_VERIFY_SUBSCRIBE_EPOCH = 100.2
        ws._FEED_RESTART_VERIFY_FAILURE_DETAIL = "verification_timeout"

    ws._tick_feed_restart_verification(now_epoch=120.0)
    assert ws._restart_verification_restart_block() is None


def test_snapshot_state_does_not_bypass_generation_checked_failed_verifier(monkeypatch):
    monkeypatch.setattr(ws, "_restart_verification_enabled", lambda: True)
    monkeypatch.setattr(ws, "_tick_feed_restart_verification", lambda **_kwargs: None)
    monkeypatch.setattr(
        ws,
        "_restart_verification_live_recovery_proof",
        lambda _now: (_ for _ in ()).throw(AssertionError("snapshot path must not run a second proof")),
    )
    with ws._RESTART_VERIFY_LOCK:
        ws._FEED_RESTART_VERIFY_STATE = "FAILED"
        ws._FEED_RESTART_VERIFY_FAILURE_DETAIL = "verification_timeout"

    effective, detail = ws._effective_runtime_state_for_snapshot("RUNNING", now_epoch=120.0)

    assert effective == "RESTART_VERIFY_FAILED"
    assert detail == "verification_timeout"
    assert ws._FEED_RESTART_VERIFY_STATE == "FAILED"


def test_failed_verifier_is_polled_while_recovery_latch_remains_set(monkeypatch):
    monkeypatch.setattr(ws, "_restart_verification_enabled", lambda: True)
    monkeypatch.setattr(ws, "_restart_verification_live_recovery_proof", lambda _now: (True, "live_recovery_ok", {}))
    monkeypatch.setattr(ws, "now_utc_epoch", lambda: 120.0)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws, "_RECONNECT_BLOCKED_REASON", "causal_recovery_required", raising=False)
    with ws._SOCKET_GENERATION_LOCK:
        monkeypatch.setattr(ws, "_SOCKET_GENERATION", 31, raising=False)
    with ws._RESTART_VERIFY_LOCK:
        ws._FEED_RESTART_VERIFY_STATE = "FAILED"
        ws._FEED_RESTART_VERIFY_SOCKET_GENERATION = 31
        ws._FEED_RESTART_VERIFY_REASON = "previous_attempt"
        ws._FEED_RESTART_VERIFY_START_EPOCH = 100.0
        ws._FEED_RESTART_VERIFY_DEADLINE_EPOCH = 110.0
        ws._FEED_RESTART_VERIFY_CONNECT_EPOCH = 100.1
        ws._FEED_RESTART_VERIFY_SUBSCRIBE_EPOCH = 100.2
        ws._FEED_RESTART_VERIFY_FAILURE_DETAIL = "verification_timeout"

    ws._watchdog_tick_restart_verification_while_blocked()

    assert ws._FEED_RESTART_VERIFY_STATE == "OK"
    assert ws._RECONNECT_BLOCKED_REASON == "causal_recovery_required"
    assert ws._restart_verification_restart_block() is None


def test_soft_resubscribe_rechecks_verification_after_token_selection(monkeypatch):
    calls = []
    monkeypatch.setattr(ws, "_restart_verification_enabled", lambda: True)
    monkeypatch.setattr(ws, "get_current_feed_session_identity", lambda: {})
    monkeypatch.setattr(ws, "append_feed_forensic_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws, "_KITE_TICKER", object(), raising=False)
    monkeypatch.setattr(ws, "_use_native_reconnect", lambda: True)
    monkeypatch.setattr(ws, "_ws_connected_state", lambda: True)
    monkeypatch.setattr(ws, "_tick_option_feed_verification", lambda **_kwargs: None)
    monkeypatch.setattr(ws, "_attempt_causal_ws1006_recovery_clear", lambda **_kwargs: None)
    monkeypatch.setattr(ws, "_soft_resubscribe_eligibility", lambda **kwargs: (True, "eligible"))
    monkeypatch.setattr(ws, "_soft_resubscribe_current", lambda **kwargs: calls.append("mutate") or True)

    def _transition_during_token_selection():
        with ws._RESTART_VERIFY_LOCK:
            ws._FEED_RESTART_VERIFY_STATE = "PENDING"
        return [1], {}

    monkeypatch.setattr(ws, "_resubscribe_token_selection", _transition_during_token_selection)

    _ensure_test_restart_candidate()
    assert ws.restart_depth_ws(reason="racing_soft_restart") is False
    assert calls == []


@pytest.mark.parametrize(("state", "enabled"), [("IDLE", True), ("OK", True), ("PENDING", False)])
def test_restart_verification_gate_preserves_idle_ok_and_disabled_compatibility(monkeypatch, state, enabled):
    calls = []
    monkeypatch.setattr(ws, "_restart_verification_enabled", lambda: enabled)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws, "get_current_feed_session_identity", lambda: {})
    monkeypatch.setattr(ws, "append_feed_forensic_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(ws, "_resubscribe_token_selection", lambda: (calls.append("resolve") or ([], {})))
    with ws._RESTART_VERIFY_LOCK:
        ws._FEED_RESTART_VERIFY_STATE = state

    _ensure_test_restart_candidate()
    assert ws.restart_depth_ws(reason="compatibility_check") is False
    assert calls == ["resolve"]


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
    _ensure_test_restart_candidate()
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

    _ensure_test_restart_candidate()
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

    assert calls == {"persist": 1, "close": 0, "join_thread": 0, "join_ticker": 0}


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

    _ensure_test_restart_candidate()
    assert ws.restart_depth_ws(reason="first") is True
    assert calls["start"] == 1
    assert calls["stop"] == 1

    # Immediate second restart should be blocked by cooldown.
    _ensure_test_restart_candidate()
    assert ws.restart_depth_ws(reason="second") is False
    assert calls["start"] == 1
    assert calls["stop"] == 1


def test_restart_ignore_cooldown_allows_immediate_restart(monkeypatch):
    # This test isolates cooldown override behavior; restart verification is
    # covered separately and intentionally blocks while its state is PENDING.
    monkeypatch.setattr(cfg, "FEED_RESTART_VERIFY_ENABLE", False, raising=False)
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

    _ensure_test_restart_candidate()
    assert ws.restart_depth_ws(reason="first") is True
    _ensure_test_restart_candidate()
    assert ws.restart_depth_ws(reason="second_blocked") is False
    _ensure_test_restart_candidate()
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

    _ensure_test_restart_candidate()
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

    _ensure_test_restart_candidate()
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

    _ensure_test_restart_candidate()
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
    _ensure_test_restart_candidate()
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

    _ensure_test_restart_candidate()
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

    _ensure_test_restart_candidate()
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

    _ensure_test_restart_candidate()
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

    _ensure_test_restart_candidate()
    assert ws.restart_depth_ws(reason="unit_restart_disconnected_ticker") is True
    assert calls == {"soft": 0, "start": 1, "stop": 1}


def test_soft_resubscribe_uses_desired_tokens_when_flag_enabled(monkeypatch):
    calls = {"subscribe": [], "set_mode": []}
    events = []

    class _DummyTicker:
        MODE_FULL = "full"
        connected = True
        ws = object()

        def subscribe(self, tokens):
            calls["subscribe"].append(list(tokens))

        def set_mode(self, mode, tokens):
            assert mode == self.MODE_FULL
            calls["set_mode"].append(list(tokens))

        def is_connected(self):
            return True

    monkeypatch.setattr(ws, "_KITE_TICKER", _DummyTicker(), raising=False)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [1, 2, 3], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", list(range(1, 40)), raising=False)
    monkeypatch.setattr(ws, "_RUNTIME_STATE", "RUNNING", raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 100.0, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {1, 2, 3}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {1: "NIFTY", 2: "BANKNIFTY", 3: "SENSEX"}, raising=False)
    _record_validated_candidate(list(range(1, 40)), list(range(4, 40)))
    ws._OPTION_OWNERSHIP_BOOTSTRAP_GENERATION = ws._current_socket_generation()
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
        ws = object()

        def subscribe(self, tokens):
            calls["subscribe"].append(list(tokens))

        def set_mode(self, mode, tokens):
            assert mode == self.MODE_FULL
            calls["set_mode"].append(list(tokens))

        def is_connected(self):
            return True

    monkeypatch.setattr(ws, "_KITE_TICKER", _DummyTicker(), raising=False)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [11, 22, 33, 44], raising=False)
    ws.invalidate_desired_subscription_candidate("test_desired_unavailable")
    monkeypatch.setattr(ws, "_RUNTIME_STATE", "RUNNING", raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 100.0, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {11, 22, 33}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {11: "NIFTY", 22: "BANKNIFTY", 33: "SENSEX"}, raising=False)
    _commit_test_option_ownership({
        44: {"symbol": "NIFTY", "instrument_type": "CE", "exchange": "NFO", "expiry": "2026-12-31", "strike": 25000},
    })
    _record_validated_candidate(
        [11, 22, 33, 44], [44], budget=123
    )
    ws._OPTION_OWNERSHIP_BOOTSTRAP_GENERATION = -1
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    monkeypatch.delenv("FEED_USE_DESIRED_TOKENS", raising=False)

    assert ws._soft_resubscribe_current(reason="unit_test_flag_off") is True
    assert calls["subscribe"] == [[11, 22, 33, 44]]
    assert calls["set_mode"] == [[11, 22, 33, 44]]
    assert events[-1][0] == "FEED_MUTATION_APPLIED"
    assert events[-1][1]["desired_tokens_count"] == 4
    assert events[-1][1]["fallback_option_tokens_count"] == 1
    assert events[-1][1]["auto_recover_missing_options"] is False
    assert events[-1][1]["resubscribe_tokens_count"] == 4


def test_soft_resubscribe_auto_recovers_desired_tokens_when_current_is_underlyings_only(monkeypatch):
    calls = {"subscribe": [], "set_mode": []}
    events = []

    class _DummyTicker:
        MODE_FULL = "full"
        connected = True
        ws = object()

        def subscribe(self, tokens):
            calls["subscribe"].append(list(tokens))

        def set_mode(self, mode, tokens):
            assert mode == self.MODE_FULL
            calls["set_mode"].append(list(tokens))

        def is_connected(self):
            return True

    monkeypatch.setattr(ws, "_KITE_TICKER", _DummyTicker(), raising=False)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [1, 2, 3], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", list(range(1, 40)), raising=False)
    monkeypatch.setattr(ws, "_RUNTIME_STATE", "RUNNING", raising=False)
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", 100.0, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {1, 2, 3}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {1: "NIFTY", 2: "BANKNIFTY", 3: "SENSEX"}, raising=False)
    _record_validated_candidate(list(range(1, 40)), list(range(4, 40)))
    ws._OPTION_OWNERSHIP_BOOTSTRAP_GENERATION = ws._current_socket_generation()
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    monkeypatch.delenv("FEED_USE_DESIRED_TOKENS", raising=False)

    assert ws._soft_resubscribe_current(reason="unit_test_auto_recover") is True
    assert calls["subscribe"] == [list(range(1, 40))]
    assert calls["set_mode"] == [list(range(1, 40))]
    assert events[-1][0] == "FEED_MUTATION_APPLIED"
    assert events[-1][1]["fallback_option_tokens_count"] == 0
    assert events[-1][1]["auto_recover_missing_options"] is False
    assert events[-1][1]["token_source"] == "validated_desired_plan"
    assert events[-1][1]["resubscribe_tokens_count"] == 39


def test_full_restart_uses_desired_tokens_when_flag_enabled(monkeypatch):
    monkeypatch.setattr(ws, "_LAST_TOKENS", [1, 2, 3], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", list(range(1, 40)), raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {1, 2, 3}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {1: "NIFTY", 2: "BANKNIFTY", 3: "SENSEX"}, raising=False)
    _record_validated_candidate(list(range(1, 40)), list(range(4, 40)))
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

    _ensure_test_restart_candidate()
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
    _commit_test_option_ownership({
        101: {"symbol": "NIFTY", "instrument_type": "CE", "exchange": "NFO", "expiry": "2026-12-31", "strike": 25000},
        102: {"symbol": "NIFTY", "instrument_type": "PE", "exchange": "NFO", "expiry": "2026-12-31", "strike": 25000},
        201: {"symbol": "BANKNIFTY", "instrument_type": "CE", "exchange": "NFO", "expiry": "2026-12-31", "strike": 50000},
    })

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
    _commit_test_option_ownership({
        101: {"symbol": "NIFTY", "instrument_type": "CE", "exchange": "NFO", "expiry": "2026-12-31", "strike": 25000},
    })
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

    _ensure_test_restart_candidate()
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

    _ensure_test_restart_candidate()
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
        ws._begin_feed_restart_verification(
            reason=str(kwargs.get("restart_verification_reason") or "test"),
            start_epoch=1000.0,
            now_epoch=1000.0,
            socket_generation=ws._current_socket_generation(),
        )
        return True

    monkeypatch.setattr(ws, "start_depth_ws", _start)

    _ensure_test_restart_candidate()
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

    monkeypatch.setattr(ws, "_SOCKET_GENERATION", 20, raising=False)
    _commit_test_option_ownership({
        101: {"symbol": "NIFTY", "instrument_type": "CE", "exchange": "NFO", "expiry": "2026-12-31", "strike": 25000},
    })
    ws._begin_feed_restart_verification(reason="ws_error:1006", start_epoch=1000.0, now_epoch=1000.0, socket_generation=20)
    ws._record_feed_restart_verify_connect(now_epoch=1000.5, socket_generation=20)
    ws._record_feed_restart_verify_subscribe(now_epoch=1000.6, socket_generation=20)
    ws._record_feed_restart_verify_tick(token=101, receipt_epoch=1000.7, socket_generation=20)

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

    monkeypatch.setattr(ws, "_SOCKET_GENERATION", 20, raising=False)
    ws._begin_feed_restart_verification(reason="ws_error:1006", start_epoch=1000.0, now_epoch=1000.0, socket_generation=20)

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
        restart_attempt_allowed=True,
    )

    payload = _read_feed_runtime_latest(tmp_path)
    assert payload["runtime_state"] == "RESTART_VERIFY_FAILED"
    assert payload["restart_attempt_allowed"] is False
    assert payload["restart_attempted"] is False
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

    monkeypatch.setattr(ws, "_SOCKET_GENERATION", 20, raising=False)
    _commit_test_option_ownership({
        101: {"symbol": "NIFTY", "instrument_type": "CE", "exchange": "NFO", "expiry": "2026-12-31", "strike": 25000},
    })
    ws._begin_feed_restart_verification(reason="ws_error:1006", start_epoch=1000.0, now_epoch=1000.0, socket_generation=20)
    ws._tick_feed_restart_verification(now_epoch=1001.0)
    assert ws._FEED_RESTART_VERIFY_STATE == "FAILED"

    # A timeout before lifecycle evidence must remain latched until callbacks
    # from the still-active socket and a fresh option-feed proof arrive. No
    # manual FAILED -> PENDING state transition is allowed or needed.
    ws._record_feed_restart_verify_connect(socket_generation=20, now_epoch=1001.0)
    ws._record_feed_restart_verify_subscribe(socket_generation=20, now_epoch=1002.0)
    ws._record_feed_restart_verify_tick(token=101, receipt_epoch=1002.5, socket_generation=20)
    assert ws._FEED_RESTART_VERIFY_STATE == "FAILED"
    assert ws._FEED_RESTART_VERIFY_CONNECT_EPOCH == 1001.0
    assert ws._FEED_RESTART_VERIFY_SUBSCRIBE_EPOCH == 1002.0

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


def test_restart_subscription_verification_does_not_clear_ws1006_recovery_blocker(monkeypatch, tmp_path):
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

    monkeypatch.setattr(ws, "_SOCKET_GENERATION", 20, raising=False)
    ws._begin_feed_restart_verification(reason="ws_error:1006", start_epoch=1000.0, now_epoch=1000.0, socket_generation=20)
    ws._record_feed_restart_verify_connect(now_epoch=1000.5, socket_generation=20)
    ws._record_feed_restart_verify_subscribe(now_epoch=1000.6, socket_generation=20)

    monkeypatch.setattr(
        ws,
        "_restart_verification_proof",
        lambda now_epoch: (True, "ok", {"source": "unit_test"}),
    )

    ws._tick_feed_restart_verification(now_epoch=1001.0)

    assert ws._reconnect_recovery_blocked_active() is True
    assert ws._RECONNECT_BLOCKED_REASON == "ws1006_process_restart_required"
    denied = [payload for event, payload in events if event == "FEED_RECONNECT_RECOVERY_CLEAR_DENIED"]
    assert denied and denied[-1]["clearance"] == "BLOCKED_CAUSAL_PROOF_REQUIRED"
    assert denied[-1]["causal_recovery_proof_present"] is False
    assert denied[-1]["read_only"] is True
    assert denied[-1]["is_order_action"] is False
    assert denied[-1]["broker_api_called"] is False
    assert denied[-1]["allowed_for_live_execution"] is False
    ws._persist_runtime_snapshot_row(
        ws_connected=True,
        source="unit_test_recovered_ticks",
        now_epoch=1001.0,
        runtime_state="RUNNING",
        last_error="",
    )
    payload = json.loads((logs_path / "feed_runtime_latest.json").read_text(encoding="utf-8"))
    assert payload["reconnect_blocked_reason"] == "ws1006_process_restart_required"
    assert payload["process_restart_required"] is True
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

    monkeypatch.setattr(ws, "_SOCKET_GENERATION", 20, raising=False)
    ws._begin_feed_restart_verification(reason="ws_error:1006", start_epoch=1000.0, now_epoch=1000.0, socket_generation=20)
    ws._record_feed_restart_verify_connect(now_epoch=1000.5, socket_generation=20)
    ws._record_feed_restart_verify_subscribe(now_epoch=1000.6, socket_generation=20)

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


def _prepare_restart_verification_race(monkeypatch):
    monkeypatch.setattr(cfg, "FEED_RESTART_VERIFY_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "FEED_RESTART_VERIFY_REQUIRE_MARKET_OPEN", False, raising=False)
    monkeypatch.setattr(cfg, "FEED_RESTART_VERIFY_TIMEOUT_SEC", 1.0, raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    ws._reset_feed_restart_verification(reason="race_test_setup")
    monkeypatch.setattr(ws, "_SOCKET_GENERATION", 10, raising=False)
    ws._begin_feed_restart_verification(
        reason="old_generation", start_epoch=1000.0, now_epoch=1000.0, socket_generation=10
    )
    ws._record_feed_restart_verify_connect(now_epoch=1000.1, socket_generation=10)
    ws._record_feed_restart_verify_subscribe(now_epoch=1000.2, socket_generation=10)


def test_old_socket_callback_cannot_record_connect_for_new_restart_verification(monkeypatch):
    _prepare_restart_verification_race(monkeypatch)
    monkeypatch.setattr(ws, "_SOCKET_GENERATION", 11, raising=False)
    ws._begin_feed_restart_verification(
        reason="new_socket_generation", start_epoch=2000.0, now_epoch=2000.0, socket_generation=11
    )

    # Models a callback that passed its socket-current check, was paused, then
    # resumed only after a newer socket/verifier generation became active.
    ws._record_feed_restart_verify_connect(now_epoch=2000.1, socket_generation=10)

    assert ws._FEED_RESTART_VERIFY_STATE == "PENDING"
    assert ws._FEED_RESTART_VERIFY_REASON == "new_socket_generation"
    assert ws._FEED_RESTART_VERIFY_CONNECT_EPOCH is None


def test_delayed_old_tick_callback_cannot_satisfy_new_restart_verification(monkeypatch):
    _prepare_restart_verification_race(monkeypatch)
    monkeypatch.setattr(cfg, "FEED_RESTART_VERIFY_ENABLE", True, raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {101: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", set(), raising=False)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [101], raising=False)
    monkeypatch.setattr(ws, "_LAST_OPTION_COUNTS_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(ws, "_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(ws, "_ws_connected_state", lambda: True)
    monkeypatch.setattr(ws, "_option_runtime_state", lambda **_kwargs: {
        "subscribed_count_by_symbol": {"NIFTY": 1},
        "feed_block_reason_by_symbol": {},
        "option_count": 1,
    })
    monkeypatch.setattr(cfg, "FEED_RESTART_VERIFY_MIN_TICKS_PER_SYMBOL", 1, raising=False)
    monkeypatch.setattr(cfg, "MAX_DEPTH_AGE_SEC", 5.0, raising=False)

    # Model a callback that passed its wrapper check before cutover and then
    # reached the delegate with its captured old generation.
    monkeypatch.setattr(ws, "_SOCKET_GENERATION", 11, raising=False)
    ws._begin_feed_restart_verification(
        reason="new_socket_generation", start_epoch=2000.0, now_epoch=2000.0, socket_generation=11
    )
    ws._record_feed_restart_verify_connect(now_epoch=2000.1, socket_generation=11)
    ws._record_feed_restart_verify_subscribe(now_epoch=2000.2, socket_generation=11)

    previous_last_ws_tick_epoch = ws._LAST_WS_TICK_EPOCH
    previous_token_receipt = dict(ws._LAST_MSG_TS_BY_TOKEN)
    ws.on_ticks(None, [{"instrument_token": 101, "last_price": 100.0}], socket_generation=10)
    assert ws._FEED_RESTART_VERIFY_STATE in {"PENDING", "FAILED"}
    assert ws._FEED_RESTART_VERIFY_TICK_EPOCH_BY_TOKEN == {}
    assert ws._LAST_WS_TICK_EPOCH == previous_last_ws_tick_epoch
    assert ws._LAST_MSG_TS_BY_TOKEN == previous_token_receipt

    ws._tick_feed_restart_verification(now_epoch=2000.3)
    assert ws._FEED_RESTART_VERIFY_STATE in {"PENDING", "FAILED"}
    assert ws._FEED_RESTART_VERIFY_STATE != "OK"
    assert ws._FEED_RESTART_VERIFY_VERIFIED_EPOCH is None


def test_socket_cutover_and_tick_callback_do_not_invert_locks(monkeypatch):
    import threading

    monkeypatch.setattr(ws, "_SOCKET_GENERATION_LOCK", threading.RLock())
    monkeypatch.setattr(ws, "_KITE_TICKER_LOCK", threading.Lock())
    assert not ws._KITE_TICKER_LOCK.locked()
    monkeypatch.setattr(ws, "_SOCKET_GENERATION", 40, raising=False)
    monkeypatch.setattr(ws, "_KITE_TICKER", type("Ticker", (), {"is_connected": lambda self: True})(), raising=False)
    start_has_ticker_lock = threading.Event()
    start_thread_entered = threading.Event()
    release_ticker_lock = threading.Event()
    callback_entered_process = threading.Event()
    callback_results = []
    start_results = []
    thread_errors = []

    def fake_process(_ws, _ticks, *, socket_generation, callback_sequence=None, callback_receive_epoch=None):
        callback_entered_process.set()
        callback_results.append(ws._ws_connected_state())

    monkeypatch.setattr(ws, "_process_on_ticks", fake_process)

    def start_path():
        try:
            start_thread_entered.set()
            with ws._KITE_TICKER_LOCK:
                start_has_ticker_lock.set()
                assert release_ticker_lock.wait(timeout=3.0)
            start_results.append(ws._advance_socket_generation())
        except BaseException as exc:
            thread_errors.append(exc)

    start_thread = _REAL_THREAD(target=start_path, daemon=True)
    start_thread.start()
    assert start_thread_entered.wait(timeout=2.0)
    assert start_has_ticker_lock.wait(timeout=2.0), repr(thread_errors)

    callback_thread = _REAL_THREAD(
        target=lambda: ws.on_ticks(None, [{"instrument_token": 101, "last_price": 100.0}], socket_generation=40),
        daemon=True,
    )
    callback_thread.start()
    assert callback_entered_process.wait(timeout=2.0)

    # Callback holds generation lock and queries ticker health while startup
    # owns the ticker lock. Startup must release ticker before advancing socket.
    release_ticker_lock.set()
    callback_thread.join(timeout=2.0)
    start_thread.join(timeout=2.0)

    assert not callback_thread.is_alive()
    assert not start_thread.is_alive()
    assert callback_results == [True]
    assert start_results == [41]
    assert ws._current_socket_generation() == 41


def test_subscription_mutation_and_tick_callback_do_not_invert_locks(monkeypatch):
    import threading

    monkeypatch.setattr(ws, "_SOCKET_GENERATION_LOCK", threading.RLock())
    monkeypatch.setattr(ws, "_KITE_TICKER_LOCK", threading.Lock())
    monkeypatch.setattr(ws, "_SOCKET_START_LOCK", threading.RLock())
    monkeypatch.setattr(ws, "_SOCKET_GENERATION", 50, raising=False)
    callback_holds_generation = threading.Event()
    allow_callback_health_check = threading.Event()
    subscription_generation_snapshot_started = threading.Event()
    thread_errors = []

    class FakeTicker:
        MODE_FULL = "full"

        def is_connected(self):
            return True

        def subscribe(self, _tokens):
            return None

        def set_mode(self, _mode, _tokens):
            return None

    monkeypatch.setattr(ws, "_KITE_TICKER", FakeTicker(), raising=False)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [], raising=False)
    monkeypatch.setattr(ws, "_can_mutate_ws_subscriptions", lambda **_kwargs: (True, "", {}))
    monkeypatch.setattr(ws, "_client_mode_for_token", lambda *_args: "full")
    monkeypatch.setattr(ws, "_record_ws_subscription_operation", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ws, "_record_subscription_request_succeeded", lambda _tokens: None)
    monkeypatch.setattr(ws, "_record_mode_request_succeeded", lambda _tokens: None)
    monkeypatch.setattr(ws, "_log_ws", lambda *_args, **_kwargs: None)
    original_generation_snapshot = ws._current_socket_generation

    def observed_generation_snapshot():
        subscription_generation_snapshot_started.set()
        return original_generation_snapshot()

    monkeypatch.setattr(ws, "_current_socket_generation", observed_generation_snapshot)

    def fake_process(_ws, _ticks, *, socket_generation, callback_sequence=None, callback_receive_epoch=None):
        callback_holds_generation.set()
        if not allow_callback_health_check.wait(timeout=3.0):
            raise AssertionError("callback health check was not released")
        assert ws._ws_connected_state() is True

    monkeypatch.setattr(ws, "_process_on_ticks", fake_process)

    def invoke_callback():
        try:
            ws.on_ticks(None, [{"instrument_token": 101, "last_price": 100.0}], socket_generation=50)
        except BaseException as exc:
            thread_errors.append(exc)

    def invoke_subscription():
        try:
            assert ws.ensure_subscribed_tokens([101], reason="lock_order_test") is True
        except BaseException as exc:
            thread_errors.append(exc)

    callback_thread = _REAL_THREAD(target=invoke_callback, daemon=True)
    callback_thread.start()
    assert callback_holds_generation.wait(timeout=2.0)
    subscription_thread = _REAL_THREAD(target=invoke_subscription, daemon=True)
    subscription_thread.start()
    assert subscription_generation_snapshot_started.wait(timeout=2.0)

    # The subscription path is waiting for the generation snapshot while the
    # callback owns that lock. It must not already own the ticker lock.
    allow_callback_health_check.set()
    callback_thread.join(timeout=2.0)
    subscription_thread.join(timeout=2.0)

    assert not callback_thread.is_alive()
    assert not subscription_thread.is_alive()
    assert thread_errors == []
    assert ws._LAST_TOKENS == [101]


def test_retired_socket_cannot_record_after_direct_socket_replacement(monkeypatch):
    _prepare_restart_verification_race(monkeypatch)
    monkeypatch.setattr(ws, "_FEED_RESTART_VERIFY_CONNECT_EPOCH", None, raising=False)

    # The verifier still names generation 10, but a direct socket replacement
    # has retired it without beginning a new restart-verification generation.
    with ws._SOCKET_GENERATION_LOCK:
        ws._SOCKET_GENERATION = 11
    ws._record_feed_restart_verify_connect(now_epoch=1000.3, socket_generation=10)

    assert ws._FEED_RESTART_VERIFY_STATE == "PENDING"
    assert ws._FEED_RESTART_VERIFY_CONNECT_EPOCH is None


def test_old_socket_stage_and_proof_cannot_verify_after_direct_replacement(monkeypatch):
    _prepare_restart_verification_race(monkeypatch)
    proof_entered = threading.Event()
    release_proof = threading.Event()

    def _blocked_success_proof(now_epoch):
        proof_entered.set()
        assert release_proof.wait(timeout=3.0)
        return True, "old_socket_proved", {"socket_generation": 10}

    monkeypatch.setattr(ws, "_restart_verification_proof", _blocked_success_proof)
    worker = _REAL_THREAD(target=ws._tick_feed_restart_verification, kwargs={"now_epoch": 1000.5})
    worker.start()
    try:
        assert proof_entered.wait(timeout=2.0)
        with ws._SOCKET_GENERATION_LOCK:
            monkeypatch.setattr(ws, "_SOCKET_GENERATION", 11, raising=False)
            ws._invalidate_feed_restart_verification_for_socket_advance(socket_generation=11)
    finally:
        release_proof.set()
        worker.join(timeout=3.0)

    assert not worker.is_alive()
    assert ws._FEED_RESTART_VERIFY_STATE == "FAILED"
    assert ws._FEED_RESTART_VERIFY_SOCKET_GENERATION == 11
    assert ws._FEED_RESTART_VERIFY_VERIFIED_EPOCH is None
    assert ws._FEED_RESTART_VERIFY_CONNECT_EPOCH is None
    assert ws._FEED_RESTART_VERIFY_SUBSCRIBE_EPOCH is None


def test_stale_success_proof_cannot_mark_newer_restart_generation_ok(monkeypatch):
    _prepare_restart_verification_race(monkeypatch)
    proof_entered = threading.Event()
    release_proof = threading.Event()

    def _blocked_success_proof(now_epoch):
        proof_entered.set()
        assert release_proof.wait(timeout=3.0)
        return True, "old_generation_proved", {"generation": "old"}

    monkeypatch.setattr(ws, "_restart_verification_proof", _blocked_success_proof)
    worker = _REAL_THREAD(target=ws._tick_feed_restart_verification, kwargs={"now_epoch": 1000.5})
    worker.start()
    try:
        assert proof_entered.wait(timeout=2.0)
        monkeypatch.setattr(ws, "_SOCKET_GENERATION", 11, raising=False)
        ws._begin_feed_restart_verification(
            reason="new_generation", start_epoch=2000.0, now_epoch=2000.0, socket_generation=11
        )
    finally:
        release_proof.set()
        worker.join(timeout=3.0)

    assert not worker.is_alive()
    assert ws._FEED_RESTART_VERIFY_STATE == "PENDING"
    assert ws._FEED_RESTART_VERIFY_REASON == "new_generation"


def test_stale_timeout_cannot_mark_newer_restart_generation_failed(monkeypatch):
    _prepare_restart_verification_race(monkeypatch)
    proof_entered = threading.Event()
    release_proof = threading.Event()

    def _blocked_failure_proof(now_epoch):
        proof_entered.set()
        assert release_proof.wait(timeout=3.0)
        return False, "old_generation_timeout", {"generation": "old"}

    monkeypatch.setattr(ws, "_restart_verification_proof", _blocked_failure_proof)
    worker = _REAL_THREAD(target=ws._tick_feed_restart_verification, kwargs={"now_epoch": 1002.0})
    worker.start()
    try:
        assert proof_entered.wait(timeout=2.0)
        monkeypatch.setattr(ws, "_SOCKET_GENERATION", 11, raising=False)
        ws._begin_feed_restart_verification(
            reason="new_generation", start_epoch=2000.0, now_epoch=2000.0, socket_generation=11
        )
    finally:
        release_proof.set()
        worker.join(timeout=3.0)

    assert not worker.is_alive()
    assert ws._FEED_RESTART_VERIFY_STATE == "PENDING"
    assert ws._FEED_RESTART_VERIFY_REASON == "new_generation"
    assert ws._FEED_RESTART_VERIFY_FAILURE_DETAIL == ""


def test_stale_restart_stage_marker_cannot_overwrite_new_generation(monkeypatch):
    _prepare_restart_verification_race(monkeypatch)
    stage_entered = threading.Event()
    release_stage = threading.Event()
    original_stage_event = ws._restart_verify_stage_event

    def _blocked_stage_event(stage):
        stage_entered.set()
        assert release_stage.wait(timeout=3.0)
        return original_stage_event(stage)

    monkeypatch.setattr(ws, "_restart_verify_stage_event", _blocked_stage_event)
    monkeypatch.setattr(
        ws,
        "_restart_verification_proof",
        lambda now_epoch: (False, "not_yet_verified", {"generation": "old"}),
    )
    worker = _REAL_THREAD(target=ws._tick_feed_restart_verification, kwargs={"now_epoch": 1000.5})
    worker.start()
    try:
        assert stage_entered.wait(timeout=2.0)
        monkeypatch.setattr(ws, "_SOCKET_GENERATION", 11, raising=False)
        ws._begin_feed_restart_verification(
            reason="new_generation", start_epoch=2000.0, now_epoch=2000.0, socket_generation=11
        )
    finally:
        release_stage.set()
        worker.join(timeout=3.0)

    assert not worker.is_alive()
    assert ws._FEED_RESTART_VERIFY_STATE == "PENDING"
    assert ws._FEED_RESTART_VERIFY_LAST_STAGE_EVENT == ""


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
    monkeypatch.setattr(ws, "_ACTIVE_AUTH_MODE", "read_only_observer", raising=False)
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

    calls = {"stop": 0, "start": 0, "soft": 0, "start_auth_mode": None}
    monkeypatch.setattr(
        ws,
        "stop_depth_ws",
        lambda reason="manual_stop": calls.__setitem__("stop", calls["stop"] + 1),
    )
    monkeypatch.setattr(
        ws,
        "start_depth_ws",
        lambda tokens, profile_verified=False, **kwargs: (
            calls.__setitem__("start", calls["start"] + 1)
            or calls.__setitem__("start_auth_mode", kwargs.get("auth_mode"))
            or True
        ),
    )
    monkeypatch.setattr(
        ws,
        "_soft_resubscribe_current",
        lambda reason: calls.__setitem__("soft", calls["soft"] + 1) or True,
    )
    monkeypatch.setattr(ws.time, "time", lambda: 1001.0)

    _ensure_test_restart_candidate()
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
    assert calls["start_auth_mode"] == "read_only_observer"
    assert calls["soft"] == 0
    requested = [payload for event, payload in events if event == "FEED_RESTART_FULL_PATH_REQUESTED"]
    assert len(requested) == 1
    assert requested[0]["restart_attempted"] is False
    assert "FEED_FULL_RESTART_BEGIN" in [event for event, _payload in events]


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

    _ensure_test_restart_candidate()
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
    requested = [payload for event, payload in events if event == "FEED_RESTART_FULL_PATH_REQUESTED"]
    assert len(requested) == 1
    assert requested[0]["restart_attempted"] is False
    assert "FEED_FULL_RESTART_BEGIN" in [event for event, _payload in events]


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

    _ensure_test_restart_candidate()
    assert (
        ws.restart_depth_ws(
            reason="market_open_option_subscriptions_missing",
            ignore_cooldown=True,
            force_full_restart=True,
        )
        is True
    )
    assert calls == {"stop": 1, "start": 1}
    requested = [payload for event, payload in events if event == "FEED_RESTART_FULL_PATH_REQUESTED"]
    assert len(requested) == 1
    assert requested[0]["restart_attempted"] is False
    assert "FEED_FULL_RESTART_BEGIN" in [event for event, _payload in events]


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

    _ensure_test_restart_candidate()
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


def test_breaker_blocked_restart_logging_uses_storm_cooldown(monkeypatch):
    monkeypatch.setattr(ws, "_LAST_BREAKER_BLOCK_LOG_EPOCH", 0.0, raising=False)
    monkeypatch.setattr(ws, "feed_breaker_tripped", lambda: True)
    monkeypatch.setattr(ws, "_AUTH_REQUIRED_LATCH", False, raising=False)
    monkeypatch.setattr(ws, "_STOP_REQUESTED", False, raising=False)
    monkeypatch.setattr(ws, "_RECONNECT_BLOCKED_REASON", "", raising=False)
    monkeypatch.setattr(ws, "_REACTOR_NOT_RESTARTABLE_DETECTED", False, raising=False)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [123], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", [123], raising=False)
    monkeypatch.setattr(ws, "_KITE_TICKER", None, raising=False)
    forensic_events = []
    monkeypatch.setattr(
        ws,
        "append_feed_forensic_event",
        lambda event, **payload: forensic_events.append((event, payload)),
    )
    monkeypatch.setattr(
        ws,
        "_resubscribe_token_selection",
        lambda: (_ for _ in ()).throw(AssertionError("breaker_open_must_skip_token_resolution")),
    )
    monkeypatch.setattr(cfg, "FEED_RESTART_STORM_COOLDOWN_SEC", 30.0, raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    times = iter((100.0, 101.0, 131.0))
    monkeypatch.setattr(ws, "now_utc_epoch", lambda: next(times))
    events = []

    _ensure_test_restart_candidate()
    assert ws.restart_depth_ws(reason="tick_stalled", force_full_restart=True) is False
    _ensure_test_restart_candidate()
    assert ws.restart_depth_ws(reason="tick_stalled", force_full_restart=True) is False
    _ensure_test_restart_candidate()
    assert ws.restart_depth_ws(reason="depth_stale", force_full_restart=True) is False

    blocked = [payload for event, payload in events if event == "FEED_RESTART_BLOCKED_BY_BREAKER"]
    assert len(blocked) == 2
    assert blocked[0]["diagnostic_cooldown_sec"] == 30.0
    assert not any(event == "feed_restart_required" for event, _payload in events)
    assert forensic_events == []
    assert not any(event == "FEED_RESTART_BLOCKED_AUTH_REQUIRED" for event, _payload in events)


def test_breaker_trip_after_preflight_still_blocks_socket_restart(monkeypatch):
    breaker_states = iter((False, False, True))
    monkeypatch.setattr(ws, "feed_breaker_tripped", lambda: next(breaker_states))
    monkeypatch.setattr(ws, "_AUTH_REQUIRED_LATCH", False, raising=False)
    monkeypatch.setattr(ws, "_STOP_REQUESTED", False, raising=False)
    monkeypatch.setattr(ws, "_RECONNECT_BLOCKED_REASON", "", raising=False)
    monkeypatch.setattr(ws, "_REACTOR_NOT_RESTARTABLE_DETECTED", False, raising=False)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [123], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", [123], raising=False)
    monkeypatch.setattr(ws, "_KITE_TICKER", object(), raising=False)
    monkeypatch.setattr(ws, "_resubscribe_token_selection", lambda: ([123], {}))
    monkeypatch.setattr(ws, "_ws_connected_state", lambda: True)
    monkeypatch.setattr(ws, "_use_native_reconnect", lambda: False)
    monkeypatch.setattr(ws.feed_restart_guard, "allow_restart", lambda **kwargs: True)
    monkeypatch.setattr(ws, "_RESTART_LOCK", ws.threading.RLock())
    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))
    calls = {"stop": 0, "start": 0}
    monkeypatch.setattr(ws, "stop_depth_ws", lambda **kwargs: calls.__setitem__("stop", calls["stop"] + 1))
    monkeypatch.setattr(
        ws,
        "start_depth_ws",
        lambda *args, **kwargs: calls.__setitem__("start", calls["start"] + 1),
    )

    _ensure_test_restart_candidate()
    assert ws.restart_depth_ws(reason="tick_stalled", force_full_restart=True) is False
    assert calls == {"stop": 0, "start": 0}
    assert any(event == "FEED_RESTART_BLOCKED_BY_BREAKER" for event, _payload in events)
    requested = [payload for event, payload in events if event == "FEED_RESTART_FULL_PATH_REQUESTED"]
    assert len(requested) == 1
    assert requested[0]["restart_attempted"] is False
    assert not any(event == "FEED_FULL_RESTART_BEGIN" for event, _payload in events)


def test_breaker_diagnostic_cooldown_rejects_nonfinite_config(monkeypatch):
    monkeypatch.setattr(ws, "_LAST_BREAKER_BLOCK_LOG_EPOCH", 0.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_RESTART_STORM_COOLDOWN_SEC", float("inf"), raising=False)
    monkeypatch.setattr(ws, "now_utc_epoch", lambda: 1000.0)
    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload, **kwargs: events.append((event, payload)))

    ws._log_breaker_blocked_restart("tick_stalled")

    blocked = [payload for event, payload in events if event == "FEED_RESTART_BLOCKED_BY_BREAKER"]
    assert len(blocked) == 1
    assert blocked[0]["diagnostic_cooldown_sec"] == 900.0


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

    _ensure_test_restart_candidate()
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
    _ensure_test_restart_candidate()
    assert ws.restart_depth_ws(reason="velocity_trip", ignore_cooldown=True, force_full_restart=True) is False
    assert "FEED_RESTART_STORM_TRIP" in [event for event, _payload in events]
    assert calls["breaker"] == 1


def test_storm_breaker_allows_restarts_over_long_window(monkeypatch):
    from core import kite_depth_ws as ws
    from config import config as cfg

    monkeypatch.setattr(ws, "_LAST_TOKENS", [123, 456], raising=False)
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", [123, 456], raising=False)
    _record_validated_candidate([123, 456], [123, 456])
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

    _ensure_test_restart_candidate()
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
