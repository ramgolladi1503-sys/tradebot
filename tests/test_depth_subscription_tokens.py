from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from config import config as cfg
from core import depth_subscription_engine as sidecar
from core import kite_depth_ws as ws
from core.market_event_graph_live_launch_plan import build_launch_plan


def _count(values) -> int:
    return int(sum(1 for _ in list(values or [])))


@pytest.fixture(autouse=True)
def _isolate_observation_plan_state(monkeypatch):
    # The builder tests exercise the caller-supplied token path. A preceding
    # observer test may leave a process-wide governed union active, which has
    # higher precedence by design and changes this test's token universe.
    monkeypatch.setattr(ws, "_OBSERVATION_PLAN_STATE", {
        "enabled": False,
        "verdict": "DISABLED",
        "production_tokens": [],
        "observation_tokens": [],
        "overlap_tokens": [],
        "observation_exclusive_tokens": [],
        "final_union_tokens": [],
        "missing_observation_tokens": [],
        "configured_budget": None,
        "feed_session_id": "",
        "feed_epoch": 0,
        "reconnect_generation": 0,
        "plan_sha": "",
        "decision_epoch": None,
    })


def _setup_depth_window_mocks(monkeypatch):
    # These resolver tests assert the production index/option universe. The
    # governed MEG tests opt in explicitly and provide their own registry.
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", False, raising=False)
    expiry = date(2026, 3, 5)
    atm_by_symbol = {
        "NIFTY": 22000,
        "BANKNIFTY": 48000,
        "SENSEX": 83000,
    }
    step_by_symbol = {
        "NIFTY": 50,
        "BANKNIFTY": 100,
        "SENSEX": 100,
    }
    around_by_symbol = {
        "NIFTY": 6,
        "BANKNIFTY": 6,
        "SENSEX": 4,
    }
    index_tokens = {
        "NIFTY": 256265,
        "BANKNIFTY": 260105,
        "SENSEX": 265001,
    }

    token_map: dict[tuple[str, int, str], int] = {}
    token_meta: dict[int, dict] = {}
    exchange_data = {"NFO": [], "BFO": []}
    next_token = 100000

    for symbol in ("NIFTY", "BANKNIFTY", "SENSEX"):
        exchange = "BFO" if symbol == "SENSEX" else "NFO"
        segment = "BFO-OPT" if exchange == "BFO" else "NFO-OPT"
        step = step_by_symbol[symbol]
        atm = atm_by_symbol[symbol]
        for off in range(-12, 13):
            strike = atm + (off * step)
            for opt_type in ("CE", "PE"):
                token = next_token
                next_token += 1
                token_map[(symbol, strike, opt_type)] = token
                token_meta[token] = {
                    "symbol": symbol,
                    "strike": float(strike),
                    "instrument_type": opt_type,
                }
                exchange_data[exchange].append(
                    {
                        "segment": segment,
                        "name": symbol,
                        "expiry": expiry,
                        "strike": float(strike),
                        "instrument_token": token,
                        "instrument_type": opt_type,
                    }
                )

    calls: list[dict] = []

    def _fake_resolve_option_tokens_window(*, symbol, expiry=None, strikes_around=6, exchange="NFO", spot=None, **kwargs):
        symbol_u = str(symbol).upper()
        calls.append(
            {
                "symbol": symbol_u,
                "expiry": expiry,
                "strikes_around": int(strikes_around),
                "exchange": str(exchange),
                "spot": float(spot) if spot is not None else None,
                "extra_keys": sorted(kwargs.keys()),
            }
        )
        out: list[int] = []
        atm_strike = int(atm_by_symbol[symbol_u])
        step = int(step_by_symbol[symbol_u])
        for off in range(-int(strikes_around), int(strikes_around) + 1):
            strike = int(atm_strike) + (off * int(step))
            out.append(token_map[(symbol_u, strike, "CE")])
            out.append(token_map[(symbol_u, strike, "PE")])
        # Add a duplicate token to verify dedupe behavior.
        out.append(out[0])
        return out

    def _fake_instruments_cached(exchange=None, ttl_sec=3600):
        exchange_u = str(exchange or "").upper()
        if exchange_u in exchange_data:
            return list(exchange_data[exchange_u])
        return []

    monkeypatch.setattr(cfg, "DEPTH_SUBSCRIPTION_VALIDATE_TOKENS", False, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SUBSCRIPTION_STRIKES_AROUND", 6, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SUBSCRIPTION_STRIKES_AROUND_BY_SYMBOL", dict(around_by_symbol), raising=False)
    monkeypatch.setattr(cfg, "STRIKE_STEP_BY_SYMBOL", dict(step_by_symbol), raising=False)
    monkeypatch.setattr(cfg, "STRIKE_STEP", 50, raising=False)
    monkeypatch.setattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_ENABLE", False, raising=False)

    monkeypatch.setattr(ws, "get_sticky_tokens", lambda: set())
    monkeypatch.setattr(ws, "_underlying_ltp", lambda symbol: float(atm_by_symbol[str(symbol).upper()]))
    monkeypatch.setattr(ws.kite_client, "next_available_expiry", lambda symbol, exchange="NFO": expiry)
    monkeypatch.setattr(ws.kite_client, "resolve_index_token", lambda symbol: int(index_tokens[str(symbol).upper()]))
    monkeypatch.setattr(ws.kite_client, "resolve_option_tokens_window", _fake_resolve_option_tokens_window)
    monkeypatch.setattr(ws.kite_client, "instruments_cached", _fake_instruments_cached)

    return {
        "calls": calls,
        "token_meta": token_meta,
        "atm_by_symbol": atm_by_symbol,
        "index_tokens": index_tokens,
        "around_by_symbol": around_by_symbol,
        "step_by_symbol": step_by_symbol,
    }


