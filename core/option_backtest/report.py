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
    wins = [trade for trade in trades if trade.net_pnl_value > 0]
    losses = [trade for trade in trades if trade.net_pnl_value < 0]
    total_net_pnl = sum(float(trade.net_pnl_value) for trade in trades)
    total_gross_pnl = sum(float(trade.gross_pnl_value) for trade in trades)
    total_costs = sum(float(trade.total_costs) for trade in trades)
    gross_profit = sum(float(trade.net_pnl_value) for trade in wins)
    gross_loss = abs(sum(float(trade.net_pnl_value) for trade in losses))
    avg_profit = gross_profit / len(wins) if wins else 0.0
    avg_loss = abs(sum(float(trade.net_pnl_value) for trade in losses) / len(losses)) if losses else 0.0
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for trade in trades:
        equity += float(trade.net_pnl_value)
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)
    slippage_impact = sum(
        (float(trade.entry_slippage_points) + float(trade.exit_slippage_points)) * float(trade.quantity)
        for trade in trades
    )
    profit_factor = None
    profit_factor_unbounded = False
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor_unbounded = True
    after_cost_expectancy = total_net_pnl / len(trades) if trades else 0.0

    warnings = []
    if after_cost_expectancy <= 0:
        warnings.append("WARNING: Negative or zero after-cost expectancy! Win rate is irrelevant.")

    oos_trades = [trade for trade in trades if trade.is_oos]
    oos_wins = [t for t in oos_trades if t.net_pnl_value > 0]
    oos_losses = [t for t in oos_trades if t.net_pnl_value < 0]
    oos_gross_profit = sum(float(t.net_pnl_value) for t in oos_wins)
    oos_gross_loss = abs(sum(float(t.net_pnl_value) for t in oos_losses))
    profit_factor_oos = None
    if oos_gross_loss > 0:
        profit_factor_oos = oos_gross_profit / oos_gross_loss

    setup_breakdown: dict[str, dict[str, float | int]] = {}
    for t in trades:
        if t.setup_id not in setup_breakdown:
            setup_breakdown[t.setup_id] = {"trades": 0, "pnl": 0.0}
        setup_breakdown[t.setup_id]["trades"] += 1
        setup_breakdown[t.setup_id]["pnl"] += float(t.net_pnl_value)

    regime_breakdown: dict[str, dict[str, float | int]] = {}
    for t in trades:
        if t.regime not in regime_breakdown:
            regime_breakdown[t.regime] = {"trades": 0, "pnl": 0.0}
        regime_breakdown[t.regime]["trades"] += 1
        regime_breakdown[t.regime]["pnl"] += float(t.net_pnl_value)

    return {
        "signals_total": int(signals_total),
        "executable_signals": int(executable_signals),
        "trades_taken": len(trades),
        "after_cost_expectancy": after_cost_expectancy,
        "profit_factor": profit_factor,
        "profit_factor_oos": profit_factor_oos,
        "setup_breakdown": setup_breakdown,
        "regime_breakdown": regime_breakdown,
        "win_rate": (len(wins) / len(trades)) if trades else 0.0,
        "wins": len(wins),
        "losses": len(losses),
        "gross_pnl_value": total_gross_pnl,
        "total_costs": total_costs,
        "total_pnl_value": total_net_pnl,
        "net_pnl_value": total_net_pnl,
        "average_profit": avg_profit,
        "average_loss": avg_loss,
        "max_drawdown": abs(max_drawdown),
        "profit_factor_unbounded": profit_factor_unbounded,
        "slippage_impact": slippage_impact,
        "rejected_reasons": dict(rejected_reasons),
        "diagnostics": diagnostics,
        "warnings": warnings,
    }
