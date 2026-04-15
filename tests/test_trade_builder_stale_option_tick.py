from __future__ import annotations

from strategies.trade_builder import TradeBuilder
import strategies.trade_builder as trade_builder_module
from config import config as cfg


class _MarketCtx:
    def __init__(self, allow_stale_quotes: bool = True, *, mode: str = "SIM", is_market_open: bool = False):
        self.allow_stale_quotes = allow_stale_quotes
        self.mode = mode
        self.is_market_open = is_market_open


def test_stale_option_tick_softens_when_allowed(monkeypatch):
    tb = TradeBuilder()
    monkeypatch.setattr(
        tb,
        "_resolve_option_contract",
        lambda *_args, **_kwargs: {
            "expiry": "2026-03-26",
            "tradingsymbol": "NIFTY26MAR25000CE",
            "instrument_token": 123456,
            "instrument_id": "NIFTY26MAR25000CE",
        },
        raising=True,
    )
    opt = {
        "strike": 25000,
        "type": "CE",
        "quote_source": "live",
        "option_ltp_source": "option_chain_live",
        "quote_ts_epoch": None,
    }
    ok, ctx = tb._option_tradability_precondition(
        symbol="NIFTY",
        opt=opt,
        market_data={"symbol": "NIFTY"},
        market_ctx=_MarketCtx(allow_stale_quotes=True),
        direction="BUY_CALL",
    )
    assert ok is True
    assert ctx.get("stale_option_tick") is True


def test_live_mild_stale_option_tick_softens_when_spread_and_volume_clean(monkeypatch):
    tb = TradeBuilder()
    monkeypatch.setattr(
        tb,
        "_resolve_option_contract",
        lambda *_args, **_kwargs: {
            "expiry": "2026-03-26",
            "tradingsymbol": "NIFTY26MAR25000CE",
            "instrument_token": 123456,
            "instrument_id": "NIFTY26MAR25000CE",
        },
        raising=True,
    )
    monkeypatch.setattr(cfg, "TRADE_BUILDER_ALLOW_LIVE_STALE_OPTION_TICK_SOFTEN", True, raising=False)
    monkeypatch.setattr(cfg, "OPTION_TICK_SOFT_STALE_SEC", 3.0, raising=False)
    monkeypatch.setattr(cfg, "OPTION_TICK_HARD_STALE_SEC", 6.0, raising=False)
    monkeypatch.setattr(cfg, "MAX_SPREAD_PCT", 0.02, raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_VOLUME_FOR_TRADE", False, raising=False)
    opt = {
        "strike": 25000,
        "type": "CE",
        "quote_source": "live",
        "option_ltp_source": "option_chain_live",
        "quote_age_sec": 2.6,
        "bid": 199.0,
        "ask": 201.0,
        "ltp": 200.0,
        "volume": 10,
    }
    ok, ctx = tb._option_tradability_precondition(
        symbol="NIFTY",
        opt=opt,
        market_data={"symbol": "NIFTY"},
        market_ctx=_MarketCtx(allow_stale_quotes=False, mode="LIVE", is_market_open=True),
        direction="BUY_CALL",
    )
    assert ok is True
    assert ctx.get("reason_code") == "STALE_OPTION_TICK"
    assert ctx.get("stale_option_tick") is True
    assert ctx.get("live_softened") is True
    assert ctx.get("spread_ok") is True


def test_live_hard_stale_option_tick_still_rejects(monkeypatch):
    tb = TradeBuilder()
    monkeypatch.setattr(
        tb,
        "_resolve_option_contract",
        lambda *_args, **_kwargs: {
            "expiry": "2026-03-26",
            "tradingsymbol": "NIFTY26MAR25000CE",
            "instrument_token": 123456,
            "instrument_id": "NIFTY26MAR25000CE",
        },
        raising=True,
    )
    monkeypatch.setattr(cfg, "TRADE_BUILDER_ALLOW_LIVE_STALE_OPTION_TICK_SOFTEN", True, raising=False)
    monkeypatch.setattr(cfg, "OPTION_TICK_SOFT_STALE_SEC", 3.0, raising=False)
    monkeypatch.setattr(cfg, "OPTION_TICK_HARD_STALE_SEC", 6.0, raising=False)
    monkeypatch.setattr(cfg, "MAX_SPREAD_PCT", 0.02, raising=False)
    opt = {
        "strike": 25000,
        "type": "CE",
        "quote_source": "live",
        "option_ltp_source": "option_chain_live",
        "quote_age_sec": 9.0,
        "bid": 199.0,
        "ask": 201.0,
        "ltp": 200.0,
        "volume": 10,
    }
    ok, ctx = tb._option_tradability_precondition(
        symbol="NIFTY",
        opt=opt,
        market_data={"symbol": "NIFTY"},
        market_ctx=_MarketCtx(allow_stale_quotes=False, mode="LIVE", is_market_open=True),
        direction="BUY_CALL",
    )
    assert ok is False
    assert ctx.get("reason_code") == "STALE_OPTION_TICK"
    assert ctx.get("hard_stale") is True


def test_stale_option_tick_can_be_bypassed_in_non_live_diagnostic_mode(monkeypatch):
    tb = TradeBuilder()
    monkeypatch.setattr(
        tb,
        "_resolve_option_contract",
        lambda *_args, **_kwargs: {
            "expiry": "2026-03-26",
            "tradingsymbol": "NIFTY26MAR25000CE",
            "instrument_token": 123456,
            "instrument_id": "NIFTY26MAR25000CE",
        },
        raising=True,
    )
    monkeypatch.setattr(cfg, "TRADE_BUILDER_STALE_OPTION_TICK_BYPASS_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_STALE_OPTION_TICK_BYPASS_ALLOW_LIVE", False, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_STALE_OPTION_TICK_BYPASS_MAX_SEC", 300.0, raising=False)
    monkeypatch.setattr(trade_builder_module, "get_option_ltp_sla_sec", lambda *args, **kwargs: 2.0, raising=True)
    opt = {
        "strike": 25000,
        "type": "CE",
        "quote_source": "live",
        "option_ltp_source": "option_chain_live",
        "quote_age_sec": 200.0,
        "bid": 199.0,
        "ask": 201.0,
        "ltp": 200.0,
        "volume": 10,
    }
    ok, ctx = tb._option_tradability_precondition(
        symbol="NIFTY",
        opt=opt,
        market_data={"symbol": "NIFTY"},
        market_ctx=_MarketCtx(allow_stale_quotes=False, mode="SIM", is_market_open=True),
        direction="BUY_CALL",
    )
    assert ok is True
    assert ctx.get("reason_code") == "STALE_OPTION_TICK"
    assert ctx.get("stale_bypass") is True
