import importlib

from config import config as cfg

UNIVERSE = "runtime/reference/market_event_graph/nifty50_live_universe_kite_9fb8832853c27944_828c0c378e493972_fba078a4cd7aeb52.json"


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
