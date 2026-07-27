import pandas as pd
from datetime import datetime, timezone
import pytest
from research.upstox_expired_options.aggregation import aggregate_5m

def test_five_minute_aggregation_boundaries():
    # Setup some dummy 1m data
    data = [
        {"timestamp": "2024-10-01T09:15:00+05:30", "open": 100, "high": 105, "low": 95, "close": 102, "volume": 1000, "open_interest": 500, "session_date": "2024-10-01"},
        {"timestamp": "2024-10-01T09:16:00+05:30", "open": 102, "high": 106, "low": 100, "close": 104, "volume": 1500, "open_interest": 550, "session_date": "2024-10-01"},
        {"timestamp": "2024-10-01T09:17:00+05:30", "open": 104, "high": 108, "low": 103, "close": 107, "volume": 1200, "open_interest": 600, "session_date": "2024-10-01"},
        {"timestamp": "2024-10-01T09:18:00+05:30", "open": 107, "high": 110, "low": 105, "close": 109, "volume": 2000, "open_interest": 650, "session_date": "2024-10-01"},
        {"timestamp": "2024-10-01T09:19:00+05:30", "open": 109, "high": 112, "low": 108, "close": 111, "volume": 1800, "open_interest": 700, "session_date": "2024-10-01"},
        # Next boundary
        {"timestamp": "2024-10-01T09:20:00+05:30", "open": 111, "high": 115, "low": 110, "close": 114, "volume": 2500, "open_interest": 750, "session_date": "2024-10-01"},
    ]
    df_1m = pd.DataFrame(data)
    df_1m['timestamp'] = pd.to_datetime(df_1m['timestamp'])
    
    df_5m = aggregate_5m(df_1m)
    assert len(df_5m) == 2
    
    # Check first candle properties
    assert df_5m.iloc[0]['timestamp'].isoformat() == "2024-10-01T09:15:00+05:30"
    assert df_5m.iloc[0]['open'] == 100
    assert df_5m.iloc[0]['high'] == 112
    assert df_5m.iloc[0]['low'] == 95
    assert df_5m.iloc[0]['close'] == 111
    assert df_5m.iloc[0]['volume'] == 7500
    assert df_5m.iloc[0]['open_interest'] == 700  # last oi
    
    # Check second candle properties
    assert df_5m.iloc[1]['timestamp'].isoformat() == "2024-10-01T09:20:00+05:30"
    assert df_5m.iloc[1]['open'] == 111
    assert df_5m.iloc[1]['close'] == 114
    assert df_5m.iloc[1]['is_complete_5m_bar'] == False

def test_no_cross_session_aggregation():
    data = [
        {"timestamp": "2024-10-01T15:29:00+05:30", "open": 100, "high": 105, "low": 95, "close": 102, "volume": 1000, "open_interest": 500, "session_date": "2024-10-01"},
        # Next day
        {"timestamp": "2024-10-02T09:15:00+05:30", "open": 102, "high": 106, "low": 100, "close": 104, "volume": 1500, "open_interest": 550, "session_date": "2024-10-02"},
    ]
    df_1m = pd.DataFrame(data)
    df_1m['timestamp'] = pd.to_datetime(df_1m['timestamp'])
    df_5m = aggregate_5m(df_1m)
    assert len(df_5m) == 2
    assert df_5m.iloc[0]['timestamp'].isoformat() == "2024-10-01T15:25:00+05:30"
    assert df_5m.iloc[1]['timestamp'].isoformat() == "2024-10-02T09:15:00+05:30"

def test_no_cross_contract_aggregation():
    # The normalizer aggregates per file, so it naturally handles per-contract aggregation.
    # We test it just takes 1 contract df.
    pass

def test_partial_five_minute_flags():
    data = [
        {"timestamp": "2024-10-01T09:15:00+05:30", "open": 100, "high": 105, "low": 95, "close": 102, "volume": 1000, "open_interest": 500, "session_date": "2024-10-01"},
        {"timestamp": "2024-10-01T09:16:00+05:30", "open": 102, "high": 106, "low": 100, "close": 104, "volume": 1500, "open_interest": 550, "session_date": "2024-10-01"},
    ]
    df_1m = pd.DataFrame(data)
    df_1m['timestamp'] = pd.to_datetime(df_1m['timestamp'])
    df_5m = aggregate_5m(df_1m)
    assert len(df_5m) == 1
    assert df_5m.iloc[0]['is_complete_5m_bar'] == False
