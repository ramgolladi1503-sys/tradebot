import importlib
import threading
import time
from datetime import date
import pytest

from config import config as cfg
from config import feed_runtime_reliability as reliability_cfg

UNIVERSE = "runtime/reference/market_event_graph/nifty50_live_universe_kite_9fb8832853c27944_828c0c378e493972_fba078a4cd7aeb52.json"


def _commit_test_option_ownership(ws, contracts):
    """Establish test ownership through the same fail-closed lifecycle API."""
    generation = ws._current_socket_generation()
    ws._OPTION_OWNERSHIP_BOOTSTRAP_GENERATION = generation
    ws._invalidate_applied_option_ownership(
        "test_reset", socket_generation=generation
    )
    expected = sorted(int(token) for token in contracts)
    desired_revision = ws.record_desired_option_contracts(
        contracts,
        expected_tokens=expected,
        source="test_instrument_master",
    )
    base, invalidated = ws._begin_applied_option_mutation(
        "test_initial_subscription", affected_tokens=expected
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


@pytest.fixture(autouse=True)
def _reset_test_option_ownership():
    """Keep generation-bound ownership evidence isolated between tests."""
    ws = importlib.import_module("core.kite_depth_ws")
    generation = ws._current_socket_generation()
    ws.record_desired_option_contracts(
        {}, expected_tokens=[], source="test_isolation"
    )
    ws._invalidate_applied_option_ownership(
        "test_isolation", socket_generation=generation
    )
    ws._OPTION_OWNERSHIP_BOOTSTRAP_GENERATION = 0
    yield
    generation = ws._current_socket_generation()
    ws.record_desired_option_contracts(
        {}, expected_tokens=[], source="test_isolation_teardown"
    )
    ws._invalidate_applied_option_ownership(
        "test_isolation_teardown", socket_generation=generation
    )
    ws._OPTION_OWNERSHIP_BOOTSTRAP_GENERATION = 0


def _stage_test_option_contracts(ws, contracts):
    return ws.record_desired_option_contracts(
        contracts,
        expected_tokens=sorted(int(token) for token in contracts),
        source="test_instrument_master",
    )


class DummyKiteSocket:
    MODE_FULL = "full"
    MODE_QUOTE = "quote"

    def __init__(self):
        self.ws = object()
        self.subscribed_tokens = {}
        self.subscribe_calls = []
        self.set_mode_calls = []

    def subscribe(self, tokens):
        normalized = [int(token) for token in tokens]
        self.subscribe_calls.append(normalized)
        for token in normalized:
            self.subscribed_tokens[int(token)] = self.MODE_QUOTE

    def set_mode(self, mode, tokens):
        normalized = [int(token) for token in tokens]
        self.set_mode_calls.append((mode, normalized))
        for token in normalized:
            self.subscribed_tokens[int(token)] = mode


class MockMutationSocket(DummyKiteSocket):
    """Keep real queue helpers synchronous even when pytest has a reactor."""


def test_on_ticks_routes_observation_tokens_into_shadow_buffer(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    shadow = importlib.import_module("core.market_event_graph_live_ohlc_buffer")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(
        cfg,
        "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH",
        UNIVERSE,
    )
    registry = registry_mod.load_observation_registry(force=True)
    shadow.reset_live_source_shadow_buffer()
    ws._reset_market_event_graph_generation_evidence()
    ws._FEED_SESSION_ID = "session-1"
    ws._FEED_RECONNECT_GENERATION = 1
    monkeypatch.setattr(ws, "_SYMBOL_LAST_LTP_TS", {}, raising=False)
    monkeypatch.setattr(ws, "_SYMBOL_LAST_OPTION_TICK_TS", {}, raising=False)
    ws._SUBSCRIPTION_REQUEST_SUCCEEDED_TOKENS.update({256265, 738561})
    ws._SUBSCRIPTION_REQUEST_SUCCEEDED_EPOCH_BY_TOKEN[256265] = 1.0
    ws._SUBSCRIPTION_REQUEST_SUCCEEDED_EPOCH_BY_TOKEN[738561] = 1.0
    ws._TOKEN_TO_SYMBOL[256265] = "NIFTY"
    ws._TOKEN_TO_SYMBOL[738561] = "RELIANCE"
    ws._set_observation_plan_state(
        enabled=True,
        verdict="PASS_LIVE_SOURCE_PRESESSION_READINESS",
        production_tokens=[256265],
        observation_tokens=list(registry.all_tokens),
        final_union_tokens=list(registry.all_tokens),
        configured_budget=150,
    )

    tick = {
        "instrument_token": 256265,
        "last_price": 25000.0,
        "exchange_timestamp": time.time(),
        "ohlc": {"open": 24990.0, "high": 25010.0, "low": 24980.0, "close": 24995.0},
        "change": 0.1,
    }
    ws.on_ticks(None, [tick])

    bars = shadow.shadow_ohlc_buffer.get_bars("NIFTY")
    assert bars
    assert bars[-1]["bar_provenance"]["instrument_token"] == 256265
    assert bars[-1]["bar_provenance"]["reconnect_generation"] == 1
    assert bars[-1]["bar_provenance"]["live_feed_session_id"] == "session-1"

    # Observation cash equities retain ordinary LTP freshness and shadow
    # routing, but are not production option contracts for option freshness.
    equity_tick_epoch = time.time()
    ws.on_ticks(None, [{
        "instrument_token": 738561,
        "last_price": 1420.0,
        "exchange_timestamp": equity_tick_epoch,
        "ohlc": {"open": 1410.0, "high": 1430.0, "low": 1400.0, "close": 1415.0},
        "change": 0.2,
    }])
    assert abs(ws._SYMBOL_LAST_LTP_TS["RELIANCE"] - equity_tick_epoch) < 0.01
    assert "RELIANCE" not in ws._SYMBOL_LAST_OPTION_TICK_TS
    equity_bars = shadow.shadow_ohlc_buffer.get_bars("RELIANCE")
    assert equity_bars
    assert equity_bars[-1]["bar_provenance"]["instrument_token"] == 738561


def test_observation_equity_is_not_option_freshness(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {738561: "RELIANCE"}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {738561}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {738561: "RELIANCE"}, raising=False)
    monkeypatch.setattr(ws, "_SYMBOL_LAST_OPTION_TICK_TS", {}, raising=False)

    # Isolate the underlying callback: same-symbol option ticks must not mask
    # an underlying token accidentally satisfying option freshness.
    ws.on_ticks(None, [{"instrument_token": 738561, "last_price": 1420.0, "exchange_timestamp": time.time()}])
    assert ws._SYMBOL_LAST_OPTION_TICK_TS == {}


def test_option_recovery_verification_ignores_underlying_ticks(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    monkeypatch.setattr(cfg, "FEED_OPTION_VERIFY_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "FEED_OPTION_VERIFY_MIN_OPTION_TICKS_PER_SYMBOL", 2, raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {101: "NIFTY", 201: "NIFTY", 202: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [101, 201, 202, 301], raising=False)
    monkeypatch.setattr(ws, "_LAST_MSG_TS_BY_TOKEN", {101: 1001.0, 301: 1001.0}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {101, 301}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {101: "NIFTY", 301: "RELIANCE"}, raising=False)
    _commit_test_option_ownership(ws, {
        201: {"symbol": "NIFTY", "instrument_type": "CE", "exchange": "NFO", "expiry": "2026-08-06", "strike": 25000},
        202: {"symbol": "NIFTY", "instrument_type": "PE", "exchange": "NFO", "expiry": "2026-08-06", "strike": 25000},
    })
    ws._reset_option_feed_verification(reason="test_reset")
    ws._begin_option_feed_verification(
        reason="reconnect",
        start_epoch=1000.0,
        requested_by_symbol={"NIFTY": 2},
        subscribed_by_symbol={"NIFTY": 2},
    )

    ws._tick_option_feed_verification(now_epoch=1002.0)
    assert ws._option_feed_verification_overlay_payload()["state"] == "PENDING"

    ws._TOKEN_TO_SYMBOL[301] = "RELIANCE"
    ws._LAST_MSG_TS_BY_TOKEN.update({201: 1002.5, 202: 1002.6})
    ws._tick_option_feed_verification(now_epoch=1003.0)
    assert ws._option_feed_verification_overlay_payload()["state"] == "OK"


def test_option_health_and_restart_counts_ignore_non_option_tokens(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {
        101: "NIFTY", 201: "NIFTY", 202: "NIFTY", 301: "RELIANCE", 401: "STICKY",
    }, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {101, 301, 401}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {101: "NIFTY", 301: "RELIANCE", 401: "STICKY"}, raising=False)
    monkeypatch.setattr(ws, "_LAST_MSG_TS_BY_TOKEN", {
        101: 99.0, 201: 99.5, 202: 98.5, 301: 99.9, 401: 100.0,
    }, raising=False)
    monkeypatch.setattr(ws, "_SYMBOL_LAST_OPTION_TICK_TS", {"NIFTY": 99.5}, raising=False)
    monkeypatch.setattr(ws, "get_latest_tick_rows_db", lambda tokens: {}, raising=False)
    _commit_test_option_ownership(ws, {
        201: {"symbol": "NIFTY", "instrument_type": "CE", "exchange": "NFO", "expiry": "2026-08-06", "strike": 25000},
        202: {"symbol": "NIFTY", "instrument_type": "PE", "exchange": "NFO", "expiry": "2026-08-06", "strike": 25000},
    })
    tokens = [101, 201, 202, 301, 401]

    total = ws._option_subscription_freshness_stats(now_epoch=100.0, tokens=tokens)
    by_symbol = ws._option_subscription_freshness_by_symbol_stats(now_epoch=100.0, tokens=tokens)
    subscribed_total, subscribed_age, _rows = ws._subscribed_option_token_stats(
        now_epoch=100.0, tokens=tokens
    )
    runtime = ws._option_runtime_state(
        now_epoch=100.0,
        tokens=tokens,
        expected_counts_by_symbol={"NIFTY": 2},
        min_required_by_symbol={"NIFTY": 1},
        ws_connected=True,
    )
    restart_counts = ws._restart_verify_ticks_by_symbol(
        tick_epochs_by_token={101: 99.5, 201: 99.6, 202: 99.7, 301: 99.8, 401: 99.9},
        after_epoch=99.0,
        now_epoch=100.0,
        max_age_sec=5.0,
    )

    assert total["option_count"] == 2
    assert set(by_symbol) == {"NIFTY"}
    assert subscribed_total == 2
    assert set(subscribed_age) == {"NIFTY"}
    assert runtime["option_count"] == 2
    assert runtime["subscribed_count_by_symbol"] == {"NIFTY": 2}
    assert "RELIANCE" not in runtime["option_age_by_symbol"]
    assert "RELIANCE" not in runtime["active_blockers_by_symbol"]
    assert restart_counts == {"NIFTY": 2}


def test_stale_option_refresh_decision_excludes_observation_sticky_and_unknown_tokens(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    monkeypatch.setattr(cfg, "SYMBOLS", ["NIFTY"], raising=False)
    monkeypatch.setattr(cfg, "FEED_STALE_OPTION_SUBSCRIPTION_REFRESH_SEC", 20.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_STALE_OPTION_SUBSCRIPTION_DRIFT_REFRESH_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_STALE_OPTION_SUBSCRIPTION_MIN_FRESH_RATIO", 0.8, raising=False)
    monkeypatch.setattr(cfg, "FEED_STALE_OPTION_SUBSCRIPTION_MUTATION_MIN_STALE_COUNT", 1, raising=False)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(ws, "build_subscription_tokens", lambda _symbols: (
        [101, 201, 202], [{"symbol": "NIFTY", "tokens": [101, 201, 202], "stale_option_pruned_count": 0}]
    ))
    monkeypatch.setattr(ws, "get_latest_tick_rows_db", lambda _tokens: {}, raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {101: "NIFTY", 201: "NIFTY", 202: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {101}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {101: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [101, 201], raising=False)
    monkeypatch.setattr(ws, "_LAST_MSG_TS_BY_TOKEN", {201: 70.0, 301: 1.0, 401: 1.0}, raising=False)
    monkeypatch.setattr(ws, "_SYMBOL_LAST_OPTION_TICK_TS", {"RELIANCE": 1.0}, raising=False)
    monkeypatch.setattr(ws, "_STALE_OPTION_MUTATION_WINDOW_STATE", {}, raising=False)
    _commit_test_option_ownership(ws, {
        201: {"symbol": "NIFTY", "instrument_type": "CE", "exchange": "NFO", "expiry": "2026-08-06", "strike": 25000},
        202: {"symbol": "NIFTY", "instrument_type": "PE", "exchange": "NFO", "expiry": "2026-08-06", "strike": 25000},
    })

    mutation_candidates = []
    monkeypatch.setattr(
        ws,
        "_should_mutate_stale_option_symbol_subscription",
        lambda **kwargs: mutation_candidates.append(kwargs["symbol"])
        or (True, {"diagnostic_urgent": True, "mutation_skip_reason": "", "mutation_window_count_by_symbol": 1}, {}),
    )
    monkeypatch.setattr(ws, "_can_mutate_ws_subscriptions", lambda **_kwargs: (True, "ok", {}))

    _applied, decision = ws._maybe_refresh_stale_option_subscription_universe(
        now_epoch=100.0,
        refresh_state={"last_refresh_epoch": 0.0, "last_freshness_refresh_epoch": 0.0},
    )

    assert decision["freshness_urgent"] is True
    assert decision["freshness_urgent_symbols"] == ["NIFTY"]
    assert decision["freshness_by_symbol"].keys() == {"NIFTY"}
    assert mutation_candidates == ["NIFTY"]
    assert "RELIANCE" not in decision["mutation_eligible_symbols"]
    assert decision["option_count"] == 1


def test_unknown_applied_option_ownership_cannot_claim_stale_options(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    generation = ws._current_socket_generation()
    ws._invalidate_applied_option_ownership(
        "test_unknown", socket_generation=generation
    )
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {201: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", set(), raising=False)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [201], raising=False)
    monkeypatch.setattr(ws, "_LAST_MSG_TS_BY_TOKEN", {201: 99.0}, raising=False)
    monkeypatch.setattr(ws, "get_latest_tick_rows_db", lambda _tokens: {}, raising=False)

    stats = ws._option_subscription_freshness_stats(now_epoch=100.0, tokens=[201])
    by_symbol = ws._option_subscription_freshness_by_symbol_stats(
        now_epoch=100.0, tokens=[201]
    )

    assert stats["option_count"] == 0
    assert by_symbol == {}


def test_ensure_subscribed_tokens_commits_staged_option_after_local_success(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    _commit_test_option_ownership(ws, {
        201: {"symbol": "NIFTY", "instrument_type": "CE", "exchange": "NFO", "expiry": "2026-08-06", "strike": 25000},
    })
    desired = {
        201: {"symbol": "NIFTY", "instrument_type": "CE", "exchange": "NFO", "expiry": "2026-08-06", "strike": 25000},
        202: {"symbol": "NIFTY", "instrument_type": "PE", "exchange": "NFO", "expiry": "2026-08-06", "strike": 25000},
    }
    _stage_test_option_contracts(ws, desired)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [201], raising=False)
    socket = DummyKiteSocket()
    monkeypatch.setattr(ws, "_KITE_TICKER", socket, raising=False)
    monkeypatch.setattr(ws, "_can_mutate_ws_subscriptions", lambda **_kwargs: (True, "ok", {}))

    assert ws.ensure_subscribed_tokens([202], reason="test_staged_option", symbol="NIFTY")

    ownership = ws.get_applied_option_ownership_snapshot()
    assert ownership.state == "KNOWN"
    assert set(ownership.contracts) == {201, 202}
    assert socket.subscribe_calls == [[202]]
    assert socket.set_mode_calls == [(socket.MODE_FULL, [202])]


def test_ensure_subscribed_tokens_failed_option_call_leaves_unknown(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    _commit_test_option_ownership(ws, {
        201: {"symbol": "NIFTY", "instrument_type": "CE", "exchange": "NFO", "expiry": "2026-08-06", "strike": 25000},
    })
    desired = {
        201: {"symbol": "NIFTY", "instrument_type": "CE", "exchange": "NFO", "expiry": "2026-08-06", "strike": 25000},
        202: {"symbol": "NIFTY", "instrument_type": "PE", "exchange": "NFO", "expiry": "2026-08-06", "strike": 25000},
    }
    _stage_test_option_contracts(ws, desired)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [201], raising=False)

    class FailingSocket(DummyKiteSocket):
        def subscribe(self, _tokens):
            raise RuntimeError("injected local subscribe failure")

    monkeypatch.setattr(ws, "_KITE_TICKER", FailingSocket(), raising=False)
    monkeypatch.setattr(ws, "_can_mutate_ws_subscriptions", lambda **_kwargs: (True, "ok", {}))

    assert ws.ensure_subscribed_tokens([202], reason="test_failed_option", symbol="NIFTY") is False
    assert ws.get_applied_option_ownership_snapshot().state == "UNKNOWN"


def test_ensure_subscribed_tokens_unclassified_option_invalidates_snapshot(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    _commit_test_option_ownership(ws, {
        201: {"symbol": "NIFTY", "instrument_type": "CE", "exchange": "NFO", "expiry": "2026-08-06", "strike": 25000},
    })
    monkeypatch.setattr(ws, "_LAST_TOKENS", [201], raising=False)
    monkeypatch.setitem(ws._TOKEN_TO_SYMBOL, 999999, "NIFTY")
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", set(), raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {}, raising=False)
    socket = DummyKiteSocket()
    monkeypatch.setattr(ws, "_KITE_TICKER", socket, raising=False)
    monkeypatch.setattr(ws, "_load_observation_registry_for_subscription", lambda: None)
    monkeypatch.setattr(ws, "_can_mutate_ws_subscriptions", lambda **_kwargs: (True, "ok", {}))

    assert ws.ensure_subscribed_tokens([999999], reason="trade_created", symbol="NIFTY")
    assert ws.get_applied_option_ownership_snapshot().state == "UNKNOWN"
    assert socket.subscribe_calls == [[999999]]


def test_ensure_subscribed_tokens_known_underlying_preserves_option_snapshot(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    _commit_test_option_ownership(ws, {
        201: {"symbol": "NIFTY", "instrument_type": "CE", "exchange": "NFO", "expiry": "2026-08-06", "strike": 25000},
    })
    before = ws.get_applied_option_ownership_snapshot()
    monkeypatch.setattr(ws, "_LAST_TOKENS", [201], raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {256265}, raising=False)
    socket = DummyKiteSocket()
    monkeypatch.setattr(ws, "_KITE_TICKER", socket, raising=False)
    monkeypatch.setattr(ws, "_can_mutate_ws_subscriptions", lambda **_kwargs: (True, "ok", {}))

    assert ws.ensure_subscribed_tokens([256265], reason="test_underlying")

    assert ws.get_applied_option_ownership_snapshot() == before
    assert socket.subscribe_calls == [[256265]]


def test_index_only_subscription_does_not_change_applied_option_ownership(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    contracts = {
        201: {"symbol": "NIFTY", "instrument_type": "CE", "exchange": "NFO", "expiry": "2026-08-06", "strike": 25000},
        202: {"symbol": "NIFTY", "instrument_type": "PE", "exchange": "NFO", "expiry": "2026-08-06", "strike": 25000},
    }
    _commit_test_option_ownership(ws, contracts)
    before = ws.get_applied_option_ownership_snapshot()
    monkeypatch.setattr(ws, "_LAST_TOKENS", [201, 202], raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {256265}, raising=False)
    socket = DummyKiteSocket()
    monkeypatch.setattr(ws, "_KITE_TICKER", socket, raising=False)
    monkeypatch.setattr(ws, "_can_mutate_ws_subscriptions", lambda **_kwargs: (True, "ok", {}))

    assert ws.ensure_subscribed_tokens([256265], reason="index_only_update")

    assert ws.get_applied_option_ownership_snapshot() == before
    assert socket.subscribe_calls == [[256265]]


def test_overlapping_staged_option_subscriptions_serialize_to_known_snapshot(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    _commit_test_option_ownership(ws, {
        201: {"symbol": "NIFTY", "instrument_type": "CE", "exchange": "NFO", "expiry": "2026-08-06", "strike": 25000},
    })
    desired = {
        201: {"symbol": "NIFTY", "instrument_type": "CE", "exchange": "NFO", "expiry": "2026-08-06", "strike": 25000},
        202: {"symbol": "NIFTY", "instrument_type": "PE", "exchange": "NFO", "expiry": "2026-08-06", "strike": 25000},
        203: {"symbol": "NIFTY", "instrument_type": "CE", "exchange": "NFO", "expiry": "2026-08-06", "strike": 25100},
    }
    _stage_test_option_contracts(ws, desired)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [201], raising=False)
    monkeypatch.setattr(ws, "_KITE_TICKER", DummyKiteSocket(), raising=False)
    monkeypatch.setattr(ws, "_can_mutate_ws_subscriptions", lambda **_kwargs: (True, "ok", {}))
    barrier = threading.Barrier(3)
    results = []

    def subscribe(token):
        barrier.wait()
        results.append(ws.ensure_subscribed_tokens([token], reason="concurrent_test", symbol="NIFTY"))

    threads = [threading.Thread(target=subscribe, args=(token,)) for token in (202, 203)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=5)

    ownership = ws.get_applied_option_ownership_snapshot()
    assert len(results) == 2 and all(results)
    assert all(not thread.is_alive() for thread in threads)
    assert ownership.state == "KNOWN"
    assert set(ownership.contracts) == {201, 202, 203}


def test_required_option_tick_verification_does_not_clear_recovery_without_gap_proof(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    from core.feed_recovery_coordinator import FeedRecoveryCoordinator

    class Clock:
        now = 1000.0

        def __call__(self):
            return self.now

    clock = Clock()
    coordinator = FeedRecoveryCoordinator(now_epoch_fn=clock)
    coordinator.request_recovery(source="on_error", code=1006, reason="peer dropped")
    monkeypatch.setattr(ws, "_FEED_RECOVERY_COORDINATOR", coordinator)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [1234])
    monkeypatch.setattr(ws, "_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL", {})
    monkeypatch.setitem(ws._TOKEN_TO_SYMBOL, 1234, "NIFTY")
    monkeypatch.setitem(ws._LAST_MSG_TS_BY_TOKEN, 1234, 1001.0)
    _commit_test_option_ownership(ws, {
        1234: {"symbol": "NIFTY", "instrument_type": "CE", "exchange": "NFO", "expiry": "2026-08-06", "strike": 25000},
    })
    monkeypatch.setattr(cfg, "FEED_OPTION_VERIFY_MIN_OPTION_TICKS_PER_SYMBOL", 1, raising=False)
    ws._reset_option_feed_verification(reason="unit_test")
    ws._begin_option_feed_verification(
        reason="reconnect",
        start_epoch=1000.0,
        requested_by_symbol={"NIFTY": 1},
        subscribed_by_symbol={"NIFTY": 1},
    )
    clock.now = 1002.0

    ws._tick_option_feed_verification(now_epoch=1002.0)

    assert ws._option_feed_verification_overlay_payload()["state"] == "OK"
    assert coordinator.get_state_snapshot().recovery_in_progress is True
    assert coordinator.incident_history == ()


def test_unknown_ownership_cannot_verify_option_feed_recovery(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    generation = ws._current_socket_generation()
    ws._invalidate_applied_option_ownership(
        "test_unknown", socket_generation=generation
    )
    monkeypatch.setattr(ws, "_LAST_TOKENS", [1234], raising=False)
    monkeypatch.setattr(ws, "_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL", {}, raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {1234: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_LAST_MSG_TS_BY_TOKEN", {1234: 1001.0}, raising=False)
    monkeypatch.setattr(cfg, "FEED_OPTION_VERIFY_MIN_OPTION_TICKS_PER_SYMBOL", 1, raising=False)
    ws._reset_option_feed_verification(reason="unknown_ownership_test")
    ws._begin_option_feed_verification(
        reason="reconnect",
        start_epoch=1000.0,
        requested_by_symbol={"NIFTY": 1},
        subscribed_by_symbol={"NIFTY": 1},
    )

    ws._tick_option_feed_verification(now_epoch=1002.0)

    assert ws._option_feed_verification_overlay_payload()["state"] != "OK"


def test_invalid_ltp_does_not_refresh_option_freshness(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", False, raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {201: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", set(), raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {}, raising=False)
    monkeypatch.setattr(ws, "_SYMBOL_LAST_OPTION_TICK_TS", {}, raising=False)
    monkeypatch.setattr(ws, "_LAST_MSG_TS_BY_TOKEN", {}, raising=False)
    _commit_test_option_ownership(ws, {
        201: {"symbol": "NIFTY", "instrument_type": "CE", "exchange": "NFO", "expiry": "2026-08-06", "strike": 25000},
    })

    for invalid_ltp in (0, "nan", "not-a-price", float("nan")):
        ws.on_ticks(None, [{
            "instrument_token": 201,
            "last_price": invalid_ltp,
            "exchange_timestamp": time.time(),
        }])

    assert ws._SYMBOL_LAST_OPTION_TICK_TS == {}
    assert 201 not in ws._LAST_MSG_TS_BY_TOKEN


def test_pending_recovery_proof_progress_is_visible_and_fail_closed(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    from core.feed_recovery_coordinator import FeedRecoveryCoordinator

    coordinator = FeedRecoveryCoordinator(now_epoch_fn=lambda: 20.0)
    coordinator.request_recovery(source="on_error", code=1006, reason="peer dropped")
    monkeypatch.setattr(ws, "_FEED_RECOVERY_COORDINATOR", coordinator)
    monkeypatch.setattr(
        ws,
        "_WS_RECOVERY_PROOF_CONTEXT",
        {
            "disconnect_started_at": 10.0,
            "reconnected_at": 12.0,
            "expected_tokens": ["101", "202"],
            "actual_tokens": ["101"],
            "required_identity_tokens": ["101"],
            "required_identity_symbols": {"101": "NIFTY"},
            "last_pre_disconnect_timestamp_by_required_identity": {"101": 9.5},
            "first_post_disconnect_timestamp_by_required_identity": {},
            "health_window_start": None,
            "invalid_reasons": [],
        },
    )

    progress = ws._ws_recovery_proof_progress_payload(now_epoch=20.0)

    assert progress["state"] == "WAITING_FOR_REQUIRED_IDENTITY_TICKS"
    assert progress["missing_tokens"] == ["202"]
    assert progress["missing_post_disconnect_identities"] == ["101"]
    assert progress["recovery_verdict"] == "PENDING"
    assert progress["read_only"] is True
    assert progress["is_order_action"] is False
    assert progress["broker_api_called"] is False
    assert progress["allowed_for_live_execution"] is False


def test_runtime_domain_producer_partitions_index_and_stock_spot_evidence():
    ws = importlib.import_module("core.kite_depth_ws")

    domains = ws._build_feed_domain_health_payload(
        now_epoch=100.0,
        option_ages_by_symbol={"NIFTY": 0.5, "TCS": 900.0},
        option_blockers_by_symbol={"NIFTY": "OK", "TCS": "STALE_OPTION_LTP"},
        option_counts_by_symbol={"NIFTY": 4, "TCS": 12},
        underlying_tokens={256265, 738561},
        underlying_symbol_by_token={256265: "NIFTY", 738561: "TCS"},
        tick_epochs_by_token={256265: 99.5, 738561: 90.0},
        index_symbols={"NIFTY", "BANKNIFTY", "SENSEX"},
        max_index_age_sec=1.0,
        max_option_age_sec=2.5,
    )

    assert domains["index_spot"]["state"] == "HEALTHY"
    assert domains["stock_spot"]["state"] == "DEGRADED"
    assert domains["index_options"]["state"] == "HEALTHY"
    assert domains["stock_options"]["state"] == "DEGRADED"
    assert domains["index_futures"]["state"] == "UNKNOWN"


def test_runtime_domain_producer_marks_missing_or_invalid_underlying_unknown():
    import math

    ws = importlib.import_module("core.kite_depth_ws")
    domains = ws._build_feed_domain_health_payload(
        now_epoch=100.0,
        option_ages_by_symbol={"NIFTY": math.nan},
        option_blockers_by_symbol={"NIFTY": "OK"},
        option_counts_by_symbol={"NIFTY": 1},
        underlying_tokens={256265},
        underlying_symbol_by_token={256265: "NIFTY"},
        tick_epochs_by_token={},
        index_symbols={"NIFTY"},
        max_index_age_sec=1.0,
        max_option_age_sec=2.5,
    )

    assert domains["index_spot"]["state"] == "UNKNOWN"
    assert domains["index_options"]["state"] == "UNKNOWN"
    bool_age = ws._build_feed_domain_health_payload(
        now_epoch=100.0,
        option_ages_by_symbol={"NIFTY": True},
        option_blockers_by_symbol={"NIFTY": "OK"},
        option_counts_by_symbol={"NIFTY": 1},
        underlying_tokens={256265},
        underlying_symbol_by_token={256265: "NIFTY"},
        tick_epochs_by_token={256265: True},
        index_symbols={"NIFTY"},
        max_index_age_sec=1.0,
        max_option_age_sec=2.5,
    )
    assert bool_age["index_spot"]["state"] == "UNKNOWN"
    assert bool_age["index_options"]["state"] == "UNKNOWN"


def test_runtime_snapshot_callback_skips_same_state_direct_writes_but_keeps_transitions(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    store = importlib.import_module("core.feed.runtime_store")
    store.reset_runtime_persistence_for_tests()
    monkeypatch.setattr(store, "_ensure_runtime_worker", lambda: None)
    monkeypatch.setattr(reliability_cfg, "FEED_RUNTIME_SNAPSHOT_INTERVAL_SEC", 60.0, raising=False)
    direct_writes = []
    submit = ws._enqueue_runtime_snapshot_with_direct_artifact
    try:
        for state_text, source in (
            ("RUNNING", "on_ticks"),
            ("RUNNING", "on_ticks"),
            ("RECOVERY_BLOCKED", "on_ticks"),
            ("RECOVERY_BLOCKED", "websocket_disconnect"),
        ):
            payload = {
                "feed_session_id": "session-cadence-test",
                "boot_epoch": 1,
                "feed_epoch": 1,
                "source": source,
                "runtime_state": state_text,
            }
            assert submit(payload, direct_artifact_writer=lambda: direct_writes.append(payload["source"])) is True

        state = store.runtime_persistence_state()
        assert direct_writes == ["on_ticks", "on_ticks", "websocket_disconnect"]
        assert state["requested"] == 4
        assert state["enqueued"] == 3
        assert state["coalesced"] == 1
        assert state["rejected"] == 0
    finally:
        store.reset_runtime_persistence_for_tests()


def test_tick_snapshot_producer_gate_runs_before_expensive_collection(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    store = importlib.import_module("core.feed.runtime_store")
    store.reset_runtime_persistence_for_tests()
    monkeypatch.setattr(reliability_cfg, "FEED_RUNTIME_SNAPSHOT_INTERVAL_SEC", 60.0, raising=False)
    collection_calls = []
    publications = []
    monkeypatch.setattr(ws, "_subscribed_tokens_count_by_symbol", lambda _tokens: collection_calls.append("symbols") or {})
    monkeypatch.setattr(ws, "_missing_option_tokens_stats", lambda: (0, {}))
    monkeypatch.setattr(ws, "derive_market_session_policy", lambda **kwargs: type("Policy", (), {"market_state": "MARKET_OPEN"})())
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(ws, "_latest_db_tick_epoch", lambda: 100.0)
    monkeypatch.setattr(ws, "_latest_depth_epoch_from_store", lambda: 100.0)
    monkeypatch.setattr(ws, "_option_runtime_state", lambda **kwargs: {
        "option_count": 0,
        "option_age_by_symbol": {},
        "sample_rows": [],
        "subscribed_count_by_symbol": {},
        "ticks_received_count_by_symbol": {},
        "last_tick_ts_by_symbol": {},
        "feed_block_reason_by_symbol": {},
        "active_blockers_by_symbol": {},
    })
    monkeypatch.setattr(ws, "_restart_verify_overlay_payload", lambda: {})
    monkeypatch.setattr(ws, "_option_feed_verification_overlay_payload", lambda: {})
    monkeypatch.setattr(ws, "_runtime_transport_truth_fields", lambda **kwargs: {})
    monkeypatch.setattr(
        ws,
        "_enqueue_runtime_snapshot_with_direct_artifact",
        lambda payload, direct_artifact_writer, **kwargs: publications.append(payload) or True,
    )

    try:
        for source, state_text, timestamp in (
            ("on_ticks", "RUNNING", 100.0),
            ("on_ticks", "RUNNING", 100.1),
            ("on_ticks", "RECOVERY_BLOCKED", 100.2),
            ("websocket_disconnect", "RECOVERY_BLOCKED", 100.3),
        ):
            ws._persist_runtime_snapshot_row(
                ws_connected=source == "on_ticks",
                source=source,
                runtime_state=state_text,
                now_epoch=timestamp,
            )
        assert len(collection_calls) == 3
        assert [item["source"] for item in publications] == [
            "on_ticks",
            "on_ticks",
            "websocket_disconnect",
        ]
        assert all("recovery_proof_progress" in item for item in publications)
        state = store.runtime_persistence_state()
        assert state["producer_requested"] == 4
        assert state["producer_coalesced"] == 1
    finally:
        store.reset_runtime_persistence_for_tests()


def test_on_ticks_ignores_non_observation_tokens(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    shadow = importlib.import_module("core.market_event_graph_live_ohlc_buffer")
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    shadow.reset_live_source_shadow_buffer()
    ws._TOKEN_TO_SYMBOL[999999] = "IGNORED"

    ws.on_ticks(None, [{"instrument_token": 999999, "last_price": 1.0, "exchange_timestamp": time.time()}])

    assert shadow.shadow_ohlc_buffer.get_bars("IGNORED") == []


def test_raw_callback_routes_actual_constituents_without_production_symbol_maps(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    shadow = importlib.import_module("core.market_event_graph_live_ohlc_buffer")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    shadow.reset_live_source_shadow_buffer()
    ws._reset_market_event_graph_generation_evidence()
    ws._FEED_SESSION_ID = "session-constituents"
    ws._FEED_RECONNECT_GENERATION = 7
    tokens = {registry.index_token, registry.token_by_symbol["RELIANCE"], registry.token_by_symbol["HDFCBANK"]}
    for token in tokens:
        ws._TOKEN_TO_SYMBOL.pop(int(token), None)
        ws._UNDERLYING_TOKEN_TO_SYMBOL.pop(int(token), None)
    ws._SUBSCRIPTION_REQUEST_SUCCEEDED_TOKENS.update(tokens)
    ws._MODE_REQUEST_SUCCEEDED_TOKENS.update(tokens)
    for token in tokens:
        ws._SUBSCRIPTION_REQUEST_SUCCEEDED_EPOCH_BY_TOKEN[int(token)] = 1.0
        ws._MODE_REQUEST_SUCCEEDED_EPOCH_BY_TOKEN[int(token)] = 1.0
    ws._set_observation_plan_state(
        enabled=True,
        verdict="PASS_LIVE_SOURCE_PRESESSION_READINESS",
        production_tokens=[registry.index_token],
        observation_tokens=list(registry.all_tokens),
        final_union_tokens=list(registry.all_tokens),
        configured_budget=150,
    )

    ws.on_ticks(None, [
        {
            "instrument_token": registry.index_token,
            "last_price": 25000.0,
            "exchange_timestamp": time.time(),
            "ohlc": {"open": 24990.0, "high": 25010.0, "low": 24980.0, "close": 24995.0},
            "change": 0.1,
        },
        {
            "instrument_token": registry.token_by_symbol["RELIANCE"],
            "last_price": 1420.0,
            "exchange_timestamp": time.time(),
            "depth": {"buy": [{"price": 1419.5}], "sell": [{"price": 1420.5}]},
        },
        {
            "instrument_token": registry.token_by_symbol["HDFCBANK"],
            "last_price": 980.0,
            "exchange_timestamp": time.time(),
            "depth": {"buy": [{"price": 979.5}], "sell": [{"price": 980.5}]},
        },
        {"instrument_token": 999999, "last_price": 1.0, "exchange_timestamp": time.time()},
    ])

    assert shadow.shadow_ohlc_buffer.get_bars("NIFTY")[-1]["bar_provenance"]["instrument_token"] == 256265
    assert shadow.shadow_ohlc_buffer.get_bars("RELIANCE")[-1]["bar_provenance"]["instrument_token"] == 738561
    assert shadow.shadow_ohlc_buffer.get_bars("HDFCBANK")[-1]["bar_provenance"]["instrument_token"] == 341249
    assert shadow.shadow_ohlc_buffer.get_bars("IGNORED") == []


def test_budget_blocked_observation_overlap_does_not_write_shadow_bar(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    shadow = importlib.import_module("core.market_event_graph_live_ohlc_buffer")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    shadow.reset_live_source_shadow_buffer()
    ws._reset_market_event_graph_generation_evidence()
    ws._FEED_SESSION_ID = "session-blocked"
    ws._FEED_RECONNECT_GENERATION = 2
    ws._SUBSCRIPTION_REQUEST_SUCCEEDED_TOKENS.add(registry.index_token)
    ws._set_observation_plan_state(
        enabled=False,
        verdict="BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION_BUDGET",
        production_tokens=[registry.index_token],
        observation_tokens=list(registry.all_tokens),
        final_union_tokens=[registry.index_token],
        missing_observation_tokens=list(registry.all_tokens),
        configured_budget=1,
    )

    ws.on_ticks(None, [{
        "instrument_token": registry.index_token,
        "last_price": 25000.0,
        "exchange_timestamp": time.time(),
        "ohlc": {"open": 24990.0, "high": 25010.0, "low": 24980.0, "close": 24995.0},
        "change": 0.1,
    }])

    assert shadow.shadow_ohlc_buffer.get_bars("NIFTY") == []
    evidence = ws.market_event_graph_subscription_evidence_for_tokens({"NIFTY": registry.index_token})
    assert evidence["observation_blocker"]["verdict"] == "BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION_BUDGET"


def test_subscription_evidence_records_successful_int_token_subscription(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    ws._reset_market_event_graph_generation_evidence()
    ws._FEED_SESSION_ID = "session-evidence"
    ws._FEED_RECONNECT_GENERATION = 11

    tokens = [registry.index_token, registry.token_by_symbol["RELIANCE"], registry.token_by_symbol["HDFCBANK"]]
    ws._record_subscription_requested(tokens)
    ws._record_subscription_request_succeeded(tokens)
    ws._record_mode_request_succeeded(tokens)

    evidence = ws.market_event_graph_subscription_evidence_for_tokens(
        {
            "NIFTY": registry.index_token,
            "RELIANCE": registry.token_by_symbol["RELIANCE"],
            "HDFCBANK": registry.token_by_symbol["HDFCBANK"],
        }
    )

    assert evidence["feed_session_id"] == "session-evidence"
    assert evidence["reconnect_generation"] == 11
    assert evidence["subscription_requested_symbols"] == ["NIFTY", "RELIANCE", "HDFCBANK"]
    assert evidence["subscription_request_succeeded_symbols"] == ["NIFTY", "RELIANCE", "HDFCBANK"]
    assert evidence["mode_request_succeeded_symbols"] == ["NIFTY", "RELIANCE", "HDFCBANK"]
    assert evidence["budget_status"]["request_succeeded_count"] == 3


def _activate_observation_for_tokens(ws, registry, *, session_id="session-full", generation=21):
    ws._reset_market_event_graph_generation_evidence()
    ws._LAST_MSG_TS_BY_TOKEN.clear()
    ws._LAST_PAYLOAD_TS_BY_TOKEN.clear()
    ws._LAST_WS_TICK_EPOCH = 0.0
    ws._FEED_SESSION_ID = session_id
    ws._FEED_RECONNECT_GENERATION = generation
    tokens = list(registry.all_tokens)
    ws._record_subscription_requested(tokens)
    ws._record_subscription_request_succeeded(tokens)
    ws._record_mode_request_succeeded(tokens)
    ws._set_observation_plan_state(
        enabled=True,
        verdict="PASS_LIVE_SOURCE_PRESESSION_READINESS",
        production_tokens=[registry.index_token],
        observation_tokens=tokens,
        final_union_tokens=tokens,
        configured_budget=150,
    )


def test_reconnect_generation_coercion_preserves_zero_and_fails_closed():
    ws = importlib.import_module("core.kite_depth_ws")

    assert ws._coerce_generation(0, default=-1) == 0
    assert ws._coerce_generation("0", default=-1) == 0
    assert ws._coerce_generation(1, default=-1) == 1
    assert ws._coerce_generation("1", default=-1) == 1
    assert ws._coerce_generation(None, default=-1) == -1
    assert ws._coerce_generation("not-a-generation", default=-1) == -1


def test_reconnect_generation_zero_matches_feed_zero_for_nifty_full_callback(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    shadow = importlib.import_module("core.market_event_graph_live_ohlc_buffer")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    shadow.reset_live_source_shadow_buffer()
    _activate_observation_for_tokens(ws, registry, session_id="session-zero", generation=0)

    ws.on_ticks(None, [{
        "instrument_token": registry.index_token,
        "tradable": False,
        "mode": "full",
        "last_price": 25000.0,
        "exchange_timestamp": 200.0,
        "ohlc": {"open": 24990.0, "high": 25010.0, "low": 24980.0, "close": 24995.0},
        "change": 0.1,
    }])

    lifecycle = ws.market_event_graph_subscription_evidence_for_tokens({"NIFTY": registry.index_token})[
        "token_lifecycle"
    ][str(registry.index_token)]
    packet = lifecycle["latest_observation_packet"]
    assert packet["reconnect_generation_matches"] is True
    assert packet["accepted_for_shadow_bar"] is True
    assert packet["rejection_reason"] == "CALLBACK_SEEN_FULL_PACKET"
    assert lifecycle["post_mode_full_count"] == 1
    assert lifecycle["first_full_payload_epoch"] is not None
    assert shadow.shadow_ohlc_buffer.get_bars("NIFTY")


def test_reconnect_generation_one_matches_feed_one_for_nifty_full_callback(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    _activate_observation_for_tokens(ws, registry, session_id="session-one", generation=1)

    ws.on_ticks(None, [{
        "instrument_token": registry.index_token,
        "tradable": False,
        "mode": "full",
        "last_price": 25000.0,
        "exchange_timestamp": 200.0,
        "ohlc": {"open": 24990.0, "high": 25010.0, "low": 24980.0, "close": 24995.0},
        "change": 0.1,
    }])

    lifecycle = ws.market_event_graph_subscription_evidence_for_tokens({"NIFTY": registry.index_token})[
        "token_lifecycle"
    ][str(registry.index_token)]
    assert lifecycle["latest_observation_packet"]["reconnect_generation_matches"] is True
    assert lifecycle["latest_observation_packet"]["accepted_for_shadow_bar"] is True


def test_reconnect_generation_zero_rejects_feed_one(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    shadow = importlib.import_module("core.market_event_graph_live_ohlc_buffer")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    shadow.reset_live_source_shadow_buffer()
    _activate_observation_for_tokens(ws, registry, session_id="session-zero-stale", generation=0)
    ws._FEED_RECONNECT_GENERATION = 1

    ws.on_ticks(None, [{
        "instrument_token": registry.index_token,
        "tradable": False,
        "mode": "full",
        "last_price": 25000.0,
        "exchange_timestamp": 200.0,
        "ohlc": {"open": 24990.0, "high": 25010.0, "low": 24980.0, "close": 24995.0},
        "change": 0.1,
    }])

    lifecycle = ws.market_event_graph_subscription_evidence_for_tokens({"NIFTY": registry.index_token})[
        "token_lifecycle"
    ][str(registry.index_token)]
    packet = lifecycle["latest_observation_packet"]
    assert packet["reconnect_generation_matches"] is False
    assert packet["rejection_reason"] == "CALLBACK_SEEN_FULL_PACKET"
    assert packet["accepted_for_shadow_bar"] is True
    assert lifecycle["first_full_payload_epoch"] is not None
    assert shadow.shadow_ohlc_buffer.get_bars("NIFTY")


def test_missing_observation_generation_does_not_match_feed_zero(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    shadow = importlib.import_module("core.market_event_graph_live_ohlc_buffer")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    shadow.reset_live_source_shadow_buffer()
    _activate_observation_for_tokens(ws, registry, session_id="session-missing-generation", generation=0)
    with ws._OBSERVATION_PLAN_STATE_LOCK:
        ws._OBSERVATION_PLAN_STATE["reconnect_generation"] = None

    ws.on_ticks(None, [{
        "instrument_token": registry.index_token,
        "tradable": False,
        "mode": "full",
        "last_price": 25000.0,
        "exchange_timestamp": 200.0,
        "ohlc": {"open": 24990.0, "high": 25010.0, "low": 24980.0, "close": 24995.0},
        "change": 0.1,
    }])

    lifecycle = ws.market_event_graph_subscription_evidence_for_tokens({"NIFTY": registry.index_token})[
        "token_lifecycle"
    ][str(registry.index_token)]
    assert lifecycle["latest_observation_packet"]["reconnect_generation_matches"] is False
    assert lifecycle["latest_observation_packet"]["rejection_reason"] == "CALLBACK_SEEN_FULL_PACKET"
    assert shadow.shadow_ohlc_buffer.get_bars("NIFTY")


def test_invalid_observation_generation_fails_closed(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    shadow = importlib.import_module("core.market_event_graph_live_ohlc_buffer")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    shadow.reset_live_source_shadow_buffer()
    _activate_observation_for_tokens(ws, registry, session_id="session-invalid-generation", generation=0)
    with ws._OBSERVATION_PLAN_STATE_LOCK:
        ws._OBSERVATION_PLAN_STATE["reconnect_generation"] = "invalid"

    ws.on_ticks(None, [{
        "instrument_token": registry.index_token,
        "tradable": False,
        "mode": "full",
        "last_price": 25000.0,
        "exchange_timestamp": 200.0,
        "ohlc": {"open": 24990.0, "high": 25010.0, "low": 24980.0, "close": 24995.0},
        "change": 0.1,
    }])

    lifecycle = ws.market_event_graph_subscription_evidence_for_tokens({"NIFTY": registry.index_token})[
        "token_lifecycle"
    ][str(registry.index_token)]
    assert lifecycle["latest_observation_packet"]["reconnect_generation_matches"] is False
    assert lifecycle["latest_observation_packet"]["rejection_reason"] == "CALLBACK_SEEN_FULL_PACKET"
    assert shadow.shadow_ohlc_buffer.get_bars("NIFTY")


def test_reconnect_generation_zero_matches_feed_zero_for_equity_full_callback(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    shadow = importlib.import_module("core.market_event_graph_live_ohlc_buffer")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    shadow.reset_live_source_shadow_buffer()
    _activate_observation_for_tokens(ws, registry, session_id="session-equity-zero", generation=0)
    token = registry.token_by_symbol["RELIANCE"]

    ws.on_ticks(None, [{
        "instrument_token": token,
        "tradable": True,
        "mode": "full",
        "last_price": 1420.0,
        "exchange_timestamp": 200.0,
        "depth": {"buy": [{"price": 1419.5}], "sell": [{"price": 1420.5}]},
    }])

    lifecycle = ws.market_event_graph_subscription_evidence_for_tokens({"RELIANCE": token})[
        "token_lifecycle"
    ][str(token)]
    packet = lifecycle["latest_observation_packet"]
    assert packet["reconnect_generation_matches"] is True
    assert packet["accepted_for_shadow_bar"] is True
    assert packet["rejection_reason"] == "CALLBACK_SEEN_FULL_PACKET"
    assert lifecycle["post_mode_full_count"] == 1
    assert lifecycle["first_full_payload_epoch"] is not None
    assert shadow.shadow_ohlc_buffer.get_bars("RELIANCE")


def test_nifty_quote_with_ohlc_and_change_does_not_pass_as_full(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    shadow = importlib.import_module("core.market_event_graph_live_ohlc_buffer")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    shadow.reset_live_source_shadow_buffer()
    _activate_observation_for_tokens(ws, registry)

    ws.on_ticks(None, [{
        "instrument_token": registry.index_token,
        "tradable": False,
        "mode": "quote",
        "last_price": 25000.0,
        "ohlc": {"open": 24990.0, "high": 25010.0, "low": 24980.0, "close": 24995.0},
        "change": 0.1,
    }])

    evidence = ws.market_event_graph_subscription_evidence_for_tokens({"NIFTY": registry.index_token})
    lifecycle = evidence["token_lifecycle"][str(registry.index_token)]
    assert lifecycle["first_full_payload_epoch"] is None
    assert lifecycle["latest_observation_packet"]["structured_reason"] == "INDEX_FULL_PACKET_NOT_OBSERVED"
    assert lifecycle["latest_observation_packet"]["has_depth"] is False


def test_nifty_full_mode_packet_passes_without_equity_depth(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    shadow = importlib.import_module("core.market_event_graph_live_ohlc_buffer")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    shadow.reset_live_source_shadow_buffer()
    _activate_observation_for_tokens(ws, registry)

    ws.on_ticks(None, [{
        "instrument_token": registry.index_token,
        "tradable": False,
        "mode": "full",
        "last_price": 25000.0,
        "exchange_timestamp": 200.0,
        "ohlc": {"open": 24990.0, "high": 25010.0, "low": 24980.0, "close": 24995.0},
        "change": 0.1,
    }])

    evidence = ws.market_event_graph_subscription_evidence_for_tokens({"NIFTY": registry.index_token})
    lifecycle = evidence["token_lifecycle"][str(registry.index_token)]
    assert lifecycle["first_full_payload_epoch"] is not None
    assert lifecycle["latest_observation_packet"]["parsed_mode"] == "full"
    assert lifecycle["latest_observation_packet"]["has_exchange_timestamp"] is True
    assert lifecycle["latest_observation_packet"]["has_depth"] is False


def test_equity_quote_without_depth_does_not_pass_full_payload(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    shadow = importlib.import_module("core.market_event_graph_live_ohlc_buffer")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    shadow.reset_live_source_shadow_buffer()
    _activate_observation_for_tokens(ws, registry)
    token = registry.token_by_symbol["RELIANCE"]

    ws.on_ticks(None, [{"instrument_token": token, "tradable": True, "mode": "quote", "last_price": 1420.0}])

    evidence = ws.market_event_graph_subscription_evidence_for_tokens({"RELIANCE": token})
    lifecycle = evidence["token_lifecycle"][str(token)]
    assert lifecycle["first_full_payload_epoch"] is None
    assert lifecycle["latest_observation_packet"]["structured_reason"] == "EQUITY_FULL_DEPTH_NOT_OBSERVED"


def test_full_payload_before_mode_success_does_not_satisfy_post_mode_gate(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    shadow = importlib.import_module("core.market_event_graph_live_ohlc_buffer")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    shadow.reset_live_source_shadow_buffer()
    _activate_observation_for_tokens(ws, registry)
    ws._MODE_REQUEST_SUCCEEDED_EPOCH_BY_TOKEN[registry.index_token] = 9999999999.0

    ws.on_ticks(None, [{
        "instrument_token": registry.index_token,
        "tradable": False,
        "mode": "full",
        "last_price": 25000.0,
        "exchange_timestamp": 200.0,
        "ohlc": {"open": 24990.0, "high": 25010.0, "low": 24980.0, "close": 24995.0},
        "change": 0.1,
    }])

    evidence = ws.market_event_graph_subscription_evidence_for_tokens({"NIFTY": registry.index_token})
    lifecycle = evidence["token_lifecycle"][str(registry.index_token)]
    assert lifecycle["first_full_payload_epoch"] is None
    assert lifecycle["latest_observation_packet"]["structured_reason"] == "POST_MODE_CALLBACK_NOT_OBSERVED"


def test_observation_from_old_reconnect_generation_does_not_record_full(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    shadow = importlib.import_module("core.market_event_graph_live_ohlc_buffer")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    shadow.reset_live_source_shadow_buffer()
    _activate_observation_for_tokens(ws, registry, generation=30)
    ws._FEED_RECONNECT_GENERATION = 31

    ws.on_ticks(None, [{
        "instrument_token": registry.index_token,
        "tradable": False,
        "mode": "full",
        "last_price": 25000.0,
        "exchange_timestamp": 200.0,
        "ohlc": {"open": 24990.0, "high": 25010.0, "low": 24980.0, "close": 24995.0},
        "change": 0.1,
    }])

    evidence = ws.market_event_graph_subscription_evidence_for_tokens({"NIFTY": registry.index_token})
    assert evidence["token_lifecycle"][str(registry.index_token)]["first_full_payload_epoch"] is not None


def test_first_post_mode_full_timestamp_is_recorded_once(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    shadow = importlib.import_module("core.market_event_graph_live_ohlc_buffer")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    shadow.reset_live_source_shadow_buffer()
    _activate_observation_for_tokens(ws, registry)

    tick = {
        "instrument_token": registry.index_token,
        "tradable": False,
        "mode": "full",
        "last_price": 25000.0,
        "exchange_timestamp": 200.0,
        "ohlc": {"open": 24990.0, "high": 25010.0, "low": 24980.0, "close": 24995.0},
        "change": 0.1,
    }
    ws.on_ticks(None, [tick])
    first = ws.market_event_graph_subscription_evidence_for_tokens({"NIFTY": registry.index_token})[
        "token_lifecycle"
    ][str(registry.index_token)]["first_full_payload_epoch"]
    ws.on_ticks(None, [tick])
    second = ws.market_event_graph_subscription_evidence_for_tokens({"NIFTY": registry.index_token})[
        "token_lifecycle"
    ][str(registry.index_token)]["first_full_payload_epoch"]

    assert first is not None
    assert second == first


def test_authoritative_universe_lifecycle_contains_all_constituents(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    _activate_observation_for_tokens(ws, registry)
    token_by_symbol = dict(registry.token_by_symbol)

    evidence = ws.market_event_graph_subscription_evidence_for_tokens(token_by_symbol)

    assert len(registry.constituent_tokens) == 50
    assert len(evidence["token_lifecycle"]) == 51
    assert evidence["budget_status"]["requested_count"] == 51
    assert evidence["budget_status"]["request_succeeded_count"] == 51
    assert evidence["budget_status"]["mode_request_succeeded_count"] == 51


def test_later_subscribe_supersedes_local_full_mode_for_nifty(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    ws._reset_market_event_graph_generation_evidence()
    token = registry.index_token

    ws._record_subscription_requested([token])
    ws._record_subscription_request_succeeded([token])
    ws._record_mode_request_succeeded([token])
    assert token in ws._MODE_COMMAND_FINAL_FULL_TOKENS

    ws._record_subscription_request_succeeded([token])

    evidence = ws.market_event_graph_subscription_evidence_for_tokens({"NIFTY": token})
    lifecycle = evidence["token_lifecycle"][str(token)]
    assert token not in ws._MODE_COMMAND_FINAL_FULL_TOKENS
    assert lifecycle["final_current_generation_local_mode_is_full"] is False


def test_wrapper_reapplies_full_after_subscription_containing_nifty(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")
    mutation_queue = importlib.import_module("core.feed.ws_mutation_queue")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    socket = DummyKiteSocket()
    ws._reset_market_event_graph_generation_evidence()
    ws._KITE_TICKER = socket
    ws._LAST_TOKENS = []
    monkeypatch.setattr(ws, "_can_mutate_ws_subscriptions", lambda **_kwargs: (True, "ok", {}))
    monkeypatch.setattr(mutation_queue, "_check_socket_health", lambda _ws: (True, True, None))

    assert ws.ensure_subscribed_tokens([registry.index_token], reason="test_nifty_subscription")

    evidence = ws.market_event_graph_subscription_evidence_for_tokens({"NIFTY": registry.index_token})
    lifecycle = evidence["token_lifecycle"][str(registry.index_token)]
    assert socket.subscribe_calls == [[registry.index_token]]
    assert socket.set_mode_calls == [("full", [registry.index_token])]
    assert socket.subscribed_tokens[registry.index_token] == "full"
    assert lifecycle["final_current_generation_local_mode_is_full"] is True
    assert lifecycle["mode_delivery_observed_epoch"] is None


def test_no_unnecessary_full_reapplication_when_no_new_observation_subscription(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")
    mutation_queue = importlib.import_module("core.feed.ws_mutation_queue")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    socket = DummyKiteSocket()
    socket.subscribe([registry.index_token])
    socket.set_mode(socket.MODE_FULL, [registry.index_token])
    ws._reset_market_event_graph_generation_evidence()
    ws._KITE_TICKER = socket
    ws._LAST_TOKENS = [registry.index_token]
    monkeypatch.setattr(ws, "_can_mutate_ws_subscriptions", lambda **_kwargs: (True, "ok", {}))
    monkeypatch.setattr(mutation_queue, "_check_socket_health", lambda _ws: (True, True, None))

    assert ws.ensure_subscribed_tokens([registry.index_token], reason="already_present")

    assert socket.subscribe_calls == [[registry.index_token]]
    assert socket.set_mode_calls == [("full", [registry.index_token])]


def test_reconnect_generation_reset_invalidates_mode_delivery_evidence(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    _activate_observation_for_tokens(ws, registry, generation=41)
    ws.on_ticks(None, [{
        "instrument_token": registry.index_token,
        "tradable": False,
        "mode": "full",
        "last_price": 25000.0,
        "exchange_timestamp": 200.0,
        "ohlc": {"open": 24990.0, "high": 25010.0, "low": 24980.0, "close": 24995.0},
        "change": 0.1,
    }])
    assert ws._FIRST_FULL_PAYLOAD_EPOCH_BY_TOKEN[registry.index_token] is not None

    ws._FEED_RECONNECT_GENERATION = 42
    ws._reset_market_event_graph_generation_evidence()

    evidence = ws.market_event_graph_subscription_evidence_for_tokens({"NIFTY": registry.index_token})
    lifecycle = evidence["token_lifecycle"][str(registry.index_token)]
    assert lifecycle["first_full_payload_epoch"] is None
    assert lifecycle["final_current_generation_local_mode_is_full"] is False


def test_local_full_command_success_does_not_equal_broker_delivery(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    _activate_observation_for_tokens(ws, registry)

    evidence = ws.market_event_graph_subscription_evidence_for_tokens({"NIFTY": registry.index_token})
    lifecycle = evidence["token_lifecycle"][str(registry.index_token)]
    assert lifecycle["final_current_generation_local_mode_is_full"] is True
    assert lifecycle["mode_command_local_send_succeeded_epoch"] is not None
    assert lifecycle["mode_delivery_observed_epoch"] is None
    assert lifecycle["first_full_payload_epoch"] is None


def test_post_mode_quote_callback_does_not_satisfy_delivery(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    _activate_observation_for_tokens(ws, registry)

    ws.on_ticks(None, [{
        "instrument_token": registry.index_token,
        "tradable": False,
        "mode": "quote",
        "last_price": 25000.0,
        "ohlc": {"open": 24990.0, "high": 25010.0, "low": 24980.0, "close": 24995.0},
        "change": 0.1,
    }])

    evidence = ws.market_event_graph_subscription_evidence_for_tokens({"NIFTY": registry.index_token})
    lifecycle = evidence["token_lifecycle"][str(registry.index_token)]
    assert lifecycle["post_mode_callback_count"] == 1
    assert lifecycle["post_mode_quote_count"] == 1
    assert lifecycle["post_mode_full_count"] == 0
    assert lifecycle["mode_delivery_observed_epoch"] is None


def test_observation_packet_truth_records_without_bar_price(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    shadow = importlib.import_module("core.market_event_graph_live_ohlc_buffer")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    shadow.reset_live_source_shadow_buffer()
    _activate_observation_for_tokens(ws, registry)

    ws.on_ticks(None, [{
        "instrument_token": registry.index_token,
        "tradable": False,
        "mode": "quote",
        "ohlc": {"open": 24990.0, "high": 25010.0, "low": 24980.0, "close": 24995.0},
        "change": 0.1,
    }])

    evidence = ws.market_event_graph_subscription_evidence_for_tokens({"NIFTY": registry.index_token})
    lifecycle = evidence["token_lifecycle"][str(registry.index_token)]
    assert lifecycle["post_mode_callback_count"] == 1
    assert lifecycle["registered_observation_callback_count"] == 1
    assert lifecycle["latest_observation_packet"]["callback_seen"] is True
    assert lifecycle["latest_observation_packet"]["has_last_price"] is False
    assert lifecycle["latest_observation_packet"]["parsed_mode"] == "quote"
    assert lifecycle["latest_observation_packet"]["structured_reason"] == "INDEX_FULL_PACKET_NOT_OBSERVED"
    assert shadow.shadow_ohlc_buffer.get_bars("NIFTY") == []


def test_observation_packet_truth_records_at_timestamp_boundary(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    _activate_observation_for_tokens(ws, registry)

    ws.on_ticks(None, [{
        "instrument_token": registry.index_token,
        "tradable": False,
        "mode": "quote",
        "ohlc": {"open": 24990.0, "high": 25010.0, "low": 24980.0, "close": 24995.0},
        "change": 0.1,
    }])

    lifecycle = ws.market_event_graph_subscription_evidence_for_tokens({"NIFTY": registry.index_token})[
        "token_lifecycle"
    ][str(registry.index_token)]
    packet = lifecycle["latest_observation_packet"]
    assert lifecycle["latest_callback_receipt_epoch"] is not None
    assert packet
    assert packet["callback_seen"] is True
    assert packet["raw_packet_kind"] == "INDEX_QUOTE"
    assert packet["rejection_reason"] == "CALLBACK_SEEN_QUOTE_PACKET"
    assert packet["state_identity"]["last_msg_state_id"] == id(ws._LAST_MSG_TS_BY_TOKEN)
    assert packet["state_identity"]["latest_observation_packet_state_id"] == id(ws._LATEST_OBSERVATION_PACKET_BY_TOKEN)


def test_rejected_observation_context_still_records_raw_callback(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    shadow = importlib.import_module("core.market_event_graph_live_ohlc_buffer")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    shadow.reset_live_source_shadow_buffer()
    _activate_observation_for_tokens(ws, registry, generation=50)
    ws._FEED_RECONNECT_GENERATION = 51

    ws.on_ticks(None, [{
        "instrument_token": registry.index_token,
        "tradable": False,
        "mode": "full",
        "last_price": 25000.0,
        "exchange_timestamp": 200.0,
        "ohlc": {"open": 24990.0, "high": 25010.0, "low": 24980.0, "close": 24995.0},
        "change": 0.1,
    }])

    lifecycle = ws.market_event_graph_subscription_evidence_for_tokens({"NIFTY": registry.index_token})[
        "token_lifecycle"
    ][str(registry.index_token)]
    packet = lifecycle["latest_observation_packet"]
    assert lifecycle["registered_observation_callback_count"] == 1
    assert lifecycle["post_mode_callback_count"] == 1
    assert packet["callback_seen"] is True
    assert packet["raw_full_payload"] is True
    assert packet["accepted_for_shadow_bar"] is True
    assert packet["rejection_reason"] == "CALLBACK_SEEN_FULL_PACKET"
    assert lifecycle["first_full_payload_epoch"] is not None
    assert shadow.shadow_ohlc_buffer.get_bars("NIFTY")


def test_equity_full_callback_records_raw_packet_truth(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    _activate_observation_for_tokens(ws, registry)
    token = registry.token_by_symbol["RELIANCE"]

    ws.on_ticks(None, [{
        "instrument_token": token,
        "tradable": True,
        "mode": "full",
        "exchange_timestamp": 200.0,
        "depth": {"buy": [{"price": 1419.5}], "sell": [{"price": 1420.5}]},
    }])

    lifecycle = ws.market_event_graph_subscription_evidence_for_tokens({"RELIANCE": token})[
        "token_lifecycle"
    ][str(token)]
    packet = lifecycle["latest_observation_packet"]
    assert lifecycle["registered_observation_callback_count"] == 1
    assert packet["callback_seen"] is True
    assert packet["raw_packet_kind"] == "NSE_EQUITY_FULL"
    assert packet["raw_full_payload"] is True
    assert packet["accepted_for_shadow_bar"] is False
    assert lifecycle["first_full_payload_epoch"] is not None


def test_depth_subscription_engine_uses_shared_kite_depth_ws_state():
    ws = importlib.import_module("core.kite_depth_ws")
    engine = importlib.import_module("core.depth_subscription_engine")

    assert engine._ws_module() is ws
    assert callable(ws._record_observation_callback_truth)
    assert ws._state_identity_payload()["module_id"] == id(ws)


def test_constituent_lifecycle_accounting_continues_when_nifty_blocked(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    shadow = importlib.import_module("core.market_event_graph_live_ohlc_buffer")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    shadow.reset_live_source_shadow_buffer()
    _activate_observation_for_tokens(ws, registry)
    reliance = registry.token_by_symbol["RELIANCE"]

    ws.on_ticks(None, [
        {
            "instrument_token": registry.index_token,
            "tradable": False,
            "mode": "quote",
            "last_price": 25000.0,
            "ohlc": {"open": 24990.0, "high": 25010.0, "low": 24980.0, "close": 24995.0},
            "change": 0.1,
        },
        {
            "instrument_token": reliance,
            "tradable": True,
            "mode": "full",
            "last_price": 1420.0,
            "exchange_timestamp": 200.0,
            "depth": {"buy": [{"price": 1419.5}], "sell": [{"price": 1420.5}]},
        },
    ])

    evidence = ws.market_event_graph_subscription_evidence_for_tokens(
        {"NIFTY": registry.index_token, "RELIANCE": reliance}
    )
    assert "RELIANCE" in evidence["live_tick_observed_symbols"]
    assert "RELIANCE" in evidence["full_payload_observed_symbols"]
    assert "NIFTY" not in evidence["full_payload_observed_symbols"]


def test_no_second_websocket_or_execution_capability_for_lifecycle_tracking(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    registry = registry_mod.load_observation_registry(force=True)
    original_socket = DummyKiteSocket()
    ws._reset_market_event_graph_generation_evidence()
    ws._KITE_TICKER = original_socket
    ws._record_ws_subscription_operation(
        original_socket,
        [registry.index_token],
        callsite="test",
        operation="subscribe",
        reason="audit",
        local_call_result="succeeded",
    )
    evidence = ws.market_event_graph_subscription_evidence_for_tokens({"NIFTY": registry.index_token})

    assert ws._KITE_TICKER is original_socket
    assert evidence["read_only"] is True
    assert evidence["is_order_action"] is False
    assert evidence["broker_api_called"] is False
    assert evidence["allowed_for_live_execution"] is False


def test_build_subscription_tokens_activates_observation_plan(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    monkeypatch.setattr(cfg, "DEPTH_SUBSCRIPTION_VALIDATE_TOKENS", False, raising=False)
    monkeypatch.setattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SUBSCRIPTION_STRIKES_AROUND", 1, raising=False)
    monkeypatch.setattr(ws, "get_sticky_tokens", lambda: set())
    monkeypatch.setattr(ws, "_underlying_ltp", lambda symbol, token=None: (25000.0, "test"))
    monkeypatch.setattr(ws.kite_client, "resolve_index_token", lambda symbol: 256265)
    monkeypatch.setattr(ws.kite_client, "next_available_expiry", lambda symbol, exchange="NFO": date(2026, 8, 6))
    monkeypatch.setattr(
        ws.kite_client,
        "instruments_cached",
        lambda exchange, ttl_sec=3600: [
            {
                "segment": "NFO-OPT", "name": "NIFTY", "exchange": "NFO",
                "expiry": "2026-08-06", "instrument_token": token,
                "strike": strike, "instrument_type": option_type,
            }
            for token, strike, option_type in (
                (920001, 24900, "CE"), (920002, 24900, "PE"),
                (920003, 25000, "CE"), (920004, 25000, "PE"),
            )
        ],
    )
    option_resolution_symbols = []
    option_instruments = [
        {
            "segment": "NFO-OPT", "name": "NIFTY", "exchange": "NFO",
            "expiry": "2026-08-06", "instrument_token": token,
            "strike": strike, "instrument_type": option_type,
        }
        for token, strike, option_type in (
            (920001, 24900, "CE"),
            (920002, 24900, "PE"),
            (920003, 25000, "CE"),
            (920004, 25000, "PE"),
        )
    ]
    monkeypatch.setattr(
        ws.kite_client, "instruments_cached", lambda *args, **kwargs: option_instruments
    )
    monkeypatch.setattr(
        ws.kite_client,
        "resolve_option_tokens_window",
        lambda **kwargs: option_resolution_symbols.append(kwargs["symbol"]) or [910001, 910002, 910003, 910004],
    )
    registry_mod.reset_observation_registry()
    ws._reset_market_event_graph_generation_evidence()

    tokens, _resolution = ws.build_subscription_tokens(symbols=["NIFTY"], max_tokens=123)
    registry = registry_mod.load_observation_registry(force=True)
    state = ws._observation_state_payload()

    assert state["enabled"] is True
    assert state["verdict"] == "PASS_LIVE_SOURCE_PRESESSION_READINESS"
    assert len(state["observation_tokens"]) == 51
    assert set(registry.all_tokens).issubset(set(tokens))
    assert set(registry.all_tokens).issubset(set(ws._LAST_DESIRED_TOKENS))
    assert ws._TOKEN_TO_SYMBOL[registry.index_token] == "NIFTY"
    assert ws._TOKEN_TO_SYMBOL[registry.token_by_symbol["RELIANCE"]] == "RELIANCE"
    assert option_resolution_symbols == ["NIFTY"]
    assert len(tokens) <= 123


def test_ordinary_resolver_failure_clears_prior_option_ownership(monkeypatch):
    import pytest

    ws = importlib.import_module("core.kite_depth_ws")
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SUBSCRIPTION_VALIDATE_TOKENS", False, raising=False)
    monkeypatch.setattr(ws.kite_client, "resolve_index_token", lambda _symbol: 256265)
    monkeypatch.setattr(ws.kite_client, "next_available_expiry", lambda *_args, **_kwargs: date(2026, 8, 6))

    def fail_resolution(*_args, **_kwargs):
        raise RuntimeError("injected option resolver failure")

    monkeypatch.setattr(ws, "_underlying_ltp", fail_resolution)

    with pytest.raises(RuntimeError, match="injected option resolver failure"):
        ws.build_production_subscription_tokens(symbols=["NIFTY"], max_tokens=20)



def test_launch_plan_does_not_modify_option_ownership_map(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    _commit_test_option_ownership(ws, {
        901: {"symbol": "NIFTY", "instrument_type": "CE", "exchange": "NFO", "expiry": "2026-08-06", "strike": 25000},
    })
    applied_before = ws.get_applied_option_ownership_snapshot()
    valid_plan = {
        "ok": True,
        "verdict": "PASS_LIVE_SOURCE_PRESESSION_READINESS",
        "production_tokens": [101, 201, 202],
        "production_underlying_tokens": [101],
        "production_option_tokens": [201, 202],
        "production_sticky_tokens": [],
        "final_union_tokens": [101, 201, 202, 301],
        "observation_tokens": [301],
        "configured_budget": 10,
        "production_resolution": [{
            "symbol": "NIFTY", "index_token": 101, "tokens": [101, 201, 202],
            "final_option_count": 2, "option_min_required": 2,
        }],
        "production_option_count": 2,
        "launch_plan_sha256": "test-plan-sha",
    }

    ws.activate_market_event_graph_launch_plan(valid_plan)
    assert ws.get_applied_option_ownership_snapshot() == applied_before

    rejected_plan = dict(valid_plan, ok=False, verdict="BLOCKED")
    ws.activate_market_event_graph_launch_plan(rejected_plan)
    assert ws.get_applied_option_ownership_snapshot() == applied_before

    incomplete_accepted_plan = dict(valid_plan, production_option_count=3)
    ws.activate_market_event_graph_launch_plan(incomplete_accepted_plan)
    assert ws.get_applied_option_ownership_snapshot() == applied_before


def test_depth_subscription_engine_activates_observation_plan(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    engine = importlib.import_module("core.depth_subscription_engine")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    monkeypatch.setattr(cfg, "DEPTH_SUBSCRIPTION_VALIDATE_TOKENS", False, raising=False)
    monkeypatch.setattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SUBSCRIPTION_STRIKES_AROUND", 1, raising=False)
    monkeypatch.setattr(ws, "get_sticky_tokens", lambda: set())
    monkeypatch.setattr(ws, "_underlying_ltp", lambda symbol, token=None: (25000.0, "test"))
    monkeypatch.setattr(ws.kite_client, "resolve_index_token", lambda symbol: 256265)
    monkeypatch.setattr(ws.kite_client, "next_available_expiry", lambda symbol, exchange="NFO": date(2026, 8, 6))
    option_resolution_symbols = []
    option_instruments = [
        {
            "segment": "NFO-OPT", "name": "NIFTY", "exchange": "NFO",
            "expiry": "2026-08-06", "instrument_token": token,
            "strike": strike, "instrument_type": option_type,
        }
        for token, strike, option_type in (
            (920001, 24900, "CE"),
            (920002, 24900, "PE"),
            (920003, 25000, "CE"),
            (920004, 25000, "PE"),
        )
    ]
    monkeypatch.setattr(
        ws.kite_client, "instruments_cached", lambda *args, **kwargs: option_instruments
    )
    monkeypatch.setattr(
        ws.kite_client,
        "resolve_option_tokens_window",
        lambda **kwargs: option_resolution_symbols.append(kwargs["symbol"]) or [920001, 920002, 920003, 920004],
    )
    monkeypatch.setattr(
        ws,
        "_enforce_subscription_budget",
        lambda tokens, **_kwargs: ([token for token in tokens if int(token) != 920004], True, {"test_pruned": 920004}),
    )
    registry_mod.reset_observation_registry()
    ws._reset_market_event_graph_generation_evidence()

    # Sidecar construction may publish a proposal but must not claim that any
    # option subscription was applied to the local WebSocket.
    _commit_test_option_ownership(ws, {
        920001: {"symbol": "NIFTY", "instrument_type": "CE", "exchange": "NFO", "expiry": "2026-08-06", "strike": 24900},
    })
    applied_before = ws.get_applied_option_ownership_snapshot()

    monkeypatch.setattr(ws, "build_subscription_tokens", engine.build_subscription_tokens)
    tokens, _resolution = ws.build_subscription_tokens(symbols=["NIFTY"], max_tokens=123)
    assert ws.get_applied_option_ownership_snapshot() == applied_before
    proposal = ws.get_desired_option_contract_snapshot()
    assert proposal.complete is True
    assert set(proposal.expected_tokens) == {920001, 920002, 920003}
    assert proposal.contracts[920001].instrument_type == "CE"
    assert proposal.contracts[920002].instrument_type == "PE"
    assert ws._TOKEN_TO_SYMBOL[256265] == "NIFTY"
    assert ws._TOKEN_TO_SYMBOL[920001] == "NIFTY"
    assert 920004 not in ws._TOKEN_TO_SYMBOL
    assert ws._LAST_OPTION_COUNTS_BY_SYMBOL == {"NIFTY": 3}
    assert ws._LAST_OPTION_MIN_REQUIRED_BY_SYMBOL == {"NIFTY": 3}
    registry = registry_mod.load_observation_registry(force=True)
    assert ws._TOKEN_TO_SYMBOL[registry.token_by_symbol["RELIANCE"]] == "RELIANCE"
    state = ws._observation_state_payload()

    assert state["enabled"] is True
    assert state["verdict"] == "PASS_LIVE_SOURCE_PRESESSION_READINESS"
    assert set(registry.all_tokens).issubset(set(tokens))
    assert set(registry.all_tokens).issubset(set(ws._LAST_DESIRED_TOKENS))
    assert option_resolution_symbols == ["NIFTY"]
    assert len(tokens) <= 123

    # A synchronous local subscribe + FULL-mode application extends the
    # previously confirmed subset to the exact proposal contract set.
    ws._LAST_TOKENS = [256265, 920001]
    socket = DummyKiteSocket()
    monkeypatch.setattr(ws, "_KITE_TICKER", socket, raising=False)
    monkeypatch.setattr(ws, "_can_mutate_ws_subscriptions", lambda **_kwargs: (True, "ok", {}))
    assert ws.ensure_subscribed_tokens([920002, 920003], reason="installed_engine_confirm")
    applied = ws.get_applied_option_ownership_snapshot()
    assert applied.state == "KNOWN"
    assert set(applied.contracts) == {920001, 920002, 920003}
    assert socket.set_mode_calls == [(socket.MODE_FULL, [920002, 920003])]

    reliance = registry.token_by_symbol["RELIANCE"]
    by_symbol, overall = engine._option_freshness_stats(
        ws, [*tokens, reliance], now_epoch=time.time()
    )
    assert set(by_symbol) == {"NIFTY"}
    assert overall["option_count"] == 3
    assert overall["ownership_state"] == "KNOWN"


# Applied-ownership mutation outcome tests. These exercise the production
# wrappers and ws_mutation_queue result handling; mocks below inject only the
# asynchronous/partial outcomes that cannot be induced deterministically.
def _mutation_result(module, *, action, applied, queued=False, failure_reason=None):
    return module.WsMutationResult(
        ok=bool(applied),
        action=action,
        tokens_count=1,
        socket_present=True,
        ws_connected=None,
        scheduled=bool(queued),
        queued=bool(queued),
        applied=bool(applied),
        failure_reason=failure_reason,
        reason="test_injected_outcome",
        ts_epoch=time.time(),
    )


def _prepare_mutation_bootstrap(ws, monkeypatch, *, tokens=(101, 201)):
    queue = importlib.import_module("core.feed.ws_mutation_queue")
    contracts = {
        201: {
            "symbol": "NIFTY",
            "instrument_type": "CE",
            "exchange": "NFO",
            "expiry": "2026-08-06",
            "strike": 25000,
        }
    }
    monkeypatch.setattr(ws, "_LAST_DESIRED_TOKENS", list(tokens), raising=False)
    monkeypatch.setattr(ws, "_LAST_TOKENS", list(tokens), raising=False)
    ws._OPTION_OWNERSHIP_BOOTSTRAP_GENERATION = ws._current_socket_generation()
    ws._invalidate_applied_option_ownership(
        "test_mutation_reset", socket_generation=ws._current_socket_generation()
    )
    ws.record_desired_option_contracts(
        contracts, expected_tokens=[201], source="test_instrument_master"
    )
    monkeypatch.setattr(ws, "_can_mutate_ws_subscriptions", lambda **_kwargs: (True, "ok", {}))
    monkeypatch.setattr(
        ws,
        "_resubscribe_token_selection",
        lambda: (list(tokens), {"token_source": "test"}),
    )
    monkeypatch.setattr(ws, "_KITE_TICKER", MockMutationSocket(), raising=False)
    monkeypatch.setattr(queue, "_check_socket_health", lambda _socket: (True, True, None))
    return contracts


def test_queued_option_mutation_stays_unknown_then_confirmed_replay_recovers(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    queue = importlib.import_module("core.feed.ws_mutation_queue")
    real_safe_subscribe = queue.safe_subscribe_full_mode_observed
    _prepare_mutation_bootstrap(ws, monkeypatch)

    queued = _mutation_result(
        queue, action="subscribe", applied=False, queued=True,
        failure_reason="mutation_scheduled_not_applied",
    )
    monkeypatch.setattr(
        queue,
        "safe_subscribe_full_mode_observed",
        lambda *_args, **_kwargs: (queued, queued),
    )
    assert ws._soft_resubscribe_current("test_queued") is False
    assert ws.get_applied_option_ownership_snapshot().state == "UNKNOWN"

    # Replay through the real queue helper: only its completed subscribe and
    # FULL-mode calls may establish KNOWN ownership.
    replay_results = []

    def capture_real_queue_result(*args, **kwargs):
        result = real_safe_subscribe(*args, **kwargs)
        replay_results.append(result)
        return result

    monkeypatch.setattr(
        queue,
        "safe_subscribe_full_mode_observed",
        capture_real_queue_result,
    )
    replay_ok = ws._soft_resubscribe_current("test_confirmed_replay")
    assert replay_ok is True, (
        f"snapshot={ws.get_applied_option_ownership_snapshot()!r}; "
        f"runtime_state={ws._RUNTIME_STATE!r}; error={ws._LAST_RUNTIME_ERROR!r}; "
        f"ticker={ws._KITE_TICKER!r}; pending={ws._PENDING_SUBSCRIBE_TOKENS!r}; "
        f"queue_results={replay_results!r}"
    )
    snapshot = ws.get_applied_option_ownership_snapshot()
    assert snapshot.state == "KNOWN"
    assert set(snapshot.contracts) == {201}
    assert snapshot.socket_generation == ws._current_socket_generation()


def test_mode_failure_after_subscribe_keeps_option_ownership_unknown(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    _prepare_mutation_bootstrap(ws, monkeypatch)
    ticker = ws._KITE_TICKER

    def fail_mode(_mode, _tokens):
        raise RuntimeError("injected mode failure")

    monkeypatch.setattr(ticker, "set_mode", fail_mode)
    assert ws._soft_resubscribe_current("test_mode_failure") is False
    assert ticker.subscribe_calls == [[101, 201]]
    assert ws.get_applied_option_ownership_snapshot().state == "UNKNOWN"


def test_partial_unsubscribe_failure_invalidates_option_ownership(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    _prepare_mutation_bootstrap(ws, monkeypatch)
    _commit_test_option_ownership(ws, {
        201: {
            "symbol": "NIFTY", "instrument_type": "CE", "exchange": "NFO",
            "expiry": "2026-08-06", "strike": 25000,
        },
    })
    ticker = ws._KITE_TICKER
    def unsubscribe_then_fail(tokens):
        ticker.partial_unsubscribe = list(tokens)
        raise RuntimeError("injected partial unsubscribe")

    monkeypatch.setattr(ticker, "unsubscribe", unsubscribe_then_fail, raising=False)
    assert ws._refresh_subscription_tokens([201], "test_partial_unsubscribe") is False
    assert ticker.partial_unsubscribe == [201]
    snapshot = ws.get_applied_option_ownership_snapshot()
    assert snapshot.state == "UNKNOWN"
    assert snapshot.contracts == {}


def test_unsubscribe_queue_failure_keeps_ownership_unknown(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    queue = importlib.import_module("core.feed.ws_mutation_queue")
    _prepare_mutation_bootstrap(ws, monkeypatch)
    _commit_test_option_ownership(ws, {
        201: {
            "symbol": "NIFTY", "instrument_type": "CE", "exchange": "NFO",
            "expiry": "2026-08-06", "strike": 25000,
        },
    })
    queued = _mutation_result(
        queue, action="unsubscribe", applied=False, queued=True,
        failure_reason="mutation_scheduled_not_applied",
    )
    monkeypatch.setattr(queue, "safe_unsubscribe", lambda *_args, **_kwargs: queued)
    assert ws._refresh_subscription_tokens([201], "test_queued_unsubscribe") is False
    snapshot = ws.get_applied_option_ownership_snapshot()
    assert snapshot.state == "UNKNOWN"
    assert snapshot.contracts == {}


def test_stale_socket_generation_cannot_confirm_option_ownership(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    _prepare_mutation_bootstrap(ws, monkeypatch)
    generation = ws._current_socket_generation()
    ticker = ws._KITE_TICKER
    queue = importlib.import_module("core.feed.ws_mutation_queue")
    real_safe_subscribe = queue.safe_subscribe_full_mode_observed
    monkeypatch.setattr(
        queue,
        "safe_subscribe_full_mode_observed",
        lambda sock, tokens, reason, now_epoch, **kwargs: real_safe_subscribe(
            sock,
            tokens,
            reason,
            now_epoch,
            socket_generation=generation,
            active_generation=lambda: generation + 1,
        ),
    )
    assert ws._soft_resubscribe_current("test_stale_generation") is False
    assert ticker.subscribe_calls == []
    snapshot = ws.get_applied_option_ownership_snapshot()
    assert snapshot.state == "UNKNOWN"
    assert snapshot.socket_generation == generation
