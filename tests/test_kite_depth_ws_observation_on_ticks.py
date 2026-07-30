import importlib

from config import config as cfg


def test_on_ticks_routes_observation_tokens_into_shadow_buffer(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    shadow = importlib.import_module("core.market_event_graph_live_ohlc_buffer")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(
        cfg,
        "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH",
        "runtime/reference/market_event_graph/nifty50_live_universe_kite_9fb8832853c27944_828c0c378e493972_fba078a4cd7aeb52.json",
    )
    registry_mod.load_observation_registry(force=True)
    shadow.reset_live_source_shadow_buffer()
    ws._reset_market_event_graph_generation_evidence()
    ws._FEED_SESSION_ID = "session-1"
    ws._FEED_RECONNECT_GENERATION = 1
    ws._SUBSCRIPTION_REQUEST_SUCCEEDED_TOKENS.update({256265, 738561})
    ws._SUBSCRIPTION_REQUEST_SUCCEEDED_EPOCH_BY_TOKEN[256265] = 1.0
    ws._SUBSCRIPTION_REQUEST_SUCCEEDED_EPOCH_BY_TOKEN[738561] = 1.0
    ws._TOKEN_TO_SYMBOL[256265] = "NIFTY"
    ws._TOKEN_TO_SYMBOL[738561] = "RELIANCE"

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
