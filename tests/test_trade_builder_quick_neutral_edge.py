from __future__ import annotations

from config import config as cfg
from strategies.trade_builder import TradeBuilder


def test_quick_neutral_fallback_requires_edge(monkeypatch):
    monkeypatch.setattr(cfg, "QUICK_NEUTRAL_FALLBACK_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "QUICK_NEUTRAL_EDGE_MIN", 0.18, raising=False)
    tb = TradeBuilder()
    md = {
        "atr": 50.0,
        "vwap_slope": 0.0,
        "rsi_mom": 0.0,
        "ltp_change": 0.0,
        "ltp_change_window": 0.0,
    }
    signal = tb._quick_neutral_fallback_signal(md, ltp=25000.0, vwap=25000.0)
    assert signal is None


def test_quick_neutral_fallback_direction_uses_signed_edge(monkeypatch):
    monkeypatch.setattr(cfg, "QUICK_NEUTRAL_FALLBACK_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "QUICK_NEUTRAL_EDGE_MIN", 0.10, raising=False)
    tb = TradeBuilder()
    md = {
        "atr": 40.0,
        "vwap_slope": -0.002,
        "rsi_mom": -0.4,
        "ltp_change": -10.0,
        "ltp_change_window": -25.0,
    }
    signal = tb._quick_neutral_fallback_signal(md, ltp=24920.0, vwap=25000.0)
    assert signal is not None
    assert signal["direction"] == "BUY_PUT"
    assert signal["reason"] == "Quick neutral edge fallback"
    assert float(signal["score"]) > float(getattr(cfg, "QUICK_NEUTRAL_SCORE_BASE", 0.53))
