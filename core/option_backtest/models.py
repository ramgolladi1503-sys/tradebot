from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from enum import Enum


class ResearchMode(str, Enum):
    SYNTHETIC_RESEARCH = "SYNTHETIC_RESEARCH"
    PROXY_RESEARCH = "PROXY_RESEARCH"
    REAL_EXECUTABLE_RESEARCH = "REAL_EXECUTABLE_RESEARCH"


@dataclass(frozen=True)
class OptionBacktestConfig:
    symbol: str
    data_path: Path
    research_mode: ResearchMode = ResearchMode.PROXY_RESEARCH
    date_from: str | None = None
    date_to: str | None = None
    timezone: str = "Asia/Kolkata"
    output_dir: Path | None = None
    require_bid_ask: bool = True
    allow_derived_levels: bool = True
    derived_stop_pct: float = 0.12
    derived_target_rr: float = 1.5
    max_hold_minutes: int = 30
    quantity: int = 1
    fill_model_run_id: str = "option_backtest"

    def __post_init__(self):
        if self.research_mode == ResearchMode.REAL_EXECUTABLE_RESEARCH:
            object.__setattr__(self, 'allow_derived_levels', False)


@dataclass(frozen=True)
class OptionBacktestTrade:
    symbol: str
    side: str
    entry_ts: str
    exit_ts: str
    entry_reference_price: float
    entry_fill_price: float
    exit_price: float
    quantity: int
    target_price: float
    stop_price: float
    exit_reason: str
    pnl_points: float
    pnl_value: float
    slippage_points: float
    hold_minutes: float
    truth_quality: str
    geometry_source: str
    confidence_raw: float | None
    confidence_final: float | None
    decision_reason: str
    setup_id: str = "unknown"
    regime: str = "unknown"
    is_oos: bool = False


@dataclass(frozen=True)
class OptionBacktestResult:
    config: OptionBacktestConfig
    summary: dict[str, Any]
    trades: list[OptionBacktestTrade] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    sampled_decisions: list[dict[str, Any]] = field(default_factory=list)
