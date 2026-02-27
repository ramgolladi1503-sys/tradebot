import pandas as pd

from dashboard.ui.table_model import normalize_df, filter_non_active


def test_normalize_df_adds_missing_cols():
    df = pd.DataFrame([{"symbol": "NIFTY", "side": "BUY"}])
    out = normalize_df(df)
    assert "last_seen_ts" in out.columns
    assert "entry" in out.columns
    assert "target" in out.columns
    assert "status" in out.columns


def test_timestamp_renamed_to_last_seen_ts():
    df = pd.DataFrame([{"timestamp": "2026-02-27T10:00:00Z", "symbol": "NIFTY"}])
    out = normalize_df(df)
    assert "last_seen_ts" in out.columns
    assert pd.notna(out.iloc[0]["last_seen_ts"])


def test_active_filtered_out_of_advisory():
    df = pd.DataFrame(
        [
            {"symbol": "NIFTY", "status": "ACTIVE"},
            {"symbol": "BANKNIFTY", "status": "PLANNING"},
        ]
    )
    out = normalize_df(df)
    filtered = filter_non_active(out)
    symbols = set(filtered["symbol"].astype(str).tolist())
    assert "NIFTY" not in symbols
    assert "BANKNIFTY" in symbols
