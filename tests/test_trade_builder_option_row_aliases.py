from __future__ import annotations

from strategies.trade_builder import TradeBuilder


def test_normalize_option_row_accepts_alias_fields():
    tb = TradeBuilder()
    row = {
        "option_type": "call",
        "strike_price": "25000",
        "last_price": "101.5",
        "best_bid": "101.0",
        "best_ask": "102.0",
        "quote_timestamp_epoch": "1771400000",
    }
    opt, err = tb._normalize_option_row(row, expected_type="CE")
    assert err is None
    assert opt is not None
    assert opt["type"] == "CE"
    assert opt["strike"] == 25000.0
    assert opt["ltp"] == 101.5
    assert opt["bid"] == 101.0
    assert opt["ask"] == 102.0
    assert opt["quote_ts_epoch"] == 1771400000.0


def test_normalize_option_row_reads_bid_ask_from_depth():
    tb = TradeBuilder()
    row = {
        "right": "PE",
        "strike": 24900,
        "ltp": 95.0,
        "depth": {
            "buy": [{"price": 94.5}],
            "sell": [{"price": 95.5}],
        },
    }
    opt, err = tb._normalize_option_row(row, expected_type="PE")
    assert err is None
    assert opt is not None
    assert opt["type"] == "PE"
    assert opt["bid"] == 94.5
    assert opt["ask"] == 95.5
    assert opt["depth_ok"] is True


def test_normalize_option_row_infers_missing_type():
    tb = TradeBuilder()
    row = {
        "strike": 25000,
        "ltp": 100.0,
        "best_bid": 99.5,
        "best_ask": 100.5,
        "quote_ts_epoch": 1771400000.0,
    }
    opt, err = tb._normalize_option_row(row, expected_type="CE")
    assert err is None
    assert opt is not None
    assert opt["type"] == "CE"
    assert opt.get("type_inferred") is True


def test_resolve_option_contract_uses_nearest_strike_fallback():
    tb = TradeBuilder()
    market_data = {
        "option_chain": [
            {
                "type": "CE",
                "strike": 25000.0,
                "expiry": "2026-04-30",
                "tradingsymbol": "NIFTY26APR25000CE",
                "instrument_token": 112233,
            }
        ]
    }
    contract = tb._resolve_option_contract(
        "NIFTY",
        25050.0,
        "CE",
        "2026-04-30",
        market_data,
    )
    assert contract["tradingsymbol"] == "NIFTY26APR25000CE"
    assert int(contract["instrument_token"]) == 112233
    assert contract.get("fallback_applied") is True
