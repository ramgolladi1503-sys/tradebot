import pytest

from dashboard.streamlit_app_runtime import build_display_row


def test_build_display_row_maps_executable_quote_fields():
    trade = {"symbol": "BANKNIFTY", "stop": 95.0, "confidence": 0.88}
    quote = {
        "ltp": 101.5,
        "bid": 101.0,
        "ask": 102.0,
        "mark_price": 101.6,
        "quote_age_sec": 0.7,
    }

    row = build_display_row(trade, quote)

    assert row["symbol"] == "BANKNIFTY"
    assert row["ltp"] == 101.5
    assert row["bid"] == 101.0
    assert row["ask"] == 102.0
    assert row["mark_price"] == 101.6
    assert row["quote_age_sec"] == 0.7
    assert row["spread_pct"] == pytest.approx((102.0 - 101.0) / 101.6)


def test_build_display_row_missing_quote_sets_none():
    row = build_display_row({"symbol": "NIFTY", "stop": 220.0}, None)

    assert row["symbol"] == "NIFTY"
    assert row["ltp"] is None
    assert row["bid"] is None
    assert row["ask"] is None
    assert row["mark_price"] is None
    assert row["quote_age_sec"] is None
    assert row["spread_pct"] is None


def test_build_display_row_keeps_explicit_spread_pct():
    quote = {"ltp": 50.0, "bid": 49.5, "ask": 50.5, "mark_price": 50.0, "spread_pct": 0.02}
    row = build_display_row({"symbol": "SENSEX"}, quote)
    assert row["spread_pct"] == 0.02
