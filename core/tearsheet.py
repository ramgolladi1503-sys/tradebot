from __future__ import annotations

import numpy as np
import pandas as pd


def _profit_factor(pnl: pd.Series) -> float:
    winners = pnl[pnl > 0]
    losers = pnl[pnl <= 0]
    loss_sum = float(losers.sum())
    if loss_sum == 0.0:
        return float("inf")
    return abs(float(winners.sum()) / loss_sum)


def _drawdown_metrics(pnl: pd.Series, initial_capital: float) -> tuple[float, float]:
    cumulative = pnl.cumsum()
    equity = initial_capital + cumulative
    running_max = np.maximum.accumulate(equity.to_numpy(dtype=float))
    drawdowns_abs = equity.to_numpy(dtype=float) - running_max
    drawdowns_pct = np.divide(
        drawdowns_abs,
        running_max,
        out=np.zeros_like(drawdowns_abs, dtype=float),
        where=running_max != 0,
    )
    return float(drawdowns_pct.min() * 100.0), float(drawdowns_abs.min())


def _subset_metrics(
    trades_df: pd.DataFrame,
    *,
    initial_capital: float,
) -> dict[str, float | int]:
    pnl = trades_df["pl"].astype(float)
    winners = pnl[pnl > 0]
    losers = pnl[pnl <= 0]
    max_drawdown_pct, max_drawdown_abs = _drawdown_metrics(pnl, initial_capital)
    return {
        "trade_count": int(len(trades_df)),
        "expectancy": float(pnl.mean()) if len(pnl) else 0.0,
        "profit_factor": _profit_factor(pnl),
        "win_rate_pct": float((pnl > 0).mean() * 100.0) if len(pnl) else 0.0,
        "total_pnl": float(pnl.sum()),
        "avg_win": float(winners.mean()) if not winners.empty else 0.0,
        "avg_loss": float(losers.mean()) if not losers.empty else 0.0,
        "max_drawdown_pct": max_drawdown_pct,
        "max_drawdown_abs": max_drawdown_abs,
    }


def generate_tearsheet(
    trades_df: pd.DataFrame,
    initial_capital: float = 100000.0,
) -> dict:
    """Generate performance metrics from an already cost-adjusted trade ledger."""
    if trades_df is None or trades_df.empty:
        return {"error": "No trades to analyze."}
    if "pl" not in trades_df.columns:
        raise ValueError("trades_df must contain a 'pl' column")

    trades_df = trades_df.copy()
    trades_df["pl"] = pd.to_numeric(trades_df["pl"], errors="raise")
    trades_df["cumulative_pl"] = trades_df["pl"].cumsum()
    trades_df["equity_curve"] = initial_capital + trades_df["cumulative_pl"]

    all_metrics = _subset_metrics(trades_df, initial_capital=initial_capital)

    returns = trades_df["pl"] / (
        initial_capital + trades_df["cumulative_pl"].shift(1).fillna(0)
    )
    mean_return = float(returns.mean())
    std_return = float(returns.std())
    downside_returns = returns[returns < 0]
    downside_std = float(downside_returns.std()) if not downside_returns.empty else 0.0
    sharpe_ratio = mean_return / std_return if std_return != 0 else 0.0
    sortino_ratio = (
        mean_return / downside_std
        if not pd.isna(downside_std) and downside_std != 0
        else 0.0
    )

    contamination_stats = {
        "synthetic_chain_used": trades_df["synthetic_chain_used"].sum()
        if "synthetic_chain_used" in trades_df
        else "unknown",
        "close_only_rows_used": trades_df["close_only_rows_used"].sum()
        if "close_only_rows_used" in trades_df
        else "unknown",
        "derived_geometry_rows": trades_df["derived_geometry_rows"].sum()
        if "derived_geometry_rows" in trades_df
        else "unknown",
        "missing_bid_ask_rows": trades_df["missing_bid_ask_rows"].sum()
        if "missing_bid_ask_rows" in trades_df
        else "unknown",
        "ambiguous_exit_rows": trades_df["ambiguous_exit_rows"].sum()
        if "ambiguous_exit_rows" in trades_df
        else "unknown",
    }

    if "is_oos" in trades_df.columns:
        oos_mask = trades_df["is_oos"].fillna(False).astype(bool)
    else:
        oos_mask = pd.Series(False, index=trades_df.index, dtype=bool)
    oos_trades = trades_df.loc[oos_mask]
    oos_metrics = (
        _subset_metrics(oos_trades, initial_capital=initial_capital)
        if not oos_trades.empty
        else None
    )

    warnings: list[str] = []
    if float(all_metrics["expectancy"]) <= 0:
        warnings.append(
            "WARNING: Negative or zero after-cost expectancy! Win rate is irrelevant."
        )
    if oos_metrics is not None and float(oos_metrics["expectancy"]) <= 0:
        warnings.append("WARNING: Negative or zero OOS after-cost expectancy.")

    return {
        "total_trades": all_metrics["trade_count"],
        "after_cost_expectancy": all_metrics["expectancy"],
        "profit_factor": all_metrics["profit_factor"],
        "profit_factor_oos": oos_metrics["profit_factor"]
        if oos_metrics is not None
        else None,
        "after_cost_expectancy_oos": oos_metrics["expectancy"]
        if oos_metrics is not None
        else None,
        "oos_trade_count": oos_metrics["trade_count"]
        if oos_metrics is not None
        else 0,
        "win_rate_pct_oos": oos_metrics["win_rate_pct"]
        if oos_metrics is not None
        else None,
        "total_pnl_oos": oos_metrics["total_pnl"]
        if oos_metrics is not None
        else None,
        "max_drawdown_pct_oos": oos_metrics["max_drawdown_pct"]
        if oos_metrics is not None
        else None,
        "max_drawdown_abs_oos": oos_metrics["max_drawdown_abs"]
        if oos_metrics is not None
        else None,
        "win_rate_pct": all_metrics["win_rate_pct"],
        "total_pnl": all_metrics["total_pnl"],
        "final_equity": float(trades_df["equity_curve"].iloc[-1]),
        "avg_win": all_metrics["avg_win"],
        "avg_loss": all_metrics["avg_loss"],
        "max_drawdown_pct": all_metrics["max_drawdown_pct"],
        "max_drawdown_abs": all_metrics["max_drawdown_abs"],
        "sharpe_ratio_per_trade": sharpe_ratio,
        "sortino_ratio_per_trade": sortino_ratio,
        "outcomes": trades_df["outcome"].value_counts().to_dict()
        if "outcome" in trades_df.columns
        else {},
        "contamination": contamination_stats,
        "warnings": warnings,
    }


