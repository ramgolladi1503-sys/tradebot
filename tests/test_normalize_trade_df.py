import pandas as pd

from dashboard.utils import REQUIRED_COLUMNS, normalize_trade_df


def test_normalize_trade_df_maps_synonyms():
    df = pd.DataFrame(
        [
            {
                "expiry": "2026-02-25",
                "type": "CE",
                "entry_price": 111.5,
                "stop_loss": 10,
                "tp": 20,
                "instrument_token": 123,
                "underlying": "NIFTY",
            }
        ]
    )
    norm = normalize_trade_df(df)
    row = norm.iloc[0]
    assert row["expiry_date"] == "2026-02-25"
    assert row["option_type"] == "CE"
    assert row["entry"] == 111.5
    assert row["stop"] == 10
    assert row["target"] == 20
    assert row["instrument_id"] == 123
    assert row["symbol"] == "NIFTY"


def test_normalize_trade_df_adds_missing_columns():
    df = pd.DataFrame([{"entry": 100}])
    norm = normalize_trade_df(df)
    for col in REQUIRED_COLUMNS:
        assert col in norm.columns
    assert norm.loc[0, "status"] == "PLANNING"


def test_normalize_trade_df_does_not_use_signal_price_as_entry_when_stale():
    df = pd.DataFrame(
        [
            {
                "symbol": "NIFTY",
                "signal_price": 101.67,
                "entry_price": 101.67,
                "entry": None,
                "suggested_entry": None,
                "entry_status": "STALE_PRICE",
            }
        ]
    )
    norm = normalize_trade_df(df)
    assert pd.isna(norm.loc[0, "entry"])


def test_normalize_trade_df_uses_suggested_entry_when_ok():
    df = pd.DataFrame(
        [
            {
                "symbol": "NIFTY",
                "entry": None,
                "suggested_entry": 44.3,
                "entry_status": "OK",
            }
        ]
    )
    norm = normalize_trade_df(df)
    assert float(norm.loc[0, "entry"]) == 44.3


def test_normalize_trade_df_expected_and_fill_entry_ok_status():
    df = pd.DataFrame(
        [
            {
                "symbol": "NIFTY",
                "entry": None,
                "suggested_entry": 44.3,
                "entry_status": "OK",
            }
        ]
    )
    norm = normalize_trade_df(df)
    assert float(norm.loc[0, "entry"]) == 44.3
    assert float(norm.loc[0, "expected_entry"]) == 44.3
    assert float(norm.loc[0, "fill_entry"]) == 44.3


def test_normalize_trade_df_uses_current_ltp_for_price_mismatch():
    df = pd.DataFrame(
        [
            {
                "symbol": "NIFTY",
                "entry": None,
                "suggested_entry": None,
                "current_ltp": 565.0,
                "entry_status": "PRICE_MISMATCH",
            }
        ]
    )
    norm = normalize_trade_df(df)
    assert float(norm.loc[0, "entry"]) == 565.0
    assert float(norm.loc[0, "expected_entry"]) == 565.0
    assert float(norm.loc[0, "fill_entry"]) == 565.0


def test_normalize_trade_df_expected_entry_present_when_stale_option_ltp():
    df = pd.DataFrame(
        [
            {
                "symbol": "NIFTY",
                "entry": None,
                "suggested_entry": 257.0,
                "entry_status": "STALE_OPTION_LTP",
            }
        ]
    )
    norm = normalize_trade_df(df)
    assert pd.isna(norm.loc[0, "entry"])
    assert float(norm.loc[0, "expected_entry"]) == 257.0
    assert pd.isna(norm.loc[0, "fill_entry"])
