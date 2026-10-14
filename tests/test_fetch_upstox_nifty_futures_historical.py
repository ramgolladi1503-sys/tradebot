import pytest
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from scripts.fetch_upstox_nifty_futures_historical import build_continuous_futures, save_parquet

def test_build_continuous_futures_stitching_and_roll_logic(tmp_path):
    # Simulate two consecutive monthly contracts
    # Contract 1: expires 2026-08-27 at 15:30
    dates_c1 = pd.date_range("2026-08-01 09:15", "2026-08-27 15:30", freq="1h")
    df1 = pd.DataFrame({
        "timestamp": dates_c1,
        "open": 24000.0,
        "high": 24100.0,
        "low": 23900.0,
        "close": 24050.0,
        "volume": 1000.0,
        "oi": 50000.0,
        "contract": "NIFTY FUT 27 AUG 26",
        "expiry": "2026-08-27",
        "instrument_key": "NSE_FO|111|27-08-2026"
    })

    # Contract 2: expires 2026-09-24 at 15:30 (active during Aug & Sep)
    dates_c2 = pd.date_range("2026-08-15 09:15", "2026-09-24 15:30", freq="1h")
    df2 = pd.DataFrame({
        "timestamp": dates_c2,
        "open": 24200.0,
        "high": 24300.0,
        "low": 24100.0,
        "close": 24250.0,
        "volume": 800.0,
        "oi": 60000.0,
        "contract": "NIFTY FUT 24 SEP 26",
        "expiry": "2026-09-24",
        "instrument_key": "NSE_FO|222|24-09-2026"
    })

    # Build continuous
    cont = build_continuous_futures([df1, df2], "1minute")

    # Invariants
    assert not cont.empty
    assert len(cont) > 0
    # Must be monotonically increasing timestamps
    assert cont["timestamp"].is_monotonic_increasing
    # Must have zero duplicates
    assert cont["timestamp"].is_unique
    # Check that up to 2026-08-27 15:30, contract is df1
    cutoff = datetime(2026, 8, 27, 15, 30)
    pre_cutoff = cont[cont["timestamp"] <= cutoff]
    assert all(pre_cutoff["contract"] == "NIFTY FUT 27 AUG 26")
    # Check that after 2026-08-27 15:30, contract is df2
    post_cutoff = cont[cont["timestamp"] > cutoff]
    assert all(post_cutoff["contract"] == "NIFTY FUT 24 SEP 26")

def test_save_parquet_and_schema_fidelity(tmp_path):
    dates = pd.date_range("2026-09-01 09:15", "2026-09-01 15:30", freq="1min")
    df = pd.DataFrame({
        "timestamp": dates,
        "open": 24500.0,
        "high": 24550.0,
        "low": 24480.0,
        "close": 24520.0,
        "volume": 250.0,
        "oi": 80000.0,
        "contract": "NIFTY FUT 24 SEP 26",
        "expiry": "2026-09-24",
        "instrument_key": "NSE_FO|222|24-09-2026"
    })

    target_file = tmp_path / "test_future.parquet"
    save_parquet(df, target_file)

    assert target_file.exists()
    assert target_file.stat().st_size > 0

    import pyarrow.parquet as pq
    table = pq.read_table(target_file)
    df_read = table.to_pandas()
    assert len(df_read) == len(df)
    assert df_read.isnull().sum().sum() == 0
    assert list(df_read.columns) == list(df.columns)
