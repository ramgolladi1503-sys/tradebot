from __future__ import annotations

from datetime import date

from config import config as cfg
from core.kite_client import kite_client
from core.option_chain import fetch_option_chain


def _build_inst(tradingsymbol: str, strike: float, expiry: date, opt_type: str = "CE"):
    return {
        "name": "NIFTY",
        "segment": "NFO-OPT",
        "tradingsymbol": tradingsymbol,
        "expiry": expiry,
        "strike": float(strike),
        "instrument_type": opt_type,
        "instrument_token": int(abs(hash((tradingsymbol, strike, opt_type))) % 10_000_000),
    }


def test_fetch_option_chain_falls_back_to_available_expiry(monkeypatch):
    instruments = [
        _build_inst("NIFTY30JAN22000CE", 22000, date(2030, 1, 30), "CE"),
        _build_inst("NIFTY30JAN22000PE", 22000, date(2030, 1, 30), "PE"),
        _build_inst("NIFTY30JAN22050CE", 22050, date(2030, 1, 30), "CE"),
        _build_inst("NIFTY30JAN22050PE", 22050, date(2030, 1, 30), "PE"),
        _build_inst("NIFTY30JAN22100CE", 22100, date(2030, 1, 30), "CE"),
        _build_inst("NIFTY30JAN22100PE", 22100, date(2030, 1, 30), "PE"),
    ]

    quotes = {}
    for inst in instruments:
        key = f"NFO:{inst['tradingsymbol']}"
        strike = inst["strike"]
        quotes[key] = {
            "last_price": max(10.0, 100.0 - abs(strike - 22050) * 0.25),
            "depth": {
                "buy": [{"price": 99.0, "quantity": 200}],
                "sell": [{"price": 101.0, "quantity": 250}],
            },
            "volume": 1000,
            "oi": 5000,
            "timestamp": "2030-01-10T10:00:00",
        }

    monkeypatch.setattr(cfg, "KITE_USE_API", True, raising=False)
    monkeypatch.setattr(cfg, "ENABLE_TERM_STRUCTURE", False, raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_LIVE_OPTION_QUOTES", False, raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_DEPTH_QUOTES_FOR_TRADE", False, raising=False)
    monkeypatch.setattr(kite_client, "kite", object(), raising=False)
    monkeypatch.setattr(kite_client, "ensure", lambda: None)
    monkeypatch.setattr(kite_client, "next_available_expiry", lambda symbol, exchange="NFO": "2030-01-23")
    monkeypatch.setattr(kite_client, "instruments_cached", lambda exchange, ttl_sec=3600: instruments)
    monkeypatch.setattr(kite_client, "quote", lambda symbols: {symbol: quotes.get(symbol, {}) for symbol in symbols})
    monkeypatch.setattr("core.option_chain.next_expiry_after", lambda start_date, expiry_type="WEEKLY", symbol=None: None)

    chain = fetch_option_chain("NIFTY", ltp=22048.0, strikes_around=2)

    assert len(chain) > 0
    assert all(row.get("expiry") == "2030-01-30" for row in chain)
    assert min(row.get("ltp", 0) for row in chain) > 0