def test_build_depth_subscription_tokens_uses_symbol_windows_and_steps(monkeypatch):
    ctx = _setup_depth_window_mocks(monkeypatch)

    tokens, _resolution = ws.build_depth_subscription_tokens(["NIFTY", "BANKNIFTY", "SENSEX"], max_tokens=200)

    assert _count(tokens) == _count(set(tokens))
    for token in ctx["index_tokens"].values():
        assert token in tokens

    token_meta = ctx["token_meta"]
    expected_strike_counts = {"NIFTY": 13, "BANKNIFTY": 13, "SENSEX": 9}
    for symbol, expected_count in expected_strike_counts.items():
        sym_tokens = [t for t in tokens if token_meta.get(t, {}).get("symbol") == symbol]
        strikes = sorted({int(token_meta[t]["strike"]) for t in sym_tokens})
        assert _count(strikes) == expected_count
        for strike in strikes:
            legs = {
                token_meta[t]["instrument_type"]
                for t in sym_tokens
                if int(token_meta[t]["strike"]) == int(strike)
            }
            assert legs == {"CE", "PE"}

    calls_by_symbol = {c["symbol"]: c for c in ctx["calls"]}
    assert calls_by_symbol["NIFTY"]["strikes_around"] == 6
    assert calls_by_symbol["BANKNIFTY"]["strikes_around"] == 6
    assert calls_by_symbol["SENSEX"]["strikes_around"] == 4
    assert calls_by_symbol["NIFTY"]["spot"] == 22000.0
    assert calls_by_symbol["BANKNIFTY"]["spot"] == 48000.0
    assert calls_by_symbol["SENSEX"]["spot"] == 83000.0
    assert calls_by_symbol["NIFTY"]["extra_keys"] == []
    assert calls_by_symbol["BANKNIFTY"]["extra_keys"] == []
    assert calls_by_symbol["SENSEX"]["extra_keys"] == []

    # Baseline token universe is approximately 73 without sticky tokens.
    assert 70 <= len(tokens) <= 80


def test_build_depth_subscription_tokens_budget_drops_farthest_options_first(monkeypatch):
    ctx = _setup_depth_window_mocks(monkeypatch)

    tokens, resolution = ws.build_depth_subscription_tokens(["NIFTY"], max_tokens=11)

    index_token = ctx["index_tokens"]["NIFTY"]
    assert index_token in tokens
    assert _count(tokens) == 11

    token_meta = ctx["token_meta"]
    option_tokens = [t for t in tokens if token_meta.get(t, {}).get("symbol") == "NIFTY"]
    kept_strikes = {int(token_meta[t]["strike"]) for t in option_tokens}
    atm = int(ctx["atm_by_symbol"]["NIFTY"])
    assert kept_strikes == {atm - 100, atm - 50, atm, atm + 50, atm + 100}
    assert resolution
    row = resolution[0]
    assert int(row.get("resolved_option_count") or 0) == 26
    assert int(row.get("option_count") or 0) == 10
    assert int(row.get("count") or 0) == 11
    assert row.get("tokens") == tokens
    assert ws._LAST_OPTION_COUNTS_BY_SYMBOL["NIFTY"] == 10
    assert row.get("option_drop_reason") == "subscription_budget_truncated"

def test_sticky_tokens_are_preserved_in_final_subscription(monkeypatch):
    ctx = _setup_depth_window_mocks(monkeypatch)
    sticky_token = 990001
    monkeypatch.setattr(ws, "get_sticky_tokens", lambda: {sticky_token})

    tokens, _resolution = ws.build_depth_subscription_tokens(["NIFTY"], max_tokens=3)

    assert sticky_token in tokens
    assert ctx["index_tokens"]["NIFTY"] in tokens
    assert _count(tokens) == 3


def test_option_tokens_under_min_are_preserved_as_degraded_coverage(monkeypatch):
    ctx = _setup_depth_window_mocks(monkeypatch)
    incidents: list[dict] = []
    monkeypatch.setattr(cfg, "MIN_OPTION_TOKENS", 100, raising=False)
    monkeypatch.setattr(
        ws,
        "_maybe_raise_option_token_incident",
        lambda **kwargs: incidents.append(dict(kwargs)),
    )
    expiry = ws.kite_client.next_available_expiry("NIFTY", exchange="NFO")
    raw = ws.kite_client.resolve_option_tokens_window(
        symbol="NIFTY",
        expiry=expiry,
        strikes_around=6,
        exchange="NFO",
        spot=22000.0,
    )
    raw_list = list(raw or [])
    assert raw_list

    direct_tokens, direct_resolution = ws.build_subscription_tokens(symbols=["NIFTY"], max_tokens=100)
    assert direct_resolution
    assert int(direct_resolution[0].get("resolved_option_count") or 0) > 0
    assert ctx["index_tokens"]["NIFTY"] in direct_tokens

    tokens, resolution = ws.build_depth_subscription_tokens(["NIFTY"], max_tokens=100)

    assert resolution
    row = resolution[0]
    assert int(row.get("resolved_option_count") or 0) > 0
    assert row.get("option_fail_reason") == "option_tokens_under_min"
    assert row.get("option_coverage_status") == "DEGRADED"
    assert row.get("option_coverage_reason") == "DEGRADED_OPTION_COVERAGE"
    assert int(row.get("resolved_option_count") or 0) > 0
    assert int(row.get("final_option_count") or 0) == int(row.get("resolved_option_count") or 0)
    assert ctx["index_tokens"]["NIFTY"] in tokens
    assert int(row.get("final_option_count") or 0) == len(
        [t for t in tokens if str(ctx["token_meta"].get(int(t), {}).get("symbol") or "").upper() == "NIFTY"]
    )
    assert incidents and incidents[-1]["symbol"] == "NIFTY"


def test_under_min_nonzero_option_universe_preserves_tokens_and_marks_degraded(monkeypatch):
    ctx = _setup_depth_window_mocks(monkeypatch)
    token_meta = ctx["token_meta"]
    atm = int(ctx["atm_by_symbol"]["NIFTY"])
    step = int(ctx["step_by_symbol"]["NIFTY"])
    target_strikes = {atm - step, atm, atm + step, atm + (2 * step)}
    option_tokens = sorted(
        int(tok)
        for tok, meta in token_meta.items()
        if str(meta.get("symbol") or "").upper() == "NIFTY" and int(float(meta.get("strike") or 0)) in target_strikes
    )
    assert _count(option_tokens) == 8

    monkeypatch.setattr(cfg, "MIN_OPTION_TOKENS", 12, raising=False)
    monkeypatch.setattr(ws.kite_client, "instruments_cached", lambda *_args, **_kwargs: [], raising=True)
    fake_resolver = lambda **_kwargs: list(option_tokens)
    monkeypatch.setattr(ws.kite_client, "resolve_option_tokens_window", fake_resolver)
    assert ws.kite_client.resolve_option_tokens_window is fake_resolver

    tokens, resolution = ws.build_depth_subscription_tokens(["NIFTY"], max_tokens=100)

    assert resolution
    row = resolution[0]
    assert row.get("option_fail_reason") == "option_tokens_under_min"
    assert row.get("option_coverage_status") == "DEGRADED"
    assert int(row.get("resolved_option_count") or 0) == 8
    assert int(row.get("final_option_count") or 0) == 8
    assert ctx["index_tokens"]["NIFTY"] in tokens


