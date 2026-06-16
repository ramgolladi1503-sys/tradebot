import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd

from scripts.fetch_kite_intraday import (
    _parse_dt,
    fetch_kite_candles,
    _normalize_candles,
    build_kite_intraday_history,
)

def test_parse_dt():
    dt = _parse_dt("2023-01-01T10:00:00Z")
    assert dt.tzinfo == timezone.utc
    assert dt.year == 2023

def test_normalize_candles():
    rows = [
        {"date": "2023-01-01T10:00:00+00:00", "open": 100, "high": 105, "low": 95, "close": 102, "volume": 1000},
        {"date": "2023-01-01T10:05:00+00:00", "open": 102, "high": 110, "low": 101, "close": 108, "volume": 2000},
    ]
    df = _normalize_candles(rows, "NIFTY")
    assert len(df) == 2
    assert "timestamp" in df.columns
    assert "symbol" in df.columns
    assert df["symbol"].iloc[0] == "NIFTY"
    assert df["open"].iloc[0] == 100

@patch("scripts.fetch_kite_intraday.kite_client")
def test_fetch_kite_candles(mock_client):
    mock_client.historical_data.return_value = {
        "candles": [
            {"date": "2023-01-01T10:00:00+00:00", "open": 100, "high": 105, "low": 95, "close": 102, "volume": 1000}
        ]
    }
    
    start_dt = datetime(2023, 1, 1, tzinfo=timezone.utc)
    end_dt = datetime(2023, 1, 2, tzinfo=timezone.utc)
    
    rows = fetch_kite_candles(
        instrument_token=12345,
        interval="5minute",
        start_dt=start_dt,
        end_dt=end_dt,
        chunk_days=60
    )
    
    assert len(rows) == 1
    assert rows[0]["open"] == 100
    mock_client.ensure.assert_called_once()

@patch("scripts.fetch_kite_intraday._resolve_index_token")
@patch("scripts.fetch_kite_intraday.fetch_kite_candles")
def test_build_kite_intraday_history(mock_fetch, mock_resolve, tmp_path):
    mock_resolve.return_value = 12345
    mock_fetch.return_value = [
        {"date": "2023-01-01T10:00:00+00:00", "open": 100, "high": 105, "low": 95, "close": 102, "volume": 1000}
    ]
    
    start_dt = datetime(2023, 1, 1, tzinfo=timezone.utc)
    end_dt = datetime(2023, 1, 2, tzinfo=timezone.utc)
    
    report = build_kite_intraday_history(
        symbol="NIFTY",
        interval="5minute",
        start_dt=start_dt,
        end_dt=end_dt,
        output_dir=tmp_path,
        chunk_days=60
    )
    
    assert report["symbol"] == "NIFTY"
    assert report["rows"] == 1
    
    out_file = Path(report["output_path"])
    assert out_file.exists()
    
    df = pd.read_csv(out_file)
    assert len(df) == 1
    assert "symbol" in df.columns
    assert df["symbol"].iloc[0] == "NIFTY"
