"""Research-only option OHLCV backtesting.

This package intentionally produces candle-proxy economics, never executable
bid/ask certification.
"""

from .engine import run_option_candle_backtest
from .models import CandleBacktestConfig, CandleBacktestResult, CandleTrade

__all__ = [
    "CandleBacktestConfig",
    "CandleBacktestResult",
    "CandleTrade",
    "run_option_candle_backtest",
]