def test_zero_option_tokens_marks_zero_coverage_and_keeps_underlying(monkeypatch):
    ctx = _setup_depth_window_mocks(monkeypatch)
    monkeypatch.setattr(cfg, "MIN_OPTION_TOKENS", 12, raising=False)
    monkeypatch.setattr(ws.kite_client, "instruments_cached", lambda *_args, **_kwargs: [], raising=True)
    fake_resolver = lambda **_kwargs: []
    monkeypatch.setattr(ws.kite_client, "resolve_option_tokens_window", fake_resolver)
    assert ws.kite_client.resolve_option_tokens_window is fake_resolver

    tokens, resolution = ws.build_depth_subscription_tokens(["NIFTY"], max_tokens=100)

    assert resolution
    row = resolution[0]
    assert row.get("option_fail_reason") == "option_tokens_zero"
    assert row.get("option_coverage_status") == "ZERO"
    assert int(row.get("resolved_option_count") or 0) == 0
    assert int(row.get("final_option_count") or 0) == 0
    assert tokens == [ctx["index_tokens"]["NIFTY"]]


def test_production_resolution_counts_use_local_owner_map_after_global_map_change(monkeypatch):
    _setup_depth_window_mocks(monkeypatch)
    observation_tokens = list(range(8_000_000, 8_000_051))
    registry = SimpleNamespace(
        all_tokens=observation_tokens,
        token_by_symbol={f"OBS{i}": token for i, token in enumerate(observation_tokens)},
        canonical_sha256="registry-sha",
    )
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "MIN_OPTION_TOKENS", 12, raising=False)
    monkeypatch.setattr(
        cfg,
        "DEPTH_SUBSCRIPTION_STRIKES_AROUND_BY_SYMBOL",
        {"NIFTY": 3, "BANKNIFTY": 3, "SENSEX": 3},
        raising=False,
    )
    monkeypatch.setattr(ws, "_load_observation_registry_for_subscription", lambda: registry)

    original_merge = ws.build_observation_subscription_merge

    def _merge_after_global_symbol_map_change(**kwargs):
        result = original_merge(**kwargs)
        # Simulate launch-plan activation racing this build and replacing the
        # process-global merged map after the local production owners exist.
        ws._TOKEN_TO_SYMBOL = {}
        return result

    monkeypatch.setattr(ws, "build_observation_subscription_merge", _merge_after_global_symbol_map_change)

    # Exercise the canonical implementation, bypassing legacy/runtime adapters
    # that may replace the public entry point during test collection.
    tokens, resolution = ws._build_subscription_tokens_impl(
        symbols=["NIFTY", "BANKNIFTY", "SENSEX"],
        max_tokens=150,
    )

    rows = {row["symbol"]: row for row in resolution}
    assert len(tokens) <= 150
    assert set(observation_tokens).issubset(tokens)
    assert rows["NIFTY"]["final_option_count"] >= 12
    assert rows["BANKNIFTY"]["final_option_count"] >= 12
    assert rows["SENSEX"]["final_option_count"] >= 12
    for symbol, row in rows.items():
        option_tokens = [token for token in row["tokens"] if token != row["index_token"]]
        assert len(option_tokens) == row["final_option_count"]

    plan_state = ws._observation_state_payload()
    launch_plan = build_launch_plan(
        session_date="2026-10-01",
        production_tokens=plan_state["production_tokens"],
        production_resolution=resolution,
        sticky_tokens=[],
        observation_tokens=observation_tokens,
        budget=150,
        master_sha256="a" * 64,
        universe_sha256="registry-sha",
        configuration={"symbols": ["NIFTY", "BANKNIFTY", "SENSEX"]},
        broker_metadata_called=False,
    )
    assert launch_plan["ok"] is True
    assert launch_plan["production_option_count"] == sum(
        int(row["final_option_count"]) for row in resolution
    )
    assert set(launch_plan["production_tokens"]) == set(
        token for row in resolution for token in row["tokens"]
    )


def test_production_only_subscription_builder_excludes_observation_ids(monkeypatch):
    ctx = _setup_depth_window_mocks(monkeypatch)
    observation_tokens = list(range(8_100_000, 8_100_051))
    registry = SimpleNamespace(
        all_tokens=observation_tokens,
        token_by_symbol={f"OBS{i}": token for i, token in enumerate(observation_tokens)},
        canonical_sha256="registry-sha",
    )
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True, raising=False)
    monkeypatch.setattr(ws, "_load_observation_registry_for_subscription", lambda: registry)

    production_tokens, resolution = ws.build_production_subscription_tokens(
        ["NIFTY", "BANKNIFTY", "SENSEX"],
        max_tokens=150,
    )

    assert production_tokens
    assert not (set(production_tokens) & set(observation_tokens))
    assert set(production_tokens).issubset(
        {int(token) for row in resolution for token in row["tokens"]}
    )
    assert ctx["index_tokens"]["NIFTY"] in production_tokens


def test_meg_disabled_builder_caps_budget_and_keeps_replay_candidate_valid(monkeypatch):
    _setup_depth_window_mocks(monkeypatch)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SUBSCRIPTION_MAX_TOKENS", 123, raising=False)

    tokens, _resolution = sidecar.build_subscription_tokens(
        symbols=["NIFTY", "BANKNIFTY", "SENSEX"],
        max_tokens=150,
    )

    candidate = ws._DESIRED_SUBSCRIPTION_CANDIDATE
    replay_tokens, replay_reason = ws._validated_desired_subscription_tokens()
    assert len(tokens) <= 123
    assert candidate.configured_budget == 123
    assert candidate.complete is True
    assert replay_reason == "validated_desired_plan"
    assert replay_tokens == sorted(tokens)


