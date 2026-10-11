from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class CandleBacktestConfig:
    timezone: str = "Asia/Kolkata"
    quantity: int = 1
    stop_pct: float = 0.20
    target_rr: float = 1.50
    max_hold_minutes: int = 30
    entry_slippage_bps: float = 50.0
    exit_slippage_bps: float = 50.0
    fixed_cost_per_order: float = 20.0
    entry_cost_bps: float = 0.0
    exit_cost_bps: float = 0.0
    max_volume_participation: float = 0.02
    require_session_catalog: bool = False
    intrabar_conflict_policy: str = "STOP_FIRST"
    fill_model_version: str = "option_candle_next_open_stop_first_v1"

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("quantity_must_be_positive")
        if not 0.0 < self.stop_pct < 1.0:
            raise ValueError("stop_pct_out_of_range")
        if self.target_rr <= 0.0:
            raise ValueError("target_rr_must_be_positive")
        if self.max_hold_minutes <= 0:
            raise ValueError("max_hold_minutes_must_be_positive")
        if self.entry_slippage_bps < 0.0 or self.exit_slippage_bps < 0.0:
            raise ValueError("slippage_bps_must_be_nonnegative")
        if self.fixed_cost_per_order < 0.0:
            raise ValueError("fixed_cost_per_order_must_be_nonnegative")
        if self.entry_cost_bps < 0.0 or self.exit_cost_bps < 0.0:
            raise ValueError("cost_bps_must_be_nonnegative")
        if not 0.0 < self.max_volume_participation <= 1.0:
            raise ValueError("max_volume_participation_out_of_range")
        if self.intrabar_conflict_policy != "STOP_FIRST":
            raise ValueError("only_stop_first_policy_is_supported")


@dataclass(frozen=True)
class CandleTrade:
    signal_id: str
    underlying: str
    direction: str
    contract_symbol: str
    option_type: str
    strike: float
    expiry: str
    signal_ts: str
    entry_ts: str
    exit_ts: str
    entry_reference_price: float
    entry_fill_price: float
    exit_reference_price: float
    exit_fill_price: float
    target_price: float
    stop_price: float
    exit_reason: str
    quantity: int
    gross_pnl: float
    entry_cost: float
    exit_cost: float
    total_costs: float
    net_pnl: float
    hold_minutes: float
    entry_fill_source: str
    exit_fill_source: str
    entry_slippage_bps: float
    exit_slippage_bps: float
    same_bar_ambiguity: bool
    catalog_time_authority: str
    evidence_level: str = "CANDLE_PROXY_ECONOMICS"
    executable_certification: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CandleBacktestResult:
    config: CandleBacktestConfig
    summary: dict[str, Any]
    trades: list[CandleTrade] = field(default_factory=list)
    rejections: list[dict[str, Any]] = field(default_factory=list)
    selections: list[dict[str, Any]] = field(default_factory=list)
