import pandas as pd

from dashboard.utils import REQUIRED_COLUMNS, normalize_trade_df


def test_normalize_trade_df_maps_synonyms():
    df = pd.DataFrame(
        [
            {
                "expiry": "2026-02-25",
                "type": "CE",
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
