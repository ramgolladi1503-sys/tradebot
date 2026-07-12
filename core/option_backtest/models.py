from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ResearchMode(str, Enum):
    SYNTHETIC_RESEARCH = "SYNTHETIC_RESEARCH"
    PROXY_RESEARCH = "PROXY_RESEARCH"
    REAL_EXECUTABLE_RESEARCH = "REAL_EXECUTABLE_RESEARCH"


@dataclass(frozen=True)
class OptionBacktestCostConfig:
    version: str = "phase3_v1"
    brokerage_per_order: float = 0.5
    exchange_fee_per_contract: float = 0.05
    tax_per_contract: float = 0.05
    other_fee_per_order: float = 0.0


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
    bar_interval_minutes: int = 1
    allow_missing_bars: bool = True
    require_contract_metadata: bool | None = None
    require_dataset_provenance: bool | None = None
    require_quote_timestamps: bool | None = None
    max_quote_age_seconds: float | None = None
    require_signal_timing_provenance: bool | None = None
    cost_config: OptionBacktestCostConfig = field(default_factory=OptionBacktestCostConfig)

    def __post_init__(self):
        if self.research_mode == ResearchMode.REAL_EXECUTABLE_RESEARCH:
            object.__setattr__(self, "allow_derived_levels", False)
        if self.bar_interval_minutes <= 0:
            raise ValueError("bar_interval_minutes_must_be_positive")
        strict_replay = self.research_mode == ResearchMode.REAL_EXECUTABLE_RESEARCH
        if strict_replay:
            object.__setattr__(self, "allow_missing_bars", False)
        if self.require_contract_metadata is None:
            object.__setattr__(self, "require_contract_metadata", strict_replay)
        if self.require_dataset_provenance is None:
            object.__setattr__(self, "require_dataset_provenance", strict_replay)
        if self.require_quote_timestamps is None:
            object.__setattr__(self, "require_quote_timestamps", strict_replay)
        if self.require_signal_timing_provenance is None:
            object.__setattr__(self, "require_signal_timing_provenance", strict_replay)
        if self.max_quote_age_seconds is None and strict_replay:
            object.__setattr__(self, "max_quote_age_seconds", 60.0)

    @property
    def strict_replay_contract(self) -> bool:
        return bool(
            self.research_mode == ResearchMode.REAL_EXECUTABLE_RESEARCH
            or self.require_contract_metadata
            or self.require_dataset_provenance
            or self.require_quote_timestamps
            or not self.allow_missing_bars
        )


@dataclass(frozen=True)
class OptionBacktestTrade:
    symbol: str
    source_symbol: str
    underlying: str
    option_type: str
    strike: float
    expiry: str
    provider: str
    dataset_hash: str
    bar_interval: str
    side: str
    entry_ts: str
    exit_ts: str
    entry_reference_price: float
    entry_fill_price: float
    exit_reference_price: float
    exit_price: float
    entry_bid: float | None
    entry_ask: float | None
    exit_bid: float | None
    exit_ask: float | None
    entry_quote_side: str
    exit_quote_side: str
    quantity: int
    entry_fill_qty: int
    exit_fill_qty: int
    target_price: float
    stop_price: float
    exit_reason: str
    pnl_points: float
    gross_pnl_value: float
    total_costs: float
    net_pnl_value: float
    entry_costs: float
    exit_costs: float
    entry_slippage_points: float
    exit_slippage_points: float
    hold_minutes: float
    truth_quality: str
    geometry_source: str
    confidence_raw: float | None
    confidence_final: float | None
    decision_reason: str
    feature_cutoff_ts: str | None = None
    signal_ts: str | None = None
    earliest_entry_ts: str | None = None
    timing_ambiguity: bool = False
    exit_fill_source: str = "unknown"
    cost_model_version: str = "unknown"
    fill_model_run_id: str = "unknown"
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
