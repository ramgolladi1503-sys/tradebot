import pytest
import pandas as pd
from pathlib import Path
from datetime import datetime
from scripts.fetch_upstox_sensex_historical import save_parquet, get_target_dir

def test_save_parquet_strict_schema_and_zero_nulls(tmp_path):
    dates = pd.date_range("2026-10-01 09:15", "2026-10-01 15:30", freq="1min")
    df = pd.DataFrame({
        "timestamp": dates,
        "open": 72000.0,
        "high": 72150.0,
        "low": 71980.0,
        "close": 72100.0,
        "volume": 0.0,
        "oi": 0.0,
        "symbol": "SENSEX",
        "instrument_key": "BSE_INDEX|SENSEX"
    })

    target_file = tmp_path / "test_sensex.parquet"
    save_parquet(df, target_file)

    assert target_file.exists()
    assert target_file.stat().st_size > 0

    import pyarrow.parquet as pq
    table = pq.read_table(target_file)
    df_read = table.to_pandas()

    # Invariants
    assert len(df_read) == len(df)
    assert df_read["timestamp"].is_monotonic_increasing
    assert df_read.isnull().sum().sum() == 0
    assert list(df_read.columns) == [
        "timestamp", "open", "high", "low", "close", "volume", "oi", "symbol", "instrument_key"
    ]

def test_get_target_dir_external_drive_resolution():
    target = get_target_dir()
    assert isinstance(target, Path)
    # If external drive is mounted, it must target external drive
    if Path("/Volumes/TradeBot").exists():
        assert str(target).startswith("/Volumes/TradeBot")
    else:
        assert str(target).endswith("data/historical/sensex")
