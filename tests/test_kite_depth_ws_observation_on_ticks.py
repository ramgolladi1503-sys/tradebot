import importlib
from datetime import date

from config import config as cfg

UNIVERSE = "runtime/reference/market_event_graph/nifty50_live_universe_kite_9fb8832853c27944_828c0c378e493972_fba078a4cd7aeb52.json"


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
        "exchange_timestamp": 100.0,
        "ohlc": {"open": 24990.0, "high": 25010.0, "low": 24980.0, "close": 24995.0},
        "change": 0.1,
    }
    ws.on_ticks(None, [tick])

    bars = shadow.shadow_ohlc_buffer.get_bars("NIFTY")
    assert bars
    assert bars[-1]["bar_provenance"]["instrument_token"] == 256265
    assert bars[-1]["bar_provenance"]["reconnect_generation"] == 1
    assert bars[-1]["bar_provenance"]["live_feed_session_id"] == "session-1"


def test_on_ticks_ignores_non_observation_tokens(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    shadow = importlib.import_module("core.market_event_graph_live_ohlc_buffer")
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    shadow.reset_live_source_shadow_buffer()
    ws._TOKEN_TO_SYMBOL[999999] = "IGNORED"

    ws.on_ticks(None, [{"instrument_token": 999999, "last_price": 1.0, "exchange_timestamp": 100.0}])

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
            "exchange_timestamp": 100.0,
            "ohlc": {"open": 24990.0, "high": 25010.0, "low": 24980.0, "close": 24995.0},
            "change": 0.1,
        },
        {
            "instrument_token": registry.token_by_symbol["RELIANCE"],
            "last_price": 1420.0,
            "exchange_timestamp": 100.0,
            "depth": {"buy": [{"price": 1419.5}], "sell": [{"price": 1420.5}]},
        },
        {
            "instrument_token": registry.token_by_symbol["HDFCBANK"],
            "last_price": 980.0,
            "exchange_timestamp": 100.0,
            "depth": {"buy": [{"price": 979.5}], "sell": [{"price": 980.5}]},
        },
        {"instrument_token": 999999, "last_price": 1.0, "exchange_timestamp": 100.0},
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
        "exchange_timestamp": 100.0,
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
    assert evidence["token_lifecycle"][str(registry.index_token)]["first_full_payload_epoch"] is None


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
        "resolve_option_tokens_window",
        lambda **_kwargs: [910001, 910002, 910003, 910004],
    )
    registry_mod.reset_observation_registry()
    ws._reset_market_event_graph_generation_evidence()

    tokens, _resolution = ws.build_subscription_tokens(symbols=["NIFTY"], max_tokens=150)
    registry = registry_mod.load_observation_registry(force=True)
    state = ws._observation_state_payload()

    assert state["enabled"] is True
    assert state["verdict"] == "PASS_LIVE_SOURCE_PRESESSION_READINESS"
    assert len(state["observation_tokens"]) == 51
    assert set(registry.all_tokens).issubset(set(tokens))
    assert set(registry.all_tokens).issubset(set(ws._LAST_DESIRED_TOKENS))
    assert ws._TOKEN_TO_SYMBOL[registry.index_token] == "NIFTY"
    assert ws._TOKEN_TO_SYMBOL[registry.token_by_symbol["RELIANCE"]] == "RELIANCE"
