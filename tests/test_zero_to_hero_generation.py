from __future__ import annotations

from config import config as cfg
from strategies.trade_builder import TradeBuilder


def _market_data(symbol="BANKNIFTY", ltp=60000.0, change=200.0, atr=100.0):
    expiry = "2026-03-06"
    chain = [
        {
            "type": "CE",
            "strike": 60000,
            "ltp": 50.0,
            "bid": 49.0,
            "ask": 51.0,
            "expiry": expiry,
            "tradingsymbol": "BANKNIFTY26MAR60000CE",
            "instrument_token": 111,
        },
        {
            "type": "CE",
            "strike": 60600,
            "ltp": 8.0,
            "bid": 7.5,
            "ask": 8.5,
            "expiry": expiry,
            "tradingsymbol": "BANKNIFTY26MAR60600CE",
            "instrument_token": 112,
        },
        {
            "type": "CE",
            "strike": 61200,
            "ltp": 7.0,
            "bid": 6.5,
            "ask": 7.5,
            "expiry": expiry,
            "tradingsymbol": "BANKNIFTY26MAR61200CE",
            "instrument_token": 113,
        },
        {
            "type": "CE",
            "strike": 61800,
            "ltp": 6.0,
            "bid": 5.5,
            "ask": 6.5,
            "expiry": expiry,
            "tradingsymbol": "BANKNIFTY26MAR61800CE",
            "instrument_token": 114,
        },
        {
            "type": "PE",
            "strike": 58800,
            "ltp": 9.0,
            "bid": 8.5,
            "ask": 9.5,
            "expiry": expiry,
            "tradingsymbol": "BANKNIFTY26MAR58800PE",
            "instrument_token": 211,
        },
    ]
    return {
        "symbol": symbol,
        "ltp": ltp,
        "atr": atr,
        "ltp_change_window": change,
        "regime": "TREND",
        "day_type": "TREND_DAY",
        "market_open": False,
        "quote_age_sec": 0,
        "option_chain": chain,
        "chain_source": "synthetic_offhours",
        "market_context": {"execution_mode": "PAPER", "market_open": False},
    }


def test_zero_to_hero_generation_otm(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_ALLOWED_MODES", ["PAPER"], raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_ALLOWED_REGIMES", ["TREND", "EVENT"], raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_OTM_PCT_MIN", 0.01, raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_OTM_PCT_MAX", 0.02, raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_PREMIUM_PCT_LOW", 0.0, raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_PREMIUM_PCT_HIGH", 1.0, raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_PREMIUM_MIN_ROWS", 1, raising=False)

    tb = TradeBuilder()
    monkeypatch.setattr(tb.execution, "spread_ok", lambda *args, **kwargs: True, raising=False)

    md = _market_data()
    trade = tb.build_zero_hero(md)
    assert trade is not None
    assert trade.option_type == "CE"
    assert trade.strike >= md["ltp"] * 1.01
    assert trade.strike <= md["ltp"] * 1.02


def test_zero_to_hero_paper_only(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_ALLOWED_MODES", ["PAPER"], raising=False)
    tb = TradeBuilder()
    md = _market_data()
    trade = tb.build_zero_hero(md)
    assert trade is None


def test_zero_to_hero_not_executable(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_ALLOWED_MODES", ["PAPER"], raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_PREMIUM_PCT_LOW", 0.0, raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_PREMIUM_PCT_HIGH", 1.0, raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_PREMIUM_MIN_ROWS", 1, raising=False)

    tb = TradeBuilder()
    monkeypatch.setattr(tb.execution, "spread_ok", lambda *args, **kwargs: True, raising=False)

    md = _market_data()
    trade = tb.build_zero_hero(md)
    assert trade is not None
    assert trade.execution_allowed is False
    assert trade.planning_only is True
