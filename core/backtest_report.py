import pandas as pd
from config import config as cfg

def analyze_results(results_df: pd.DataFrame):
    if results_df is None or results_df.empty:
        return {"trades": 0}

    total = len(results_df)
    wins = (results_df["pl"] > 0).sum()
    losses = (results_df["pl"] <= 0).sum()
    win_rate = wins / total if total else 0

    avg_win = results_df.loc[results_df["pl"] > 0, "pl"].mean() if wins else 0
    avg_loss = results_df.loc[results_df["pl"] <= 0, "pl"].mean() if losses else 0
    profit_factor = abs(results_df.loc[results_df["pl"] > 0, "pl"].sum()) / abs(results_df.loc[results_df["pl"] <= 0, "pl"].sum()) if losses else float("inf")

    equity = results_df["capital"]
    peak = equity.cummax()
    drawdown = (equity - peak)
    max_dd = drawdown.min() if not drawdown.empty else 0

    return {
        "trades": total,
        "win_rate": round(win_rate, 4),
        "avg_win": round(avg_win, 2) if pd.notna(avg_win) else 0,
        "avg_loss": round(avg_loss, 2) if pd.notna(avg_loss) else 0,
        "profit_factor": round(profit_factor, 3) if profit_factor != float("inf") else "inf",
        "max_drawdown": round(max_dd, 2)
    }

def risk_summary(results_df: pd.DataFrame):
    """
    Walk-forward risk summary with per-strategy pass/fail flags.
    """
    if results_df is None or results_df.empty:
        return {"overall": {"trades": 0}, "strategies": []}
    df = results_df.copy()
    overall = analyze_results(df)
    # Thresholds
    min_trades = getattr(cfg, "WF_MIN_TRADES", 20)
    min_pf = getattr(cfg, "WF_MIN_PF", 1.2)
    min_wr = getattr(cfg, "WF_MIN_WIN_RATE", 0.45)
    max_dd = getattr(cfg, "WF_MAX_DD", -5000.0)

    strategies = []
    if "strategy" in df.columns:
        for strat, sdf in df.groupby("strategy"):
            stats = analyze_results(sdf)
            passed = True
            if stats.get("trades", 0) < min_trades:
                passed = False
            try:
                pf_val = stats.get("profit_factor")
                if pf_val == "inf":
                    pf_val = 9.99
                if float(pf_val) < min_pf:
                    passed = False
            except Exception:
                passed = False
            try:
                if float(stats.get("win_rate", 0)) < min_wr:
                    passed = False
            except Exception:
                passed = False
            try:
                if float(stats.get("max_drawdown", 0)) < max_dd:
                    passed = False
            except Exception:
                pass
            strategies.append({
                "strategy": strat,
                **stats,
                "passed": passed,
            })
    return {"overall": overall, "strategies": strategies}