def test_meg_builder_filters_cash_symbols_and_publishes_only_merged_identities(monkeypatch):
    ctx = _setup_depth_window_mocks(monkeypatch)
    cash_symbols = [f"CASH{i:02d}" for i in range(50)]
    cash_tokens = list(range(8_200_000, 8_200_050))
    registry_tokens = [ctx["index_tokens"]["NIFTY"], *cash_tokens]
    registry = SimpleNamespace(
        all_tokens=registry_tokens,
        token_by_symbol={
            "NIFTY": ctx["index_tokens"]["NIFTY"],
            **dict(zip(cash_symbols, cash_tokens)),
        },
        canonical_sha256="synthetic-registry-sha",
    )
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SUBSCRIPTION_MAX_TOKENS", 123, raising=False)
    monkeypatch.setattr(ws, "_load_observation_registry_for_subscription", lambda: registry)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", set(), raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {}, raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {}, raising=False)
    original_merge = ws.build_observation_subscription_merge

    symbols = ["NIFTY", "BANKNIFTY", "SENSEX", *cash_symbols]
    tokens, resolution = ws._build_subscription_tokens_impl(symbols, max_tokens=150)

    assert len(tokens) == 123
    assert len(set(tokens)) == 123
    assert {call["symbol"] for call in ctx["calls"]} == {"NIFTY", "BANKNIFTY", "SENSEX"}
    assert {row["symbol"] for row in resolution} == {"NIFTY", "BANKNIFTY", "SENSEX"}
    assert set(registry_tokens).issubset(ws._UNDERLYING_TOKENS)
    expected_identity = {int(token): symbol for symbol, token in registry.token_by_symbol.items()}
    assert all(ws._UNDERLYING_TOKEN_TO_SYMBOL[token] == symbol for token, symbol in expected_identity.items())
    assert all(ws._TOKEN_TO_SYMBOL[token] == symbol for token, symbol in expected_identity.items())

    # A failed observation merge must not claim cash-token identity or readiness.
    monkeypatch.setattr(
        ws,
        "build_observation_subscription_merge",
        lambda **_kwargs: {
            "ok": False,
            "tokens": [],
            "reason": "synthetic_blocked_merge",
            "missing_or_pruned_observation_tokens": registry_tokens,
        },
    )
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", set(), raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {}, raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {}, raising=False)
    ws._build_subscription_tokens_impl(symbols, max_tokens=123)
    assert set(cash_tokens).isdisjoint(ws._UNDERLYING_TOKENS)
    assert set(cash_tokens).isdisjoint(ws._UNDERLYING_TOKEN_TO_SYMBOL)
    assert all(token not in ws._TOKEN_TO_SYMBOL for token in cash_tokens)
    assert ws._observation_state_payload()["enabled"] is False

    # A successful token union with incomplete registry identity is also blocked.
    monkeypatch.setattr(ws, "build_observation_subscription_merge", original_merge)
    incomplete_registry = SimpleNamespace(
        all_tokens=registry_tokens,
        token_by_symbol={
            "NIFTY": ctx["index_tokens"]["NIFTY"],
            **dict(zip(cash_symbols[:-1], cash_tokens[:-1])),
        },
        canonical_sha256="incomplete-registry-sha",
    )
    monkeypatch.setattr(ws, "_load_observation_registry_for_subscription", lambda: incomplete_registry)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", set(), raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {}, raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {}, raising=False)
    ws._build_subscription_tokens_impl(symbols, max_tokens=123)
    assert set(cash_tokens).isdisjoint(ws._UNDERLYING_TOKENS)
    assert set(cash_tokens).isdisjoint(ws._UNDERLYING_TOKEN_TO_SYMBOL)
    assert ws._observation_state_payload()["enabled"] is False
    with pytest.raises(ValueError, match="at least one configured index option symbol"):
        ws._build_subscription_tokens_impl(cash_symbols, max_tokens=123)


def test_degraded_coverage_blocks_until_fresh_option_tick_proves_recovery(monkeypatch):
    ctx = _setup_depth_window_mocks(monkeypatch)
    token_meta = ctx["token_meta"]
    atm = int(ctx["atm_by_symbol"]["NIFTY"])
    step = int(ctx["step_by_symbol"]["NIFTY"])
    target_strikes = {atm - step, atm, atm + step, atm + (2 * step)}
    option_tokens = sorted(
        int(tok)
        for tok, meta in token_meta.items()
        if str(meta.get("symbol") or "").upper() == "NIFTY" and int(float(meta.get("strike") or 0)) in target_strikes
    )
    assert _count(option_tokens) == 8

    monkeypatch.setattr(cfg, "MIN_OPTION_TOKENS", 12, raising=False)
    monkeypatch.setattr(ws.kite_client, "instruments_cached", lambda *_args, **_kwargs: [], raising=True)
    monkeypatch.setattr(ws.kite_client, "resolve_option_tokens_window", lambda **_kwargs: list(option_tokens))
    monkeypatch.setattr(ws, "_LAST_MSG_TS_BY_TOKEN", {}, raising=False)

    tokens, _resolution = ws.build_depth_subscription_tokens(["NIFTY"], max_tokens=100)

    import core.blocker_lifecycle as bl

    bl.reset_blocker_registries()
    option_state = ws._option_runtime_state(
        now_epoch=200.0,
        tokens=tokens,
        expected_counts_by_symbol={"NIFTY": 8},
        min_required_by_symbol={"NIFTY": 12},
        ws_connected=True,
    )
    assert option_state["feed_block_reason_by_symbol"]["NIFTY"] == "NO_LIVE_OPTION_FEED"

    # This test's recovery assertion requires authoritative applied option
    # ownership; resolver output alone is only a proposal.
    identities = {
        token: {
            "symbol": "NIFTY",
            "instrument_type": token_meta[token]["instrument_type"],
            "exchange": "NFO",
            "expiry": "2026-03-05",
            "strike": token_meta[token]["strike"],
        }
        for token in option_tokens
    }
    generation = ws._current_socket_generation()
    ws._OPTION_OWNERSHIP_BOOTSTRAP_GENERATION = generation
    ws._invalidate_applied_option_ownership(
        "test_reset", socket_generation=generation
    )
    revision = ws.record_desired_option_contracts(
        identities, expected_tokens=option_tokens, source="test_instrument_master"
    )
    base, invalidated = ws._begin_applied_option_mutation(
        "test_local_subscription", affected_tokens=option_tokens
    )
    assert ws._commit_applied_option_ownership(
        socket_generation=generation,
        desired_revision=revision,
        base_snapshot=base,
        invalidated_revision=invalidated.revision,
        confirmed_tokens=option_tokens,
        subscribe_tokens=option_tokens,
        fresh_socket=True,
        provenance="test_local_api_success",
    )
    monkeypatch.setattr(ws, "_LAST_MSG_TS_BY_TOKEN", {int(option_tokens[0]): 199.5}, raising=False)
    option_state = ws._option_runtime_state(
        now_epoch=200.0,
        tokens=tokens,
        expected_counts_by_symbol={"NIFTY": 8},
        min_required_by_symbol={"NIFTY": 12},
        ws_connected=True,
    )
    assert option_state["feed_block_reason_by_symbol"]["NIFTY"] == "OK"


