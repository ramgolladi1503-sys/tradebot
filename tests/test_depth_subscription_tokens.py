from __future__ import annotations

from datetime import date

from config import config as cfg
from core import kite_depth_ws as ws


def _count(values) -> int:
    return int(sum(1 for _ in list(values or [])))


def _setup_depth_window_mocks(monkeypatch):
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
    monkeypatch.setattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MAX_AGE_SEC", 2.5, raising=False)
    monkeypatch.setattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_REQUIRE_SESSION_TICK", True, raising=False)
    monkeypatch.setattr(ws, "now_utc_epoch", lambda: 200.0)
    monkeypatch.setattr(ws, "_DEPTH_WS_START_EPOCH", 100.0, raising=False)
    monkeypatch.setattr(ws, "_SYMBOL_LAST_OPTION_TICK_TS", {"NIFTY": 150.0}, raising=False)

    tokens = [1, 11, 12, 13, 14, 15, 16]
    option_rank_by_token = {
        11: (0.91, 1, 0.2, 2, 11),
        12: (0.82, 1, 0.3, 2, 12),
        13: (0.73, 1, 0.4, 2, 13),
        14: (0.64, 1, 0.5, 2, 14),
        15: (0.55, 1, 0.6, 2, 15),
        16: (0.46, 1, 0.7, 2, 16),
    }
    token_to_symbol = {1: "NIFTY", 11: "NIFTY", 12: "NIFTY", 13: "NIFTY", 14: "NIFTY", 15: "NIFTY", 16: "NIFTY"}

    def _fake_latest_tick_rows_db(option_tokens):
        rows = {}
        for token in list(option_tokens or []):
            rows[int(token)] = {
                "ts_epoch": 199.0 if int(token) == 11 else 180.0,
                "ltp": 100.0,
            }
        return rows

    monkeypatch.setattr(ws, "get_latest_tick_rows_db", _fake_latest_tick_rows_db)

    retained, meta = ws._prune_stale_option_subscription_tokens(
        tokens=tokens,
        option_rank_by_token=option_rank_by_token,
        token_to_symbol=token_to_symbol,
        min_required_by_symbol={"NIFTY": 4},
    )

    assert 1 in retained
    assert _count([tok for tok in retained if tok != 1]) == 4
    assert _count(retained) == 5
    assert meta["pruned_count"] == 2
    assert meta["pruned_by_symbol"] == {"NIFTY": 2}
    assert meta["protected_stale_by_symbol"] == {"NIFTY": 3}
    assert meta["min_required_blocked_by_symbol"] == {}
    assert meta["min_required_by_symbol"] == {"NIFTY": 4}
    assert _count(meta["stale_samples"]) <= 10


