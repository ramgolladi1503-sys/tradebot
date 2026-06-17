import pytest
from datetime import date
from config import config as cfg
from strategies.volatility_trend import volatility_scaled_trend_strategy
from strategies.vwap_orb import vwap_orb_strategy
from strategies.zero_hero import zero_hero_strategy


def test_vwap_orb_fails_closed_on_positive_gamma():
    # Proves that positive gamma suppresses volatility and vetoes ORB trades
    assert (
        vwap_orb_strategy(
            "NIFTY",
            101.0,
            100.0,
            market_data={"dealer_gamma_exposure": 1000},
        )
        == []
    )


def test_zero_hero_requires_expiry_context(monkeypatch):
    # Proves the strategy respects the strict expiry config when non-expiry is disabled
    monkeypatch.setattr(cfg, "ZERO_HERO_ALLOW_NON_EXPIRY_CONTEXT", False)
    assert (
        zero_hero_strategy(
            "NIFTY",
            22050.0,
            {"bias": "bullish"},
            current_date=date(2026, 3, 11),
            expiry_window_days=0,
        )
        == []
    )


def test_volatility_trend_fails_closed_on_no_cross_asset_confirmation():
    # Proves that it vetoes if cross-assets are not confirming the trend direction
    assert (
        volatility_scaled_trend_strategy(
            "NIFTY",
            101.0,
            100.0,
            1.2,
            cross_assets={"BANKNIFTY": {"ltp": 90.0, "vwap": 100.0}},  # Opposite trend to Nifty
        )
        == []
    )
