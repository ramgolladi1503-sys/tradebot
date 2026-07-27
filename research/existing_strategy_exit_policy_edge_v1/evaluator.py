from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import fmean, median
from typing import Iterable, Sequence

from research.existing_strategy_exit_policy_edge_v1.contract import ExitPolicy


@dataclass(frozen=True)
class OptionBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float

    def __post_init__(self) -> None:
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("option prices must be positive")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("invalid OHLC bar")


@dataclass(frozen=True)
class CostModel:
    entry_slippage_points: float = 0.0
    exit_slippage_points: float = 0.0
    fixed_round_trip_rupees: float = 0.0
    quantity: int = 1

    def __post_init__(self) -> None:
        if self.entry_slippage_points < 0 or self.exit_slippage_points < 0:
            raise ValueError("slippage cannot be negative")
        if self.fixed_round_trip_rupees < 0 or self.quantity <= 0:
            raise ValueError("invalid cost model")


@dataclass(frozen=True)
class TradeOutcome:
    strategy_id: str
    signal_id: str
    policy_id: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    exit_reason: str
    gross_points: float
    net_points: float
    gross_r: float
    net_r: float
    mfe_r: float
    mae_r: float


def evaluate_long_option_trade(
    *,
    strategy_id: str,
    signal_id: str,
    bars: Sequence[OptionBar],
    entry_price: float,
    risk_points: float,
    policy: ExitPolicy,
    costs: CostModel,
) -> TradeOutcome:
    """Evaluate a long CE/PE premium trade with conservative stop-first ordering."""
    if not bars:
        raise ValueError("bars cannot be empty")
    if entry_price <= 0 or risk_points <= 0:
        raise ValueError("entry_price and risk_points must be positive")

    effective_entry = entry_price + costs.entry_slippage_points
    target = effective_entry + (risk_points * policy.target_r)
    stop = effective_entry - (risk_points * policy.stop_r)
    deadline = bars[0].timestamp + timedelta(minutes=policy.max_hold_minutes)

    max_high = effective_entry
    min_low = effective_entry
    chosen_bar = bars[0]
    raw_exit = bars[0].close
    reason = "TIME_EXIT"

    for bar in bars:
        if bar.timestamp > deadline:
            break
        max_high = max(max_high, bar.high)
        min_low = min(min_low, bar.low)
        chosen_bar = bar
        stop_hit = bar.low <= stop
        target_hit = bar.high >= target
        if stop_hit:
            raw_exit = stop
            reason = "STOP"
            break
        if target_hit:
            raw_exit = target
            reason = "TARGET"
            break
        raw_exit = bar.close

    effective_exit = max(0.0, raw_exit - costs.exit_slippage_points)
    gross_points = raw_exit - effective_entry
    variable_cost_points = costs.fixed_round_trip_rupees / costs.quantity
    net_points = effective_exit - effective_entry - variable_cost_points
    mfe_r = (max_high - effective_entry) / risk_points
    mae_r = (min_low - effective_entry) / risk_points

    return TradeOutcome(
        strategy_id=strategy_id,
        signal_id=signal_id,
        policy_id=policy.policy_id,
        entry_time=bars[0].timestamp,
        exit_time=chosen_bar.timestamp,
        entry_price=effective_entry,
        exit_price=effective_exit,
        exit_reason=reason,
        gross_points=gross_points,
        net_points=net_points,
        gross_r=gross_points / risk_points,
        net_r=net_points / risk_points,
        mfe_r=mfe_r,
        mae_r=mae_r,
    )


def summarize(outcomes: Iterable[TradeOutcome]) -> dict[str, float | int]:
    rows = list(outcomes)
    if not rows:
        return {"trade_count": 0}
    net = [row.net_r for row in rows]
    wins = [value for value in net if value > 0]
    losses = [value for value in net if value < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "trade_count": len(rows),
        "win_rate": len(wins) / len(rows),
        "mean_net_r": fmean(net),
        "median_net_r": median(net),
        "profit_factor": gross_profit / gross_loss if gross_loss else float("inf"),
        "target_count": sum(row.exit_reason == "TARGET" for row in rows),
        "stop_count": sum(row.exit_reason == "STOP" for row in rows),
        "time_exit_count": sum(row.exit_reason == "TIME_EXIT" for row in rows),
    }


def remove_top_winners(outcomes: Iterable[TradeOutcome], count: int = 3) -> list[TradeOutcome]:
    rows = sorted(outcomes, key=lambda row: row.net_r, reverse=True)
    return rows[max(0, count):]
