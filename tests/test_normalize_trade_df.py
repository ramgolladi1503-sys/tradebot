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
    assert pd.isna(row["entry"])
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


def test_normalize_trade_df_does_not_backfill_entry_from_suggested_entry():
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
    assert pd.isna(norm.loc[0, "entry"])


def test_normalize_trade_df_does_not_invent_expected_or_fill_entry():
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
    assert pd.isna(norm.loc[0, "entry"])
    assert pd.isna(norm.loc[0, "expected_entry"])
    assert pd.isna(norm.loc[0, "fill_entry"])


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
    assert pd.isna(norm.loc[0, "entry"])
    assert pd.isna(norm.loc[0, "expected_entry"])
    assert pd.isna(norm.loc[0, "fill_entry"])


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
    assert pd.isna(norm.loc[0, "expected_entry"])
    assert pd.isna(norm.loc[0, "fill_entry"])


def test_normalize_trade_df_preserves_permission_and_readiness():
    df = pd.DataFrame(
        [
            {
                "symbol": "NIFTY",
                "permission": "EXECUTE",
                "permission_reason": "engine_decision",
                "readiness": "READY",
                "final_action": "EXECUTE",
            }
        ]
    )
    norm = normalize_trade_df(df)
    row = norm.iloc[0]
    assert row["permission"] == "EXECUTE"
    assert row["permission_reason"] == "engine_decision"
    assert row["readiness"] == "READY"
    assert row["final_action"] == "EXECUTE"


def test_normalize_trade_df_preserves_entry_semantics():
    df = pd.DataFrame(
        [
            {
                "symbol": "NIFTY",
                "entry": 50.0,
                "entry_status": "displayable",
                "display_entry": 60.0,
                "display_entry_status": "displayable",
                "execution_entry": 70.0,
                "execution_entry_status": "executable",
            }
        ]
    )
    norm = normalize_trade_df(df)
    row = norm.iloc[0]
    assert float(row["entry"]) == 50.0
    assert float(row["display_entry"]) == 60.0
    assert float(row["execution_entry"]) == 70.0
    assert row["entry_status"] == "displayable"


def test_normalize_trade_df_preserves_blockers():
    df = pd.DataFrame(
        [
            {
                "symbol": "NIFTY",
                "blockers": ["STALE_OPTION_LTP"],
                "hard_blockers": ["NO_TOKEN"],
                "soft_penalties": ["SPREAD_WARN"],
                "warnings": ["LTP_STALE"],
            }
        ]
    )
    norm = normalize_trade_df(df)
    row = norm.iloc[0]
    assert row["blockers"] == ["STALE_OPTION_LTP"]
    assert row["hard_blockers"] == ["NO_TOKEN"]
    assert row["soft_penalties"] == ["SPREAD_WARN"]
    assert row["warnings"] == ["LTP_STALE"]