def test_maybe_refresh_stale_option_subscription_universe_applies_delta(monkeypatch):
    refresh_state = {"last_refresh_epoch": 0.0}

    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [101, 102], raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {101: "NIFTY", 102: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_normalize_positive_tokens", lambda values: [int(v) for v in values if int(v) > 0])
    monkeypatch.setattr(
        ws,
        "get_latest_tick_rows_db",
        lambda tokens: {int(tok): {"ts_epoch": 199.0, "ltp": 100.0} for tok in list(tokens or [])},
    )
    monkeypatch.setattr(
        ws,
        "build_subscription_tokens",
        lambda symbols: ([101], [{"symbol": "NIFTY", "stale_option_pruned_count": 1, "tokens": [101, 102]}]),
    )

    should_refresh, payload = ws._maybe_refresh_stale_option_subscription_universe(
        now_epoch=200.0,
        refresh_state=refresh_state,
    )

    assert should_refresh is True
    assert refresh_state["last_refresh_epoch"] == 200.0
    assert payload["refresh_mode"] == "delta"
    assert payload["subscribe_tokens"] == []
    assert payload["unsubscribe_tokens"] == [102]
    assert payload["desired_count"] == 1
    assert payload["previous_count"] == 2
    assert payload["force_resubscribe_current"] is False


def test_build_depth_subscription_tokens_passes_symbol_minimums_into_prune(monkeypatch):
    ctx = _setup_depth_window_mocks(monkeypatch)
    token_meta = ctx["token_meta"]
    atm = int(ctx["atm_by_symbol"]["NIFTY"])
    captured: dict[str, dict[str, int]] = {}

    monkeypatch.setattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MAX_AGE_SEC", 2.5, raising=False)
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

    real_prune = ws._prune_stale_option_subscription_tokens

    def _wrapped_prune(**kwargs):
        captured["min_required_by_symbol"] = dict(kwargs.get("min_required_by_symbol") or {})
        return real_prune(**kwargs)

    monkeypatch.setattr(ws, "_prune_stale_option_subscription_tokens", _wrapped_prune)

    tokens, resolution = ws.build_depth_subscription_tokens(["NIFTY"], max_tokens=200)

    row = resolution[0]
    assert captured["min_required_by_symbol"] == {"NIFTY": int(row.get("option_min_required") or 0)}
    assert int(row.get("stale_option_pruned_count") or 0) > 0
    assert int(row.get("final_option_count") or 0) >= int(row.get("option_min_required") or 0)
    assert row.get("option_fail_reason") in (None, "")
    assert int(row.get("option_count") or 0) == int(row.get("final_option_count") or 0)


def test_maybe_refresh_stale_option_subscription_universe_triggers_freshness_refresh(monkeypatch):
    refresh_state = {"last_refresh_epoch": 0.0, "last_freshness_refresh_epoch": 0.0}

    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [101, 102], raising=False)
    monkeypatch.setattr(ws, "_TOKEN_TO_SYMBOL", {101: "NIFTY", 102: "NIFTY"}, raising=False)
    monkeypatch.setattr(ws, "_normalize_positive_tokens", lambda values: [int(v) for v in values if int(v) > 0])
    monkeypatch.setattr(
        ws,
        "get_latest_tick_rows_db",
        lambda tokens: {int(tok): {"ts_epoch": 180.0, "ltp": 100.0} for tok in list(tokens or [])},
    )
    monkeypatch.setattr(
        ws,
        "build_subscription_tokens",
        lambda symbols: ([1, 101, 102], [{"symbol": "NIFTY", "stale_option_pruned_count": 0, "tokens": [101, 102]}]),
    )

    should_refresh, payload = ws._maybe_refresh_stale_option_subscription_universe(
        now_epoch=200.0,
        refresh_state=refresh_state,
    )

    assert should_refresh is True
    assert refresh_state["last_freshness_refresh_epoch"] == 200.0
    assert payload["refresh_mode"] == "symbol_freshness_refresh"
    assert payload["refresh_tokens"] == [101, 102]
    assert payload["refresh_token_count"] == 2
    assert payload["force_resubscribe_current"] is False
    assert payload["freshness_urgent"] is True
    assert payload["fresh_count"] == 0
    assert payload["stale_count"] == 2
    assert payload["fresh_ratio"] == 0.0


def test_maybe_refresh_stale_option_subscription_universe_refreshes_only_stale_symbol_family(monkeypatch):
    refresh_state = {"last_refresh_epoch": 0.0, "last_freshness_refresh_epoch": 0.0}

    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(ws, "_LAST_TOKENS", [101, 102, 201, 202], raising=False)
    monkeypatch.setattr(
        ws,
        "_TOKEN_TO_SYMBOL",
        {101: "NIFTY", 102: "NIFTY", 201: "BANKNIFTY", 202: "BANKNIFTY"},
        raising=False,
    )
    monkeypatch.setattr(ws, "_normalize_positive_tokens", lambda values: [int(v) for v in values if int(v) > 0])

    def _fake_latest_tick_rows_db(tokens):
        rows = {}
        for tok in list(tokens or []):
            tok_int = int(tok)
            rows[tok_int] = {"ts_epoch": 180.0 if tok_int in (101, 102) else 199.5, "ltp": 100.0}
        return rows

    monkeypatch.setattr(ws, "get_latest_tick_rows_db", _fake_latest_tick_rows_db)
    monkeypatch.setattr(
        ws,
        "build_subscription_tokens",
        lambda symbols: (
            [1, 101, 102, 201, 202],
            [
                {"symbol": "NIFTY", "stale_option_pruned_count": 0, "tokens": [101, 102]},
                {"symbol": "BANKNIFTY", "stale_option_pruned_count": 0, "tokens": [201, 202]},
            ],
        ),
    )

    should_refresh, payload = ws._maybe_refresh_stale_option_subscription_universe(
        now_epoch=200.0,
        refresh_state=refresh_state,
    )

    assert should_refresh is True
    assert payload["refresh_mode"] == "symbol_freshness_refresh"
    assert payload["refresh_tokens"] == [101, 102]
    assert payload["refresh_token_count"] == 2
    assert payload["freshness_urgent"] is True
    assert payload["freshness_urgent_symbols"] == ["NIFTY"]
    assert payload["fresh_count"] == 2
    assert payload["stale_count"] == 2


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
