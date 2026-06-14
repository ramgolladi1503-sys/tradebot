import time
import pytest
from strategies.banknifty_intraday import generate_signal as banknifty_signal
from strategies.zero_hero import zero_hero_strategy as zero_hero_signal

def test_banknifty_pure_signal():
    start_time = time.perf_counter()
    signal = banknifty_signal(ltp=45000, vwap=44900, bias="bullish", vwap_buffer=0.002, min_move=0.001)
    end_time = time.perf_counter()
    
    # Assert it returns a dictionary and doesn't execute orders
    assert isinstance(signal, dict)
    assert "direction" in signal
    
    # Assert it runs purely in memory without I/O blocks (< 5ms)
    assert (end_time - start_time) < 0.005

def test_zero_hero_pure_signal():
    start_time = time.perf_counter()
    signal = zero_hero_signal(symbol="BANKNIFTY", ltp=20, premarket_bias="bullish", regime="EXPIRY_CONTEXT")
    end_time = time.perf_counter()
    
    # Signal can be None, dict, or list of dicts
    if signal is not None:
        assert isinstance(signal, (dict, list))
    
    # Assert no I/O blocks
    assert (end_time - start_time) < 0.005
