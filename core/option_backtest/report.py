from __future__ import annotations

from collections import Counter
from typing import Any

from .models import OptionBacktestTrade


def summarize_backtest(
    *,
    signals_total: int,
    executable_signals: int,
    trades: list[OptionBacktestTrade],
    rejected_reasons: Counter[str],
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    wins = [trade for trade in trades if trade.pnl_value > 0]
    losses = [trade for trade in trades if trade.pnl_value < 0]
    total_pnl = sum(float(trade.pnl_value) for trade in trades)
    gross_profit = sum(float(trade.pnl_value) for trade in wins)
    gross_loss = abs(sum(float(trade.pnl_value) for trade in losses))
    avg_profit = gross_profit / len(wins) if wins else 0.0
    avg_loss = abs(sum(float(trade.pnl_value) for trade in losses) / len(losses)) if losses else 0.0
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for trade in trades:
        equity += float(trade.pnl_value)
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)
    slippage_impact = sum(float(trade.slippage_points) * float(trade.quantity) for trade in trades)
    profit_factor = None
    profit_factor_unbounded = False
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor_unbounded = True
    return {
        "signals_total": int(signals_total),
        "executable_signals": int(executable_signals),
        "trades_taken": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / len(trades)) if trades else 0.0,
        "total_pnl_value": total_pnl,
        "average_profit": avg_profit,
        "average_loss": avg_loss,
        "max_drawdown": abs(max_drawdown),
        "profit_factor": profit_factor,
        "profit_factor_unbounded": profit_factor_unbounded,
        "slippage_impact": slippage_impact,
        "rejected_reasons": dict(rejected_reasons),
        "diagnostics": diagnostics,
    }
