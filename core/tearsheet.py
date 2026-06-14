import pandas as pd
import numpy as np

def generate_tearsheet(trades_df: pd.DataFrame, initial_capital: float = 100000.0) -> dict:
    """
    Generate an elite backtest tearsheet containing advanced performance metrics.
    Expects trades_df to have at least: ['entry_idx', 'pl', 'outcome']
    """
    if trades_df is None or trades_df.empty:
        return {"error": "No trades to analyze."}

    trades_df = trades_df.copy()
    trades_df["cumulative_pl"] = trades_df["pl"].cumsum()
    trades_df["equity_curve"] = initial_capital + trades_df["cumulative_pl"]
    
    total_trades = len(trades_df)
    winners = trades_df[trades_df["pl"] > 0]
    losers = trades_df[trades_df["pl"] <= 0]
    
    win_rate = len(winners) / total_trades if total_trades > 0 else 0.0
    avg_win = winners["pl"].mean() if not winners.empty else 0.0
    avg_loss = losers["pl"].mean() if not losers.empty else 0.0
    
    profit_factor = abs(winners["pl"].sum() / losers["pl"].sum()) if not losers.empty and losers["pl"].sum() != 0 else float("inf")
    
    # Drawdown Calculation
    equity = trades_df["equity_curve"].values
    running_max = np.maximum.accumulate(equity)
    drawdowns = (equity - running_max) / running_max
    max_drawdown_pct = drawdowns.min() * 100.0  # percentage
    max_drawdown_abs = (equity - running_max).min()
    
    # Returns for Sharpe/Sortino (assuming each trade is an independent period for simplification)
    # In a real engine, we'd resample to daily equity to compute annualized Sharpe.
    returns = trades_df["pl"] / (initial_capital + trades_df["cumulative_pl"].shift(1).fillna(0))
    mean_return = returns.mean()
    std_return = returns.std()
    
    downside_returns = returns[returns < 0]
    downside_std = downside_returns.std()
    
    # Assuming 252 trading days and average trades per day is roughly known, we approximate.
    # For now, we calculate per-trade Sharpe and scale it.
    sharpe_ratio = (mean_return / std_return) if std_return != 0 else 0.0
    sortino_ratio = (mean_return / downside_std) if not pd.isna(downside_std) and downside_std != 0 else 0.0

    contamination_stats = {
        "synthetic_chain_used": trades_df["synthetic_chain_used"].sum() if "synthetic_chain_used" in trades_df else "unknown",
        "close_only_rows_used": trades_df["close_only_rows_used"].sum() if "close_only_rows_used" in trades_df else "unknown",
        "derived_geometry_rows": trades_df["derived_geometry_rows"].sum() if "derived_geometry_rows" in trades_df else "unknown",
        "missing_bid_ask_rows": trades_df["missing_bid_ask_rows"].sum() if "missing_bid_ask_rows" in trades_df else "unknown",
        "ambiguous_exit_rows": trades_df["ambiguous_exit_rows"].sum() if "ambiguous_exit_rows" in trades_df else "unknown",
    }

    after_cost_expectancy = trades_df["pl"].mean() if not trades_df.empty else 0.0
    
    oos_trades = trades_df[trades_df.get("is_oos", pd.Series([False]*len(trades_df)))]
    if not oos_trades.empty:
        oos_winners = oos_trades[oos_trades["pl"] > 0]
        oos_losers = oos_trades[oos_trades["pl"] <= 0]
        profit_factor_oos = abs(oos_winners["pl"].sum() / oos_losers["pl"].sum()) if not oos_losers.empty and oos_losers["pl"].sum() != 0 else float("inf")
    else:
        profit_factor_oos = None

    warnings = []
    if after_cost_expectancy <= 0:
        warnings.append("WARNING: Negative or zero after-cost expectancy! Win rate is irrelevant.")

    return {
        "total_trades": total_trades,
        "after_cost_expectancy": after_cost_expectancy,
        "profit_factor": profit_factor,
        "profit_factor_oos": profit_factor_oos,
        "win_rate_pct": win_rate * 100.0,
        "total_pnl": trades_df["pl"].sum(),
        "final_equity": trades_df["equity_curve"].iloc[-1],
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "max_drawdown_pct": max_drawdown_pct,
        "max_drawdown_abs": max_drawdown_abs,
        "sharpe_ratio_per_trade": sharpe_ratio,
        "sortino_ratio_per_trade": sortino_ratio,
        "outcomes": trades_df["outcome"].value_counts().to_dict(),
        "contamination": contamination_stats,
        "warnings": warnings
    }

def print_tearsheet(metrics: dict):
    if "error" in metrics:
        print(f"Tearsheet Error: {metrics['error']}")
        return

    print("="*40)
    print("      ELITE BACKTEST TEARSHEET      ")
    print("="*40)
    
    if metrics.get("warnings"):
        for w in metrics["warnings"]:
            print(f"\033[91m{w}\033[0m")
        print("="*40)

    print(f"Final Equity:       ${metrics['final_equity']:,.2f}")
    print(f"Total PnL:          ${metrics['total_pnl']:,.2f}")
    print(f"Total Trades:       {metrics['total_trades']}")
    print(f"Expectancy (Net):   ${metrics['after_cost_expectancy']:,.2f}")
    
    # Deprecate win rate if expectancy is bad
    if metrics['after_cost_expectancy'] > 0:
        print(f"Win Rate:           {metrics['win_rate_pct']:.2f}%")
    else:
        print(f"Win Rate:           {metrics['win_rate_pct']:.2f}% (IRRELEVANT - NEGATIVE EXPECTANCY)")
        
    print(f"Profit Factor:      {metrics['profit_factor']:.2f}")
    if metrics.get('profit_factor_oos') is not None:
        print(f"Profit Factor(OOS): {metrics['profit_factor_oos']:.2f}")
        
    print(f"Average Win:        ${metrics['avg_win']:,.2f}")
    print(f"Average Loss:       ${metrics['avg_loss']:,.2f}")
    print(f"Max Drawdown:       {metrics['max_drawdown_pct']:.2f}% (${metrics['max_drawdown_abs']:,.2f})")
    print(f"Sharpe (per trade): {metrics['sharpe_ratio_per_trade']:.4f}")
    print(f"Sortino (per trade):{metrics['sortino_ratio_per_trade']:.4f}")
    print("="*40)
    print("Outcomes Distribution:")
    for outcome, count in metrics["outcomes"].items():
        print(f"  {outcome}: {count}")
    print("="*40)
    if "contamination" in metrics:
        print("Contamination / Proxy Evidence:")
        for k, v in metrics["contamination"].items():
            print(f"  {k}: {v}")
        print("="*40)
