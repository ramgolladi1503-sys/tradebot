from __future__ import annotations

from datetime import date

import pytest

from config import config as cfg
import strategies.banknifty_intraday as banknifty_intraday
import strategies.nifty_intraday as nifty_intraday
import strategies.sensex_intraday as sensex_intraday
import strategies.zero_hero as zero_hero


@pytest.mark.parametrize(
    ("module", "ltp", "vwap", "bias"),
    [
        (nifty_intraday, 100.35, 100.0, "bullish"),
        (banknifty_intraday, 50520.0, 50340.0, "bullish"),
        (sensex_intraday, 78120.0, 77850.0, "bullish"),
    ],
)
def test_same_input_differs_by_regime(module, ltp, vwap, bias):
    trend_debug = {}
    range_debug = {}

    trend_signal = module.generate_signal(
        ltp=ltp,
        vwap=vwap,
        bias=bias,
        debug_stats=trend_debug,
        regime="TRENDING_UP",
    )
    range_signal = module.generate_signal(
        ltp=ltp,
        vwap=vwap,
        bias=bias,
        debug_stats=range_debug,
        regime="RANGE",
    )

    assert trend_signal is not None
    assert range_signal is not None
    assert trend_signal["setup_type"] == "BREAKOUT"
    assert range_signal["setup_type"] == "MEAN_REVERSION"
    assert trend_signal["direction"] != range_signal["direction"]
    assert trend_debug["regime_path"]["regime"] == "TRENDING_UP"
    assert range_debug["regime_path"]["regime"] == "RANGE"


def test_breakout_generation_suppressed_in_range_regime():
    debug = {}

    signal = nifty_intraday.generate_signal(
        ltp=100.35,
        vwap=100.0,
        bias="bullish",
        debug_stats=debug,
        regime="RANGE",
    )

    assert signal is not None
    assert signal["setup_type"] == "MEAN_REVERSION"
    assert "breakout_suppressed_range_regime" in signal["soft_flags"]
    assert signal["regime_path"] == "RANGE"
    assert debug["regime_path"]["setup_family"] == "MEAN_REVERSION"


def test_zero_hero_differs_between_expiry_and_non_expiry_context(monkeypatch):
    monkeypatch.setattr(zero_hero, "next_expiry", lambda _symbol: date(2026, 3, 12))
    monkeypatch.setattr(cfg, "ZERO_HERO_ALLOW_NON_EXPIRY_CONTEXT", True, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_NON_EXPIRY_PREMIUM_FLOOR", 15.0, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_NON_EXPIRY_ENTRY_MULT", 0.0035, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_NON_EXPIRY_TARGET_MULT", 1.6, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_NON_EXPIRY_STOP_MULT", 0.85, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_NON_EXPIRY_CONFIDENCE", 46, raising=False)

    expiry_debug = {}
    non_expiry_debug = {}

    expiry_trades = zero_hero.zero_hero_strategy(
        "NIFTY",
        22050.0,
        {"bias": "bullish"},
        current_date=date(2026, 3, 11),
        debug_stats=expiry_debug,
        regime="EXPIRY_CONTEXT",
    )
    non_expiry_trades = zero_hero.zero_hero_strategy(
        "NIFTY",
        22050.0,
        {"bias": "bullish"},
        current_date=date(2026, 3, 1),
        debug_stats=non_expiry_debug,
        regime="TRENDING_UP",
    )

    assert len(expiry_trades) == 1
    assert len(non_expiry_trades) == 1
    assert expiry_trades[0]["confidence_reason"] != non_expiry_trades[0]["confidence_reason"]
    assert expiry_trades[0]["entry_price"] != non_expiry_trades[0]["entry_price"]
    assert expiry_trades[0]["variant"] == "expiry_context"
    assert non_expiry_trades[0]["variant"] == "non_expiry_context"
    assert expiry_debug["regime_path"]["regime"] == "EXPIRY_CONTEXT"
    assert non_expiry_debug["regime_path"]["regime"] == "TRENDING_UP"
