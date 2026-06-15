import time
import pytest
from strategies.banknifty_intraday import generate_signal as banknifty_signal
from strategies.zero_hero import zero_hero_strategy as zero_hero_signal
from core.market_calendar import next_expiry

def test_banknifty_pure_signal():
    start_time = time.perf_counter()
    signal = banknifty_signal(ltp=45000, vwap=44900, bias="bullish", vwap_buffer=0.002, min_move=0.001)
    end_time = time.perf_counter()
    
    # Assert it returns a dictionary with explicit expected values
    assert signal == {'direction': 'BUY_CALL', 'reason': 'VWAP directional setup', 'score': 0.714, 'soft_flags': ['regime_unknown', 'bias_aligned'], 'setup_type': 'BREAKOUT', 'regime_path': 'UNKNOWN'}
    
    # Assert it runs purely in memory without I/O blocks (< 5ms)
    assert (end_time - start_time) < 0.005

def test_zero_hero_pure_signal():
    start_time = time.perf_counter()
    signal = zero_hero_signal(
        symbol="BANKNIFTY",
        ltp=20,
        premarket_bias="bullish",
        current_date=next_expiry("BANKNIFTY"),
        regime="EXPIRY_CONTEXT",
    )
    end_time = time.perf_counter()
    
    # Assert it explicitly returns a list of dictionaries with correct targets for a multi-leg strategy
    assert signal == [{'symbol': 'BANKNIFTY', 'strike': 0, 'option_type': 'CE', 'entry_price': 25.0, 'stop_loss': 20.0, 'target': 50.0, 'lot_size': 1, 'confidence': 60, 'confidence_reason': 'expiry_window_manual_advisory', 'regime_path': 'EXPIRY_CONTEXT', 'variant': 'expiry_context'}]
    
    # Assert no I/O blocks
    assert (end_time - start_time) < 0.005
