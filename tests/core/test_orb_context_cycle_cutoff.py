import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import config
import core.market_data
from core.market_data import fetch_live_market_data
from core.ohlc_buffer import OhlcBuffer

@pytest.fixture(autouse=True)
def isolated_global_state():
    real_buffer = OhlcBuffer()
    with patch.object(config.config, "SYMBOLS", ["NIFTY"]), \
         patch.dict(core.market_data._DATA_CACHE, {}, clear=True), \
         patch.dict(core.market_data._INDICATOR_LAST_UPDATE_EPOCH, {}, clear=True), \
         patch("core.market_data.ohlc_buffer", real_buffer):
        yield real_buffer

def create_valid_bars(start_dt, count=15):
    bars = []
    for i in range(count):
        ts = start_dt + timedelta(minutes=i)
        bars.append({
            "date": ts.isoformat(),
            "open": 100.0 + i,
            "high": 105.0 + i,
            "low": 95.0 + i,
            "close": 102.0 + i,
            "volume": 1000.0 + (i * 10)
        })
    return bars

def test_fetch_live_market_data_passes_frozen_cycle_cutoff_to_orb_context(isolated_global_state):
    tz = ZoneInfo("Asia/Kolkata")
    start_dt = datetime(2023, 1, 1, 9, 15, tzinfo=tz)
    cycle_cutoff = datetime(2023, 1, 1, 9, 30, 30, tzinfo=tz)
    forming_ts = datetime(2023, 1, 1, 9, 30, tzinfo=tz)
    
    real_buffer = isolated_global_state
    
    completed_bars = create_valid_bars(start_dt, count=15)
    forming_bar = {
        "date": forming_ts.isoformat(),
        "open": 115.0,
        "high": 120.0,
        "low": 110.0,
        "close": 118.0,
        "volume": 500.0
    }
    
    all_bars = completed_bars + [forming_bar]
    real_buffer.seed_bars("NIFTY", all_bars)
    
    with patch("core.market_data.now_ist", return_value=cycle_cutoff) as mock_now, \
         patch("core.market_data.now_utc_epoch", return_value=cycle_cutoff.timestamp()), \
         patch("core.market_data._orb_state_from_candles", wraps=core.market_data._orb_state_from_candles) as orb_spy, \
         patch("core.kite_client.kite_client.kite", MagicMock()), \
         patch("core.kite_client.kite_client.ensure", MagicMock()), \
         patch("core.kite_client.kite_client.resolve_index_token", return_value=256265):
        
        results = fetch_live_market_data()
        
        # Prove the clock contract:
        assert mock_now.call_count == 8
        
        # Prove ORB call
        assert orb_spy.call_count == 1
        call_kwargs = orb_spy.call_args[1]
        assert call_kwargs["now_dt"] is cycle_cutoff
        
        # Assert the exact timestamps
        passed_bars = orb_spy.call_args[0][1]
        assert len(passed_bars) == 15
        
        # Ensure we check the right key. OhlcBuffer get_completed_bars returns dicts. What key does it use? "timestamp" or "date"?
        # Let's check "timestamp" because OHL buffer normalizes it to "timestamp".
        expected_timestamps = [b["date"] for b in completed_bars]
        actual_timestamps = []
        for b in passed_bars:
            val = b.get("date") or b.get("ts") or b.get("timestamp")
            actual_timestamps.append(val.isoformat() if isinstance(val, datetime) else val)
        
        assert actual_timestamps == expected_timestamps
        assert actual_timestamps[0] == start_dt.isoformat()
        assert actual_timestamps[-1] == completed_bars[-1]["date"]
        assert len(set(actual_timestamps)) == len(actual_timestamps), "Timestamps must be unique"
        assert sorted(actual_timestamps) == actual_timestamps, "Timestamps must be strictly increasing"
        assert forming_bar["date"] not in actual_timestamps, "Forming bar timestamp must be excluded"
        assert "+05:30" in actual_timestamps[0], "Timestamps must be timezone-aware"

def test_warm_seed_path_passes_same_frozen_cutoff_to_orb_context(isolated_global_state):
    tz = ZoneInfo("Asia/Kolkata")
    start_dt = datetime(2023, 1, 1, 9, 15, tzinfo=tz)
    cycle_cutoff = datetime(2023, 1, 1, 9, 30, 30, tzinfo=tz)
    forming_ts = datetime(2023, 1, 1, 9, 30, tzinfo=tz)
    
    real_buffer = isolated_global_state
    
    completed_bars = create_valid_bars(start_dt, count=15)
    forming_bar = {
        "date": forming_ts.isoformat(),
        "open": 115.0,
        "high": 120.0,
        "low": 110.0,
        "close": 118.0,
        "volume": 500.0
    }
    all_bars = completed_bars + [forming_bar]
    
    def mock_history(*args, **kwargs):
        # kite client returns historical_data with "date" key containing a datetime object
        return [{"date": datetime.fromisoformat(b["date"]), "open": b["open"], "high": b["high"], "low": b["low"], "close": b["close"], "volume": b["volume"]} for b in all_bars]
        
    with patch("core.market_data.now_ist", return_value=cycle_cutoff) as mock_now, \
         patch("core.market_data.now_utc_epoch", return_value=cycle_cutoff.timestamp()), \
         patch("core.kite_client.kite_client.historical_data", side_effect=mock_history), \
         patch("core.market_data._orb_state_from_candles", wraps=core.market_data._orb_state_from_candles) as orb_spy, \
         patch("core.kite_client.kite_client.kite", MagicMock()), \
         patch("core.kite_client.kite_client.ensure", MagicMock()), \
         patch("core.kite_client.kite_client.resolve_index_token", return_value=256265):
        
        results = fetch_live_market_data()
        
        assert mock_now.call_count == 4
        
        assert len(real_buffer._bars.get("NIFTY", {})) > 0
        
        assert orb_spy.call_count == 1
        
        call_kwargs = orb_spy.call_args[1]
        assert call_kwargs["now_dt"] is cycle_cutoff
        
        passed_bars = orb_spy.call_args[0][1]
        assert len(passed_bars) == 15
        
        actual_timestamps = []
        for b in passed_bars:
            val = b.get("date") or b.get("ts") or b.get("timestamp")
            actual_timestamps.append(val.isoformat() if isinstance(val, datetime) else val)
        assert forming_bar["date"] not in actual_timestamps
        assert len(set(actual_timestamps)) == len(actual_timestamps)
        assert sorted(actual_timestamps) == actual_timestamps

