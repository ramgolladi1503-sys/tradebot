from __future__ import annotations

from config import config as cfg
from strategies.trade_builder import TradeBuilder


def test_zero_to_hero_premium_band_fallback_when_insufficient_rows(monkeypatch):
    tb = TradeBuilder()
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_PREMIUM_MIN_ROWS", 50, raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_PREMIUM_FALLBACK_LOW", 10.0, raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_PREMIUM_FALLBACK_HIGH", 120.0, raising=False)

    low, high, source = tb._zero_to_hero_premium_band([], "CE", "2026-03-27")

    assert low == 10.0
    assert high == 120.0
    assert source == "fallback_band"
