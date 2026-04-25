from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Callable, Optional, Dict, Any

import pandas as pd

warnings.warn(
    "core.replay_backtest_v3.ReplayBacktestEngineV3 is deprecated. "
    "Use core.replay_engine.ReplayEngine or scripts/validate_system.py as the canonical replay path.",
    DeprecationWarning,
    stacklevel=2,
)

from core.replay_backtest_v2 import ExecutionSimulatorV2, BacktestConfigV2

# (rest unchanged)
