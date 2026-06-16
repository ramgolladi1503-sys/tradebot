import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd
import scripts.fetch_kite_intraday as fetch_module

from scripts.fetch_kite_intraday import (
    _parse_dt,
    fetch_kite_candles,
    _normalize_candles,
    build_kite_intraday_history,
)

def test_parse_dt():
    """
    Edge purpose:
    Preserve UTC parsing for historical feed boundaries so downstream candle
    slicing does not drift on timezone-naive input.
    """
    dt = _parse_dt("2023-01-01T10:00:00Z")
    assert dt.tzinfo == timezone.utc
    assert dt.year == 2023

def test_normalize_candles():
    """
    Edge purpose:
    Verify normalized output always carries the canonical intraday schema used
    by the rest of the offline pipeline.
    """
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

def test_fetch_kite_candles(monkeypatch):
    """
    Edge purpose:
    Confirm the fetcher chunks the historical request through the Kite client
    and returns only normalized candle rows for a bounded offline replay.
    """
    calls = []

    class FakeKiteClient:
        def ensure(self):
            calls.append(("ensure",))

        def historical_data(self, instrument_token, start_dt, end_dt, interval=None):
            calls.append(
                (
                    "historical_data",
                    instrument_token,
                    start_dt,
                    end_dt,
                    interval,
                )
            )
            return {
                "candles": [
                    {
                        "date": "2023-01-01T10:00:00+00:00",
                        "open": 100,
                        "high": 105,
                        "low": 95,
                        "close": 102,
                        "volume": 1000,
                    }
                ]
            }

    monkeypatch.setattr(fetch_module, "kite_client", FakeKiteClient())
    
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
    assert calls[0] == ("ensure",)
    assert calls[1][0] == "historical_data"
    assert calls[1][1] == 12345
    assert calls[1][4] == "5minute"

def test_build_kite_intraday_history(monkeypatch, tmp_path):
    """
    Edge purpose:
    Prove the file writer produces the canonical intraday CSV contract without
    requiring live broker access or changing freshness/feed behavior.
    """
    monkeypatch.setattr(fetch_module, "_resolve_index_token", lambda symbol: 12345)
    monkeypatch.setattr(
        fetch_module,
        "fetch_kite_candles",
        lambda **kwargs: [
            {
                "date": "2023-01-01T10:00:00+00:00",
                "open": 100,
                "high": 105,
                "low": 95,
                "close": 102,
                "volume": 1000,
            }
        ],
    )
    
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

def test_fetch_kite_candles_rejects_invalid_window():
    """
    Edge purpose:
    Fail closed when the caller passes an inverted time window, preventing a
    misleading 'successful' history fetch.
    """
    start_dt = datetime(2023, 1, 2, tzinfo=timezone.utc)
    end_dt = datetime(2023, 1, 1, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="end_dt must be greater than start_dt"):
        fetch_kite_candles(
            instrument_token=12345,
            interval="5minute",
            start_dt=start_dt,
            end_dt=end_dt,
        )