def test_build_depth_subscription_tokens_prunes_stale_options_but_keeps_fresh_and_underlying(monkeypatch):
    ctx = _setup_depth_window_mocks(monkeypatch)
    token_meta = ctx["token_meta"]
    atm = int(ctx["atm_by_symbol"]["NIFTY"])

    monkeypatch.setattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MAX_AGE_SEC", 2.5, raising=False)
    # This test expects immediate pruning once a token is stale beyond max_age_sec.
    monkeypatch.setattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_CONSECUTIVE_STALE_WINDOWS", 1, raising=False)
    monkeypatch.setattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_REQUIRE_SESSION_TICK", True, raising=False)
    monkeypatch.setattr(ws, "now_utc_epoch", lambda: 200.0)
    monkeypatch.setattr(ws, "_DEPTH_WS_START_EPOCH", 100.0, raising=False)
    monkeypatch.setattr(ws, "_SYMBOL_LAST_OPTION_TICK_TS", {"NIFTY": 150.0}, raising=False)

    def _fake_latest_tick_rows_db(tokens):
        rows = {}
        for token in list(tokens or []):
            meta = token_meta.get(int(token)) or {}
            if str(meta.get("symbol") or "").upper() != "NIFTY":
                continue
            strike = int(float(meta.get("strike") or 0))
            age_sec = 1.0 if abs(strike - atm) <= 150 else 20.0
            rows[int(token)] = {"ts_epoch": 200.0 - age_sec, "ltp": 100.0}
        return rows

    monkeypatch.setattr(ws, "get_latest_tick_rows_db", _fake_latest_tick_rows_db)

    tokens, resolution = ws.build_depth_subscription_tokens(["NIFTY"], max_tokens=200)

    index_token = ctx["index_tokens"]["NIFTY"]
    assert index_token in tokens

    sticky_tokens = {990001}
    monkeypatch.setattr(ws, "get_sticky_tokens", lambda: set(sticky_tokens))
    # Rebuild once more to prove sticky tokens survive the prune path as well.
    tokens, resolution = ws.build_depth_subscription_tokens(["NIFTY"], max_tokens=200)

    assert 990001 in tokens
    option_tokens = [t for t in tokens if token_meta.get(t, {}).get("symbol") == "NIFTY"]
    kept_strikes = {int(token_meta[t]["strike"]) for t in option_tokens}
    assert all(abs(strike - atm) <= 150 for strike in kept_strikes)
    assert _count(option_tokens) == 14
    row = resolution[0]
    assert int(row.get("stale_option_pruned_count") or 0) > 0
    assert row.get("option_drop_reason") == "stale_option_subscription_pruned"
    assert row.get("option_fail_reason") in (None, "")
    assert row.get("stale_option_prune_enabled") is True
    assert float(row.get("stale_option_prune_max_age_sec") or 0.0) == 2.5
    assert row.get("stale_option_prune_require_session_tick") is True
    assert int((row.get("stale_option_session_tick_skipped_count_by_symbol") or {}).get("NIFTY") or 0) == 0


def test_build_depth_subscription_tokens_requires_session_tick_before_pruning_stale_options(monkeypatch):
    ctx = _setup_depth_window_mocks(monkeypatch)
    token_meta = ctx["token_meta"]
    atm = int(ctx["atm_by_symbol"]["NIFTY"])

    monkeypatch.setattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MAX_AGE_SEC", 2.5, raising=False)
    monkeypatch.setattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_REQUIRE_SESSION_TICK", True, raising=False)
    monkeypatch.setattr(ws, "now_utc_epoch", lambda: 200.0)
    monkeypatch.setattr(ws, "_DEPTH_WS_START_EPOCH", 100.0, raising=False)
    monkeypatch.setattr(ws, "_SYMBOL_LAST_OPTION_TICK_TS", {}, raising=False)

    def _fake_latest_tick_rows_db(tokens):
        rows = {}
        for token in list(tokens or []):
            meta = token_meta.get(int(token)) or {}
            if str(meta.get("symbol") or "").upper() != "NIFTY":
                continue
            strike = int(float(meta.get("strike") or 0))
            age_sec = 1.0 if abs(strike - atm) <= 150 else 20.0
            rows[int(token)] = {"ts_epoch": 200.0 - age_sec, "ltp": 100.0}
        return rows

    monkeypatch.setattr(ws, "get_latest_tick_rows_db", _fake_latest_tick_rows_db)

    tokens, resolution = ws.build_depth_subscription_tokens(["NIFTY"], max_tokens=200)

    index_token = ctx["index_tokens"]["NIFTY"]
    assert index_token in tokens
    option_tokens = [t for t in tokens if token_meta.get(t, {}).get("symbol") == "NIFTY"]
    kept_strikes = {int(token_meta[t]["strike"]) for t in option_tokens}
    assert kept_strikes == {atm + (off * 50) for off in range(-6, 7)}
    assert _count(option_tokens) == 26
    row = resolution[0]
    assert int(row.get("stale_option_pruned_count") or 0) == 0
    assert row.get("option_drop_reason") in (None, "")
    assert row.get("stale_option_prune_enabled") is True
    assert row.get("stale_option_prune_require_session_tick") is True
    skipped = row.get("stale_option_session_tick_skipped_count_by_symbol") or {}
    assert int(skipped.get("NIFTY") or 0) == 26


def test_prune_stale_option_subscription_tokens_preserves_symbol_floor(monkeypatch):
    ctx = _setup_depth_window_mocks(monkeypatch)
    token_meta = ctx["token_meta"]
    nifty_options = [
        int(t) for t, meta in token_meta.items()
        if str(meta.get("symbol") or "").upper() == "NIFTY"
    ][:10]

    monkeypatch.setattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MAX_AGE_SEC", 2.5, raising=False)
    monkeypatch.setattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_CONSECUTIVE_STALE_WINDOWS", 1, raising=False)
    monkeypatch.setattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_REQUIRE_SESSION_TICK", False, raising=False)
    monkeypatch.setattr(ws, "now_utc_epoch", lambda: 200.0)
    monkeypatch.setattr(ws, "_DEPTH_WS_START_EPOCH", 100.0, raising=False)
    monkeypatch.setattr(
        ws,
        "get_latest_tick_rows_db",
        lambda tokens: {int(t): {"ts_epoch": 180.0, "ltp": 100.0} for t in tokens},
    )

    rank_by_token = {int(t): (abs(i - 5), 1, float(i), 0, int(t)) for i, t in enumerate(nifty_options)}
    token_to_symbol = {int(t): "NIFTY" for t in nifty_options}

    min_required = {"NIFTY": 4}
    kept_tokens, meta = ws._prune_stale_option_subscription_tokens(
        tokens=nifty_options,
        option_rank_by_token=rank_by_token,
        token_to_symbol=token_to_symbol,
        min_required_by_symbol=min_required,
    )

    assert len(kept_tokens) == 4
    assert meta["pruned_count"] == 6
    assert meta["kept_count"] == 4
    assert meta["protected_stale_by_symbol"]["NIFTY"] == 4


