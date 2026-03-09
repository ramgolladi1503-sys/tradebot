from __future__ import annotations

from strategies.trade_builder import TradeBuilder
from config import config as cfg


class _ExecStub:
    def spread_ok(self, bid, ask, price, **_kwargs):
        try:
            bid_f = float(bid)
            ask_f = float(ask)
            px_f = float(price)
        except Exception:
            return False
        if px_f <= 0 or ask_f < bid_f:
            return False
        return ((ask_f - bid_f) / px_f) <= 0.35

    def estimate_slippage(self, *_args, **_kwargs):
        return 0.0


def _option_row(strike: float, opt_type: str, ltp: float) -> dict:
    return {
        "type": opt_type,
        "strike": strike,
        "ltp": ltp,
        "bid": round(ltp * 0.98, 2),
        "ask": round(ltp * 1.02, 2),
        "volume": 1000,
        "instrument_token": int(strike * 10),
        "tradingsymbol": f"NIFTYEXP{int(strike)}{opt_type}",
    }


def test_expiry_lotto_mode_generates_3_to_4_candidates(monkeypatch):
    monkeypatch.setattr(cfg, "EXPIRY_LOTTO_MODE", True, raising=False)
    monkeypatch.setattr(cfg, "EXPIRY_LOTTO_TARGET_CANDIDATES", 4, raising=False)
    monkeypatch.setattr(cfg, "EXPIRY_LOTTO_MAX_TRADES", 4, raising=False)
    monkeypatch.setattr(cfg, "EXPIRY_LOTTO_ATM_STRIKES", 2, raising=False)
    monkeypatch.setattr(cfg, "EXPIRY_LOTTO_MIN_OPTION_TOKENS", 4, raising=False)
    monkeypatch.setattr(cfg, "EXPIRY_LOTTO_REQUIRE_TREND_CONFIRM", False, raising=False)
    monkeypatch.setattr(cfg, "LOT_SIZE", {"NIFTY": 50}, raising=False)

    builder = TradeBuilder(predictor=object(), execution=_ExecStub())
    monkeypatch.setattr(
        builder,
        "_resolve_option_contract",
        lambda symbol, strike, opt_type, expiry, market_data: {
            "expiry": "2026-03-02",
            "tradingsymbol": f"{symbol}-2026-03-02-{int(float(strike))}-{opt_type}",
            "instrument_token": int(float(strike) * 10),
        },
    )
    monkeypatch.setattr(
        builder,
        "_identity_fields",
        lambda symbol, instrument, expiry, strike, right, qty_lots: ("OPT", f"{symbol}|{expiry}|{strike}|{right}", 50, None),
    )
    monkeypatch.setattr(
        builder,
        "trade_intent_flags",
        lambda *args, **kwargs: {
            "tradable": True,
            "tradable_reasons_blocking": [],
            "planning_only": True,
            "execution_allowed": False,
            "execution_reason": "EXPIRY_LOTTO_MODE",
            "source_flags": {},
        },
    )

    chain = [
        _option_row(24600, "CE", 95.0),
        _option_row(24650, "CE", 90.0),
        _option_row(24700, "CE", 88.0),
        _option_row(24750, "CE", 84.0),
        _option_row(24800, "CE", 79.0),
        _option_row(24600, "PE", 50.0),
    ]
    market_data = {
        "symbol": "NIFTY",
        "ltp": 24705.0,
        "atr": 120.0,
        "ltp_change_window": 30.0,
        "day_type": "EXPIRY_DAY",
        "trend_state": "UP",
        "orb_bias": "UP",
        "option_chain": chain,
        "market_open": True,
    }

    out = builder.build_expiry_lotto_candidates(market_data, debug_reasons=True)
    assert 3 <= len(out) <= 4
    assert all(str(t.strategy) == "EXPIRY_LOTTO" for t in out)
    assert all(bool(t.planning_only) for t in out)


def test_expiry_lotto_fail_fast_when_option_tokens_under_min(monkeypatch):
    monkeypatch.setattr(cfg, "EXPIRY_LOTTO_MODE", True, raising=False)
    monkeypatch.setattr(cfg, "EXPIRY_LOTTO_MIN_OPTION_TOKENS", 6, raising=False)
    monkeypatch.setattr(cfg, "MIN_OPTION_TOKENS", 6, raising=False)
    monkeypatch.setattr(cfg, "EXPIRY_LOTTO_REQUIRE_TREND_CONFIRM", False, raising=False)
    monkeypatch.setattr(cfg, "LOT_SIZE", {"NIFTY": 50}, raising=False)

    builder = TradeBuilder(predictor=object(), execution=_ExecStub())
    incidents: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "strategies.trade_builder.create_incident",
        lambda sev, code, context: incidents.append((str(code), dict(context or {}))) or "inc-test",
    )
    chain = [
        _option_row(24600, "CE", 95.0),
        _option_row(24650, "CE", 90.0),
    ]
    market_data = {
        "symbol": "NIFTY",
        "ltp": 24705.0,
        "atr": 120.0,
        "ltp_change_window": 30.0,
        "day_type": "EXPIRY_DAY",
        "trend_state": "UP",
        "orb_bias": "UP",
        "option_chain": chain,
        "market_open": True,
    }

    out = builder.build_expiry_lotto_candidates(market_data, debug_reasons=True)
    assert out == []
    assert isinstance(builder._reject_ctx, dict)
    assert builder._reject_ctx.get("reason") == "expiry_lotto_option_tokens_under_min"
    assert incidents and incidents[-1][0] == "EXPIRY_LOTTO_OPTION_TOKENS_UNDER_MIN"
