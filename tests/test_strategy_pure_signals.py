import statistics
import time

from core.market_calendar import next_expiry
from strategies.banknifty_intraday import generate_signal as banknifty_signal
from strategies.zero_hero import zero_hero_strategy as zero_hero_signal


def _median_runtime_seconds(fn, *, samples: int = 25) -> float:
    durations: list[float] = []
    for _ in range(samples):
        start_time = time.perf_counter()
        fn()
        durations.append(time.perf_counter() - start_time)
    return statistics.median(durations)

def test_banknifty_pure_signal():
    signal = banknifty_signal(
        ltp=45000,
        vwap=44900,
        bias="bullish",
        vwap_buffer=0.002,
        min_move=0.001,
        regime="TRENDING_UP",
    )
    median_runtime = _median_runtime_seconds(
        lambda: banknifty_signal(
            ltp=45000,
            vwap=44900,
            bias="bullish",
            vwap_buffer=0.002,
            min_move=0.001,
            regime="TRENDING_UP",
        )
    )
    
    assert signal is not None
    assert signal["direction"] == "BUY_CALL"
    assert signal["reason"] == "VWAP directional setup"
    assert signal["setup_type"] == "BREAKOUT"
    assert signal["regime_path"] == "TRENDING_UP"
    assert "bias_aligned" in signal["soft_flags"]
    
    # Assert typical runtime stays in-memory fast without single-sample scheduler noise (< 5ms median).
    assert median_runtime < 0.005

def test_zero_hero_pure_signal():
    signal = zero_hero_signal(
        symbol="BANKNIFTY",
        ltp=20,
        premarket_bias="bullish",
        current_date=next_expiry("BANKNIFTY"),
        regime="EXPIRY_CONTEXT",
    )
    median_runtime = _median_runtime_seconds(
        lambda: zero_hero_signal(
            symbol="BANKNIFTY",
            ltp=20,
            premarket_bias="bullish",
            current_date=next_expiry("BANKNIFTY"),
            regime="EXPIRY_CONTEXT",
        )
    )
    
    # Assert it explicitly returns a list of dictionaries with correct targets for a multi-leg strategy
    assert signal == [{'symbol': 'BANKNIFTY', 'strike': 0, 'option_type': 'CE', 'entry_price': 25.0, 'stop_loss': 20.0, 'target': 50.0, 'lot_size': 1, 'confidence': 60, 'confidence_reason': 'expiry_window_manual_advisory', 'regime_path': 'EXPIRY_CONTEXT', 'variant': 'expiry_context'}]
    
    # Assert typical runtime stays in-memory fast without single-sample scheduler noise (< 5ms median).
    assert median_runtime < 0.005