def test_maybe_refresh_stale_option_subscription_universe_applies_delta(monkeypatch):
    ctx = _setup_depth_window_mocks(monkeypatch)
    token_meta = ctx["token_meta"]
    nifty_options = [
        int(t) for t, meta in token_meta.items()
        if str(meta.get("symbol") or "").upper() == "NIFTY"
    ]
    current_tokens = nifty_options[:10]
    monkeypatch.setattr(ws, "_LAST_TOKENS", list(current_tokens), raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {int(t): "NIFTY" for t in nifty_options}, raising=False)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    contracts = {
        int(t): ws.OptionContractIdentity(
            token=int(t),
            symbol="NIFTY",
            instrument_type=str(token_meta[t].get("instrument_type") or "CE"),
            exchange="NFO",
            expiry="2026-03-05",
            strike=float(token_meta[t].get("strike") or 22000),
        )
        for t in current_tokens
    }
    snap = ws.AppliedOptionOwnershipSnapshot(
        state="KNOWN",
        socket_generation=ws._current_socket_generation(),
        revision=1,
        provenance="test",
        contracts=contracts,
    )
    monkeypatch.setattr(ws, "get_applied_option_ownership_snapshot", lambda: snap)

    now_epoch = 1000.0
    tick_ts = {int(t): (now_epoch - 1.0 if i < 2 else now_epoch - 50.0) for i, t in enumerate(current_tokens)}
    monkeypatch.setattr(ws, "_LAST_MSG_TS_BY_TOKEN", tick_ts, raising=False)
    monkeypatch.setattr(ws, "_can_mutate_ws_subscriptions", lambda **kwargs: (True, "ok", {}))
    desired_tokens = nifty_options[2:12]
    monkeypatch.setattr(
        ws,
        "build_subscription_tokens",
        lambda symbols: (list(desired_tokens), [{"symbol": "NIFTY", "tokens": list(desired_tokens)}]),
    )
    monkeypatch.setattr(
        ws,
        "_should_mutate_stale_option_symbol_subscription",
        lambda **kwargs: (True, {"mutation_window_count_by_symbol": 3}, {}),
    )

    refresh_state = {"last_refresh_epoch": 0.0, "last_freshness_refresh_epoch": 0.0}
    changed, payload = ws._maybe_refresh_stale_option_subscription_universe(
        now_epoch=now_epoch,
        refresh_state=refresh_state,
    )

    assert changed is True
    assert payload["freshness_urgent"] is True
    assert payload["reason"] == "freshness_drift"
    assert len(payload["subscribe_tokens"]) > 0 or len(payload["unsubscribe_tokens"]) > 0


def test_build_depth_subscription_tokens_passes_symbol_minimums_into_prune(monkeypatch):
    ctx = _setup_depth_window_mocks(monkeypatch)
    captured_min_required: list[dict] = []
    orig_prune = ws._prune_stale_option_subscription_tokens

    def _spy_prune(*args, **kwargs):
        captured_min_required.append(dict(kwargs.get("min_required_by_symbol") or {}))
        return orig_prune(*args, **kwargs)

    monkeypatch.setattr(ws, "_prune_stale_option_subscription_tokens", _spy_prune)
    monkeypatch.setattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MIN_REQUIRED_FLOOR", 14, raising=False)
    monkeypatch.setattr(cfg, "MIN_OPTION_TOKENS", 12, raising=False)

    tokens, resolution = ws.build_depth_subscription_tokens(["NIFTY"], max_tokens=100)

    assert len(captured_min_required) == 1
    assert captured_min_required[0].get("NIFTY") >= 14


def test_maybe_refresh_stale_option_subscription_universe_triggers_freshness_refresh(monkeypatch):
    ctx = _setup_depth_window_mocks(monkeypatch)
    token_meta = ctx["token_meta"]
    nifty_options = [
        int(t) for t, meta in token_meta.items()
        if str(meta.get("symbol") or "").upper() == "NIFTY"
    ][:10]

    monkeypatch.setattr(ws, "_LAST_TOKENS", list(nifty_options), raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {int(t): "NIFTY" for t in nifty_options}, raising=False)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    contracts2 = {
        int(t): ws.OptionContractIdentity(
            token=int(t),
            symbol="NIFTY",
            instrument_type=str(token_meta[t].get("instrument_type") or "CE"),
            exchange="NFO",
            expiry="2026-03-05",
            strike=float(token_meta[t].get("strike") or 22000),
        )
        for t in nifty_options
    }
    snap2 = ws.AppliedOptionOwnershipSnapshot(
        state="KNOWN",
        socket_generation=ws._current_socket_generation(),
        revision=1,
        provenance="test",
        contracts=contracts2,
    )
    monkeypatch.setattr(ws, "get_applied_option_ownership_snapshot", lambda: snap2)

    now_epoch = 1000.0
    tick_ts = {int(t): now_epoch - 50.0 for t in nifty_options}
    monkeypatch.setattr(ws, "_LAST_MSG_TS_BY_TOKEN", tick_ts, raising=False)
    monkeypatch.setattr(ws, "_can_mutate_ws_subscriptions", lambda **kwargs: (True, "ok", {}))
    monkeypatch.setattr(
        ws,
        "build_subscription_tokens",
        lambda symbols: (list(nifty_options), [{"symbol": "NIFTY", "tokens": list(nifty_options)}]),
    )
    monkeypatch.setattr(
        ws,
        "_should_mutate_stale_option_symbol_subscription",
        lambda **kwargs: (True, {"mutation_window_count_by_symbol": 3}, {}),
    )

    refresh_state = {"last_refresh_epoch": 0.0, "last_freshness_refresh_epoch": 0.0}
    changed, payload = ws._maybe_refresh_stale_option_subscription_universe(
        now_epoch=now_epoch,
        refresh_state=refresh_state,
    )

    assert changed is True
    assert payload["refresh_mode"] == "symbol_freshness_refresh"
    assert payload["subscribe_tokens"] == []
    assert payload["unsubscribe_tokens"] == []
    assert payload["refresh_tokens"] == sorted(nifty_options)


