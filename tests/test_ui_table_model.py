import pandas as pd

from dashboard.ui.table_model import build_identity_col, normalize_df, filter_non_active, select_display_df, dedupe


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


def test_normalize_df_handles_duplicate_last_seen_columns():
    df = pd.DataFrame(
        [
            {"timestamp": None, "created_at": "2026-02-27T10:00:00Z", "symbol": "NIFTY"},
            {"timestamp": "2026-02-27T10:05:00Z", "created_at": None, "symbol": "BANKNIFTY"},
        ]
    )

    out = normalize_df(df)

    assert list(out.columns).count("last_seen_ts") == 1
    assert pd.notna(out.iloc[0]["last_seen_ts"])
    assert pd.notna(out.iloc[1]["last_seen_ts"])


def test_normalize_df_does_not_backfill_entry_from_signal_price_when_stale():
    df = pd.DataFrame(
        [
            {
                "timestamp": "2026-03-02T03:35:04Z",
                "symbol": "NIFTY",
                "status": "PLANNING",
                "side": "BUY",
                "signal_price": 101.67,
                "entry_price": 101.67,
                "entry": None,
                "suggested_entry": None,
                "entry_status": "STALE_PRICE",
            }
        ]
    )
    out = normalize_df(df)
    assert pd.isna(out.iloc[0]["entry"])


def test_normalize_df_backfills_entry_from_suggested_entry_only_when_ok():
    df = pd.DataFrame(
        [
            {
                "timestamp": "2026-03-02T03:35:04Z",
                "symbol": "NIFTY",
                "status": "PLANNING",
                "side": "BUY",
                "entry": None,
                "suggested_entry": 44.3,
                "entry_status": "OK",
            }
        ]
    )
    out = normalize_df(df)
    assert float(out.iloc[0]["entry"]) == 44.3


def test_normalize_df_backfills_entry_for_price_mismatch_from_current_ltp():
    df = pd.DataFrame(
        [
            {
                "timestamp": "2026-03-02T03:35:04Z",
                "symbol": "NIFTY",
                "status": "PLANNING",
                "side": "BUY",
                "entry": None,
                "suggested_entry": None,
                "current_ltp": 565.0,
                "entry_status": "PRICE_MISMATCH",
            }
        ]
    )
    out = normalize_df(df)
    assert float(out.iloc[0]["entry"]) == 565.0


def test_select_display_df_formats_last_seen_ts_in_ist():
    df = pd.DataFrame(
        [
            {
                "last_seen_ts": "2026-03-02T03:35:04Z",
                "symbol": "NIFTY",
                "expiry_date": "2026-03-02",
                "strike": 24600,
                "opt_type": "PE",
                "side": "BUY",
                "status": "PLANNING",
                "entry": 44.3,
                "stop": 35.0,
                "target": 60.0,
                "confidence": 0.38,
                "trade_key": "k1",
            }
        ]
    )
    out = select_display_df(df, "advisory")
    assert out.iloc[0]["last_seen_ts"] == "2026-03-02 09:05:04 IST"


def test_dedupe_uses_stable_trade_identity_not_entry_price():
    df = pd.DataFrame(
        [
            {
                "last_seen_ts": "2026-03-02T03:35:04Z",
                "symbol": "NIFTY",
                "expiry_date": "2026-03-02",
                "strike": 24600,
                "opt_type": "PE",
                "side": "BUY",
                "status": "PLANNING",
                "entry": 101.7,
            },
            {
                "last_seen_ts": "2026-03-02T03:36:04Z",
                "symbol": "NIFTY",
                "expiry_date": "2026-03-02",
                "strike": 24600,
                "opt_type": "PE",
                "side": "BUY",
                "status": "PLANNING",
                "entry": 44.3,
            },
        ]
    )
    out = dedupe(df)
    assert len(out) == 1
    assert float(out.iloc[0]["entry"]) == 44.3


def test_build_identity_col_includes_ce_for_option_row():
    df = pd.DataFrame(
        [
            {
                "symbol": "NIFTY",
                "instrument_type": "OPT",
                "expiry_date": "2026-03-17",
                "strike": 23850,
                "right": "CE",
            }
        ]
    )

    out = build_identity_col(df)

    assert out.iloc[0]["identity"] == "NIFTY\n2026-03-17\n23850 CE"


def test_build_identity_col_includes_pe_from_tradingsymbol_suffix():
    df = pd.DataFrame(
        [
            {
                "symbol": "NIFTY",
                "instrument_type": "OPT",
                "expiry_date": "2026-03-17",
                "strike": 23850,
                "tradingsymbol": "NIFTY26MAR1723850PE",
            }
        ]
    )

    out = build_identity_col(df)

    assert out.iloc[0]["identity"] == "NIFTY\n2026-03-17\n23850 PE"


def test_build_identity_col_preserves_non_option_identity_behavior():
    df = pd.DataFrame(
        [
            {
                "symbol": "NIFTY",
                "instrument_type": "IDX",
                "expiry_date": "2026-03-17",
                "strike": 23850,
            }
        ]
    )

    out = build_identity_col(df)

    assert out.iloc[0]["identity"] == "NIFTY\n2026-03-17\n23850"
