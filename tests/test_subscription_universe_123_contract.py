from datetime import date
import importlib
from types import SimpleNamespace

import pytest

from config import config as cfg


UNIVERSE = (
    "runtime/reference/market_event_graph/"
    "nifty50_live_universe_kite_9fb8832853c27944_828c0c378e493972_fba078a4cd7aeb52.json"
)


def test_live_subscription_contract_is_exactly_123_and_constituents_are_cash_only(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    engine = importlib.import_module("core.depth_subscription_engine")
    registry_mod = importlib.import_module("core.market_event_graph_live_observation_registry")

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", UNIVERSE)
    monkeypatch.setattr(cfg, "DEPTH_SUBSCRIPTION_MAX_TOKENS", 123)
    monkeypatch.setattr(cfg, "DEPTH_SUBSCRIPTION_VALIDATE_TOKENS", False)
    monkeypatch.setattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SUBSCRIPTION_STRIKES_AROUND", 6)
    monkeypatch.setattr(
        cfg,
        "DEPTH_SUBSCRIPTION_STRIKES_AROUND_BY_SYMBOL",
        {"NIFTY": 6, "BANKNIFTY": 6, "SENSEX": 4},
    )
    monkeypatch.setattr(
        cfg,
        "STRIKE_STEP_BY_SYMBOL",
        {"NIFTY": 50, "BANKNIFTY": 100, "SENSEX": 100},
    )
    monkeypatch.setattr(ws, "get_sticky_tokens", lambda: set())

    registry_mod.reset_observation_registry()
    registry = registry_mod.load_observation_registry(force=True)
    index_tokens = {
        "NIFTY": registry.index_token,
        "BANKNIFTY": 260105,
        "SENSEX": 265,
    }
    option_counts = {"NIFTY": 26, "BANKNIFTY": 26, "SENSEX": 18}
    option_bases = {"NIFTY": 910000, "BANKNIFTY": 920000, "SENSEX": 930000}
    option_resolution_calls = []

    monkeypatch.setattr(
        ws.kite_client,
        "resolve_index_token",
        lambda symbol: index_tokens[str(symbol).upper()],
    )
    monkeypatch.setattr(
        ws.kite_client,
        "next_available_expiry",
        lambda symbol, exchange="NFO": date(2026, 10, 6),
    )
    monkeypatch.setattr(
        ws,
        "_underlying_ltp",
        lambda symbol, token=None: (
            {"NIFTY": 25000.0, "BANKNIFTY": 55000.0, "SENSEX": 82000.0}[str(symbol).upper()],
            "test",
        ),
    )

    def resolve_option_tokens_window(*, symbol, **_kwargs):
        symbol = str(symbol).upper()
        option_resolution_calls.append(symbol)
        return [
            option_bases[symbol] + offset
            for offset in range(1, option_counts[symbol] + 1)
        ]

    monkeypatch.setattr(
        ws.kite_client,
        "resolve_option_tokens_window",
        resolve_option_tokens_window,
    )
    monkeypatch.setattr(
        ws.kite_client,
        "instruments_cached",
        lambda *args, **kwargs: [],
    )

    ws.reset_market_event_graph_observation_plan_state()
    requested_symbols = [
        "NIFTY",
        "BANKNIFTY",
        "SENSEX",
        *(
            symbol
            for symbol in registry.token_by_symbol
            if symbol not in {"NIFTY", "BANKNIFTY", "SENSEX"}
        ),
    ]
    tokens, resolution = engine.build_subscription_tokens(
        symbols=requested_symbols,
        max_tokens=123,
    )
    state = ws._observation_state_payload()

    assert option_resolution_calls == ["NIFTY", "BANKNIFTY", "SENSEX"]
    assert "RELIANCE" not in option_resolution_calls
    assert "HDFCBANK" not in option_resolution_calls
    assert {row["symbol"] for row in resolution} == {"NIFTY", "BANKNIFTY", "SENSEX"}

    assert len(state["production_tokens"]) == 73
    assert len(state["observation_tokens"]) == 51
    assert len(tokens) == 123
    assert len(state["final_union_tokens"]) == 123
    assert set(registry.all_tokens).issubset(set(tokens))
    assert set(registry.all_tokens).issubset(set(ws._UNDERLYING_TOKENS))
    assert {
        int(token): str(symbol).upper()
        for symbol, token in registry.token_by_symbol.items()
    }.items() <= ws._UNDERLYING_TOKEN_TO_SYMBOL.items()
    assert state["enabled"] is True
    assert state["verdict"] == "PASS_LIVE_SOURCE_PRESESSION_READINESS"
    assert state["configured_budget"] == 123

    # A failed union must not publish observation-only cash identities.
    original_merge = ws.build_observation_subscription_merge
    monkeypatch.setattr(
        ws,
        "build_observation_subscription_merge",
        lambda **_kwargs: {
            "ok": False,
            "tokens": [],
            "reason": "synthetic_blocked_merge",
            "missing_or_pruned_observation_tokens": list(registry.all_tokens),
        },
    )
    ws.reset_market_event_graph_observation_plan_state()
    engine.build_subscription_tokens(symbols=requested_symbols, max_tokens=123)
    cash_tokens = set(registry.all_tokens) - {int(registry.index_token)}
    assert cash_tokens.isdisjoint(ws._UNDERLYING_TOKENS)
    assert cash_tokens.isdisjoint(ws._UNDERLYING_TOKEN_TO_SYMBOL)
    assert all(token not in ws._TOKEN_TO_SYMBOL for token in cash_tokens)
    assert ws._observation_state_payload()["enabled"] is False

    # A nominally successful union with incomplete registry identity also fails closed.
    monkeypatch.setattr(ws, "build_observation_subscription_merge", original_merge)
    incomplete_registry = SimpleNamespace(
        all_tokens=registry.all_tokens,
        token_by_symbol={
            symbol: token
            for symbol, token in registry.token_by_symbol.items()
            if symbol != next(
                symbol
                for symbol in registry.token_by_symbol
                if symbol not in {"NIFTY", "BANKNIFTY", "SENSEX"}
            )
        },
        canonical_sha256=registry.canonical_sha256,
    )
    monkeypatch.setattr(ws, "load_observation_registry", lambda force=False: incomplete_registry)
    ws.reset_market_event_graph_observation_plan_state()
    engine.build_subscription_tokens(symbols=requested_symbols, max_tokens=123)
    assert cash_tokens.isdisjoint(ws._UNDERLYING_TOKENS)
    assert cash_tokens.isdisjoint(ws._UNDERLYING_TOKEN_TO_SYMBOL)
    assert ws._observation_state_payload()["enabled"] is False
    cash_only_symbols = [
        symbol
        for symbol in registry.token_by_symbol
        if symbol not in {"NIFTY", "BANKNIFTY", "SENSEX"}
    ]
    with pytest.raises(ValueError, match="at least one configured index option symbol"):
        engine.build_subscription_tokens(symbols=cash_only_symbols, max_tokens=123)