def test_maybe_refresh_stale_option_subscription_universe_refreshes_only_stale_symbol_family(monkeypatch):
    ctx = _setup_depth_window_mocks(monkeypatch)
    token_meta = ctx["token_meta"]
    nifty_options = [
        int(t) for t, meta in token_meta.items()
        if str(meta.get("symbol") or "").upper() == "NIFTY"
    ][:10]
    banknifty_options = [
        int(t) for t, meta in token_meta.items()
        if str(meta.get("symbol") or "").upper() == "BANKNIFTY"
    ][:10]

    all_current = nifty_options + banknifty_options
    tok_to_sym = {int(t): "NIFTY" for t in nifty_options}
    tok_to_sym.update({int(t): "BANKNIFTY" for t in banknifty_options})

    contracts3 = {}
    for t in nifty_options:
        contracts3[int(t)] = ws.OptionContractIdentity(
            token=int(t),
            symbol="NIFTY",
            instrument_type=str(token_meta[t].get("instrument_type") or "CE"),
            exchange="NFO",
            expiry="2026-03-05",
            strike=float(token_meta[t].get("strike") or 22000),
        )
    for t in banknifty_options:
        contracts3[int(t)] = ws.OptionContractIdentity(
            token=int(t),
            symbol="BANKNIFTY",
            instrument_type=str(token_meta[t].get("instrument_type") or "CE"),
            exchange="NFO",
            expiry="2026-03-05",
            strike=float(token_meta[t].get("strike") or 48000),
        )
    snap3 = ws.AppliedOptionOwnershipSnapshot(
        state="KNOWN",
        socket_generation=ws._current_socket_generation(),
        revision=1,
        provenance="test",
        contracts=contracts3,
    )

    monkeypatch.setattr(ws, "_LAST_TOKENS", list(all_current), raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", tok_to_sym, raising=False)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(ws, "get_applied_option_ownership_snapshot", lambda: snap3)

    now_epoch = 1000.0
    tick_ts = {}
    for t in nifty_options:
        tick_ts[int(t)] = now_epoch - 45.0
    for t in banknifty_options:
        tick_ts[int(t)] = now_epoch - 0.5
    monkeypatch.setattr(ws, "_LAST_MSG_TS_BY_TOKEN", tick_ts, raising=False)
    monkeypatch.setattr(ws, "_can_mutate_ws_subscriptions", lambda **kwargs: (True, "ok", {}))

    new_nifty = [
        int(t) for t, meta in token_meta.items()
        if str(meta.get("symbol") or "").upper() == "NIFTY"
    ][2:12]
    all_desired = new_nifty + banknifty_options

    monkeypatch.setattr(
        ws,
        "build_subscription_tokens",
        lambda symbols: (
            list(all_desired),
            [
                {"symbol": "NIFTY", "tokens": list(new_nifty)},
                {"symbol": "BANKNIFTY", "tokens": list(banknifty_options)},
            ],
        ),
    )

    def _fake_should_mutate(**kwargs):
        sym = kwargs.get("symbol")
        if sym == "NIFTY":
            return True, {"mutation_window_count_by_symbol": 3}, {}
        return False, {"mutation_window_count_by_symbol": 0}, {}

    monkeypatch.setattr(ws, "_should_mutate_stale_option_symbol_subscription", _fake_should_mutate)

    refresh_state = {"last_refresh_epoch": 0.0, "last_freshness_refresh_epoch": 0.0}
    changed, payload = ws._maybe_refresh_stale_option_subscription_universe(
        now_epoch=now_epoch,
        refresh_state=refresh_state,
    )

    assert changed is True
    assert payload["mutation_eligible_symbols"] == ["NIFTY"]
    assert "BANKNIFTY" not in payload["mutation_eligible_symbols"]

    for tok in payload["subscribe_tokens"] + payload["unsubscribe_tokens"]:
        assert tok_to_sym.get(int(tok)) == "NIFTY" or tok in new_nifty
        assert tok not in banknifty_options


def test_option_expiry_unavailable_sets_fail_reason(monkeypatch):
    ctx = _setup_depth_window_mocks(monkeypatch)
    incidents: list[dict] = []
    monkeypatch.setattr(ws.kite_client, "next_available_expiry", lambda symbol, exchange="NFO": None)
    monkeypatch.setattr(
        ws,
        "_maybe_raise_option_token_incident",
        lambda **kwargs: incidents.append(dict(kwargs)),
    )

    tokens, resolution = ws.build_depth_subscription_tokens(["NIFTY"], max_tokens=100)

    assert tokens == [ctx["index_tokens"]["NIFTY"]]
    assert resolution
    row = resolution[0]
    assert row.get("option_fail_reason") == "expiry_unavailable"
    assert int(row.get("option_count") or 0) == 0
    assert incidents and incidents[-1].get("fail_reason") == "expiry_unavailable"


def test_validate_tokens_keeps_resolved_bfo_option_tokens(monkeypatch):
    ctx = _setup_depth_window_mocks(monkeypatch)
    monkeypatch.setattr(cfg, "DEPTH_SUBSCRIPTION_VALIDATE_TOKENS", True, raising=False)

    nfo_known_rows: list[dict] = []
    for token, meta in ctx["token_meta"].items():
        if str(meta.get("symbol") or "").upper() != "SENSEX":
            nfo_known_rows.append({"instrument_token": int(token)})
    for symbol, token in ctx["index_tokens"].items():
        if str(symbol).upper() != "SENSEX":
            nfo_known_rows.append({"instrument_token": int(token)})

    def _nfo_only_instruments_cached(exchange=None, ttl_sec=3600):
        if str(exchange or "").upper() == "NFO":
            return list(nfo_known_rows)
        return []

    monkeypatch.setattr(ws.kite_client, "instruments_cached", _nfo_only_instruments_cached)

    tokens, resolution = ws.build_depth_subscription_tokens(["SENSEX"], max_tokens=200)

    token_set = set(tokens)
    sensex_option_tokens = [
        int(tok)
        for tok, meta in ctx["token_meta"].items()
        if str(meta.get("symbol") or "").upper() == "SENSEX"
    ]
    kept_sensex_options = [tok for tok in sensex_option_tokens if tok in token_set]

    # Even with known_tokens containing only NFO rows, resolver-confirmed BFO option tokens
    # must be preserved when token validation runs.
    assert _count(kept_sensex_options) >= 18
    assert resolution
    assert str(resolution[0].get("symbol") or "").upper() == "SENSEX"
    assert int(resolution[0].get("option_count") or 0) >= 18


def test_build_depth_subscription_tokens_fallback_preserves_symbols_argument(monkeypatch):
    calls = []

    def _broken_keyword_only(*, symbols=None, max_tokens=None):
        raise TypeError("keyword path broken")

    def _positional_symbols(symbols):
        calls.append(list(symbols or []))
        return [101], [{"symbol": "NIFTY", "count": 1}]

    monkeypatch.setattr(ws, "build_subscription_tokens", _broken_keyword_only)
    monkeypatch.setattr(ws, "build_tokens", _positional_symbols, raising=False)

    tokens, resolution = ws.build_depth_subscription_tokens(["NIFTY"], max_tokens=10)

    assert calls == [["NIFTY"]]
    assert tokens == [101]
    assert resolution == [{"symbol": "NIFTY", "count": 1}]


def test_record_desired_subscription_candidate_clamps_budget_to_governed_budget(monkeypatch):
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", False, raising=False)
    monkeypatch.setattr(ws, "_UNDERLYING_TOKENS", {256265})
    monkeypatch.setattr(ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {256265: "NIFTY"})
    raw_tokens = [256265, 1001, 1002]
    option_tokens = [1001, 1002]
    contracts = {
        1001: {"symbol": "NIFTY", "instrument_type": "CE", "strike": 22000, "exchange": "NFO", "expiry": "2026-03-05"},
        1002: {"symbol": "NIFTY", "instrument_type": "PE", "strike": 22000, "exchange": "NFO", "expiry": "2026-03-05"},
    }
    ws.record_desired_option_contracts(
        contracts,
        expected_tokens=option_tokens,
        source="test_budget_clamp",
    )
    # Pass configured_budget=150 exceeding governed budget (123)
    rev = ws.record_desired_subscription_candidate(
        raw_tokens,
        option_tokens=option_tokens,
        configured_budget=150,
        source="test_budget_clamp",
        observation_required=False,
    )
    assert rev > 0
    candidate = ws._DESIRED_SUBSCRIPTION_CANDIDATE
    assert candidate.complete is True
    assert candidate.configured_budget == 123
    assert set(candidate.tokens) == set(raw_tokens)
    validated, reason = ws._validated_desired_subscription_tokens()
    assert validated == sorted(raw_tokens)
    assert reason == "validated_desired_plan"


def test_wi06_gate1_validate_tokens_drops_phantom_option_tokens(monkeypatch):
    """GATE-WI06-1: Option tokens not in known_tokens are dropped and pruned from option_rank_by_token."""
    ctx = _setup_depth_window_mocks(monkeypatch)
    monkeypatch.setattr(cfg, "DEPTH_SUBSCRIPTION_VALIDATE_TOKENS", True, raising=False)

    # Populate known_tokens for NFO with all NIFTY tokens except phantom token 999999
    known_rows = []
    for token, meta in ctx["token_meta"].items():
        if str(meta.get("symbol") or "").upper() == "NIFTY":
            known_rows.append({"instrument_token": int(token)})
    for symbol, token in ctx["index_tokens"].items():
        if str(symbol).upper() == "NIFTY":
            known_rows.append({"instrument_token": int(token)})

    def _instruments_cached(exchange=None, ttl_sec=3600):
        if str(exchange or "").upper() == "NFO":
            return list(known_rows)
        return []

    monkeypatch.setattr(ws.kite_client, "instruments_cached", _instruments_cached)

    # Inject phantom option token 999999 into option resolver output
    orig_resolve = ws.kite_client.resolve_option_tokens_window

    def _fake_resolve(**kwargs):
        toks = orig_resolve(**kwargs)
        return toks + [999999]

    monkeypatch.setattr(ws.kite_client, "resolve_option_tokens_window", _fake_resolve)

    tokens, resolution = ws.build_depth_subscription_tokens(["NIFTY"], max_tokens=200)

    # 999999 must NOT be in subscribed tokens
    assert 999999 not in tokens


def test_wi06_gate2_validate_tokens_preserves_underlying_and_open_trades(monkeypatch):
    """GATE-WI06-2: Underlying tokens and active open trades are preserved even if not in options universe."""
    ctx = _setup_depth_window_mocks(monkeypatch)
    monkeypatch.setattr(cfg, "DEPTH_SUBSCRIPTION_VALIDATE_TOKENS", True, raising=False)

    index_token = ctx["index_tokens"]["NIFTY"]
    active_trade_token = 888888
    monkeypatch.setattr(ws, "get_sticky_tokens", lambda: {active_trade_token})

    monkeypatch.setattr(
        ws.kite_client,
        "instruments_cached",
        lambda exchange=None, ttl_sec=3600: [{"instrument_token": int(index_token)}],
    )

    tokens, resolution = ws.build_depth_subscription_tokens(
        ["NIFTY"],
        max_tokens=200,
    )

    # Both index token and active open trade token must be preserved
    assert index_token in tokens
    assert active_trade_token in tokens


def test_wi06_gate3_stale_local_cache_bypassed_for_broker_fetch(tmp_path, monkeypatch):
    """GATE-WI06-3: Local cache older than current IST date is marked stale and bypassed for broker fetch."""
    import os
    import json
    import core.option_token_resolver as resolver
    from datetime import datetime, timedelta
    from core.time_utils import IST_TZ

    fake_data_dir = tmp_path / "data"
    fake_data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(resolver, "data_root", lambda: fake_data_dir)

    stale_cache_file = fake_data_dir / "kite_instruments.json"
    stale_cache_file.write_text(json.dumps({"NFO": [{"instrument_token": 111111}]}))

    # Set mtime to 2 days ago
    past_time = (datetime.now(tz=IST_TZ) - timedelta(days=2)).timestamp()
    os.utime(str(stale_cache_file), (past_time, past_time))

    broker_called = []

    def _fake_broker(exchange, ttl_sec=3600):
        broker_called.append(exchange)
        return [{"instrument_token": 222222}]

    monkeypatch.setattr(resolver.kite_client, "instruments_cached", _fake_broker)

    inst, source = resolver._load_instruments("NFO")
    assert source == "kite_client_cache"
    assert inst == [{"instrument_token": 222222}]
    assert broker_called == ["NFO"]


def test_wi06_gate4_stale_cache_broker_unreachable_fails_closed(tmp_path, monkeypatch):
    """GATE-WI06-4: When local cache is stale and broker is unreachable, fail closed with TokenCoverageError."""
    import os
    import json
    import core.option_token_resolver as resolver
    from datetime import datetime, timedelta
    from core.time_utils import IST_TZ

    fake_data_dir = tmp_path / "data"
    fake_data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(resolver, "data_root", lambda: fake_data_dir)

    stale_cache_file = fake_data_dir / "kite_instruments.json"
    stale_cache_file.write_text(json.dumps({"NFO": [{"instrument_token": 111111}]}))

    past_time = (datetime.now(tz=IST_TZ) - timedelta(days=3)).timestamp()
    os.utime(str(stale_cache_file), (past_time, past_time))

    # Broker is unreachable or returns empty
    monkeypatch.setattr(
        resolver.kite_client,
        "instruments_cached",
        lambda exchange, ttl_sec=3600: [],
    )

    with pytest.raises(resolver.TokenCoverageError) as exc_info:
        resolver._load_instruments("NFO")

    assert exc_info.value.code == "CACHE_STALE_AND_BROKER_UNREACHABLE"


def test_wi06_gate5_temporal_alignment_ist_date(monkeypatch):
    """GATE-WI06-5: Instrument caching and option token resolving strictly use canonical IST date."""
    from core.time_utils import now_ist
    import core.option_token_resolver as resolver

    ist_today = now_ist().date()
    assert resolver._trading_date() == ist_today
