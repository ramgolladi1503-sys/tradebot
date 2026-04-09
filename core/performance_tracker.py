from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List


@dataclass
class TradeRecord:
    symbol: str
    strategy: str
    entry_price: float
    exit_price: float
    quantity: int
    pnl: float
    expected_slippage: float
    actual_slippage: float


@dataclass
class PerformanceMetrics:
    total_trades: int
    win_rate: float
    avg_pnl: float
    expectancy: float
    avg_slippage_error: float


class PerformanceTracker:
    def __init__(self):
        self.trades: List[TradeRecord] = []

    def record_trade(self, record: TradeRecord):
        self.trades.append(record)

    def compute(self) -> PerformanceMetrics:
        if not self.trades:
            return PerformanceMetrics(0, 0.0, 0.0, 0.0, 0.0)

        total = len(self.trades)
        wins = sum(1 for t in self.trades if t.pnl > 0)
        avg_pnl = sum(t.pnl for t in self.trades) / total
        expectancy = avg_pnl
        slippage_error = sum(abs(t.actual_slippage - t.expected_slippage) for t in self.trades) / total

        return PerformanceMetrics(
            total_trades=total,
            win_rate=wins / total,
            avg_pnl=avg_pnl,
            expectancy=expectancy,
            avg_slippage_error=slippage_error,
        )

    def strategy_breakdown(self) -> dict[str, float]:
        result = {}
        for t in self.trades:
            result.setdefault(t.strategy, []).append(t.pnl)
        return {k: sum(v)/len(v) for k, v in result.items()}
