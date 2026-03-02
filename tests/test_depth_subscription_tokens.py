from __future__ import annotations

from datetime import date

from config import config as cfg
from core import kite_depth_ws as ws


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

    def _fake_resolve_option_tokens_window(symbol, expiry_date, atm_strike, strikes_around, step, exchange="NFO"):
        symbol_u = str(symbol).upper()
        calls.append(
            {
                "symbol": symbol_u,
                "expiry": expiry_date,
                "atm": int(atm_strike),
                "strikes_around": int(strikes_around),
                "step": int(step),
                "exchange": str(exchange),
            }
        )
        out: list[int] = []
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

    assert len(tokens) == len(set(tokens))
    for token in ctx["index_tokens"].values():
        assert token in tokens

    token_meta = ctx["token_meta"]
    expected_strike_counts = {"NIFTY": 13, "BANKNIFTY": 13, "SENSEX": 9}
    for symbol, expected_count in expected_strike_counts.items():
        sym_tokens = [t for t in tokens if token_meta.get(t, {}).get("symbol") == symbol]
        strikes = sorted({int(token_meta[t]["strike"]) for t in sym_tokens})
        assert len(strikes) == expected_count
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
    assert calls_by_symbol["NIFTY"]["step"] == 50
    assert calls_by_symbol["BANKNIFTY"]["step"] == 100
    assert calls_by_symbol["SENSEX"]["step"] == 100

    # Baseline token universe is approximately 73 without sticky tokens.
    assert 70 <= len(tokens) <= 80


def test_build_depth_subscription_tokens_budget_drops_farthest_options_first(monkeypatch):
    ctx = _setup_depth_window_mocks(monkeypatch)

    tokens, _resolution = ws.build_depth_subscription_tokens(["NIFTY"], max_tokens=11)

    index_token = ctx["index_tokens"]["NIFTY"]
    assert index_token in tokens
    assert len(tokens) == 11

    token_meta = ctx["token_meta"]
    option_tokens = [t for t in tokens if token_meta.get(t, {}).get("symbol") == "NIFTY"]
    kept_strikes = {int(token_meta[t]["strike"]) for t in option_tokens}
    atm = int(ctx["atm_by_symbol"]["NIFTY"])
    assert kept_strikes == {atm - 100, atm - 50, atm, atm + 50, atm + 100}


def test_sticky_tokens_are_preserved_in_final_subscription(monkeypatch):
    ctx = _setup_depth_window_mocks(monkeypatch)
    sticky_token = 990001
    monkeypatch.setattr(ws, "get_sticky_tokens", lambda: {sticky_token})

    tokens, _resolution = ws.build_depth_subscription_tokens(["NIFTY"], max_tokens=3)

    assert sticky_token in tokens
    assert ctx["index_tokens"]["NIFTY"] in tokens
    assert len(tokens) == 3
