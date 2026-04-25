from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Callable, Optional, Dict, Any

import pandas as pd

warnings.warn(
    "core.replay_backtest_v2.ReplayBacktestEngineV2 is deprecated. "
    "Use core.replay_engine.ReplayEngine or scripts/validate_system.py as the canonical replay path.",
    DeprecationWarning,
    stacklevel=2,
)


@dataclass
class BacktestConfigV2:
    starting_capital: float = 100000.0
    fee_per_trade: float = 0.0
    horizon: int = 5
    latency_bars: int = 1
    base_slippage_bps: float = 4.0
    spread_slippage_mult: float = 0.50
    participation_rate: float = 0.10
    impact_bps_per_participation: float = 12.0
    min_fill_fraction: float = 0.25
    default_bar_volume: int = 1000

# (rest unchanged)