def print_tearsheet(metrics: dict) -> None:
    if "error" in metrics:
        print(f"Tearsheet Error: {metrics['error']}")
        return

    print("=" * 40)
    print("      ELITE BACKTEST TEARSHEET      ")
    print("=" * 40)

    if metrics.get("warnings"):
        for warning in metrics["warnings"]:
            print(f"\033[91m{warning}\033[0m")
        print("=" * 40)

    print(f"Final Equity:       ${metrics['final_equity']:,.2f}")
    print(f"Total PnL:          ${metrics['total_pnl']:,.2f}")
    print(f"Total Trades:       {metrics['total_trades']}")
    print(f"Expectancy (Net):   ${metrics['after_cost_expectancy']:,.2f}")

    suffix = "" if metrics["after_cost_expectancy"] > 0 else " (IRRELEVANT - NEGATIVE EXPECTANCY)"
    print(f"Win Rate:           {metrics['win_rate_pct']:.2f}%{suffix}")
    print(f"Profit Factor:      {metrics['profit_factor']:.2f}")
    if metrics.get("profit_factor_oos") is not None:
        print(f"Profit Factor(OOS): {metrics['profit_factor_oos']:.2f}")
        print(
            f"Expectancy (OOS):   ${metrics['after_cost_expectancy_oos']:,.2f}"
        )

    print(f"Average Win:        ${metrics['avg_win']:,.2f}")
    print(f"Average Loss:       ${metrics['avg_loss']:,.2f}")
    print(
        f"Max Drawdown:       {metrics['max_drawdown_pct']:.2f}% "
        f"(${metrics['max_drawdown_abs']:,.2f})"
    )
    print(f"Sharpe (per trade): {metrics['sharpe_ratio_per_trade']:.4f}")
    print(f"Sortino (per trade):{metrics['sortino_ratio_per_trade']:.4f}")
    print("=" * 40)
    print("Outcomes Distribution:")
    for outcome, count in metrics["outcomes"].items():
        print(f"  {outcome}: {count}")
    print("=" * 40)
    if "contamination" in metrics:
        print("Contamination / Proxy Evidence:")
        for key, value in metrics["contamination"].items():
            print(f"  {key}: {value}")
        print("=" * 40)
