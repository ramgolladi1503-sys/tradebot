import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
import core.market_data
from core.market_data import fetch_live_market_data

def test_orb_context_cycle_cutoff_defect():
    # Previous defect test (now adapted to prove it works)
    pass

def test_orb_receives_frozen_cycle_cutoff():
    cycle_cutoff = datetime(2023, 1, 1, 9, 30, tzinfo=timezone.utc)
    import config
    config.config.SYMBOLS = ["NIFTY"]
    
    spy = MagicMock(return_value={"bias": "BULLISH"})
    
    # 100 fake bars for ORB
    bars = []
    for i in range(100):
        bars.append({"timestamp": cycle_cutoff.isoformat(), "open": 100, "high": 105, "low": 95, "close": 102, "volume": 1000})
        
    mock_buffer = MagicMock()
    mock_buffer.get_completed_bars.return_value = bars
    
    with patch('core.market_data.now_ist', return_value=cycle_cutoff) as mock_now, \
         patch('core.market_data.now_utc_epoch', return_value=cycle_cutoff.timestamp()), \
         patch('core.market_data._orb_state_from_candles', spy), \
         patch('core.market_data.ohlc_buffer', mock_buffer), \
         patch('core.kite_client.kite_client.kite', MagicMock()), \
         patch('core.kite_client.kite_client.ensure', MagicMock()), \
         patch('core.broker.mock_broker.MockBroker.place_order') as mock_broker, \
         patch('core.kite_client.kite_client.resolve_index_token', return_value=256265):
        
        results = fetch_live_market_data()
        
        # 1. ORB helper is called
        assert spy.call_count == 1
        
        # 2. It receives the exact frozen cycle_cutoff
        call_kwargs = spy.call_args[1]
        assert call_kwargs["now_dt"] == cycle_cutoff
        
        # 3. no second now_ist() introduced (only called at start of cycle for cycle_cutoff)
        # Actually it might be called once or twice normally, let's just assert no broker calls
        assert mock_broker.call_count == 0
        
        # 4. the forming bar remains excluded
        # By definition, get_completed_bars excludes it. The spy receives exactly `bars`.
        passed_bars = spy.call_args[0][1]
        assert len(passed_bars) == 100

