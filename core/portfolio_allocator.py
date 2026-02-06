import pandas as pd
import numpy as np

REGIME_ALLOWED_STRATEGIES = {
    "TRENDING": ["directional", "momentum"],
    "RANGING": ["mean_reversion"],
    "VOLATILE": ["vol_expansion"],
    "LOW_VOL": ["mean_reversion"]
}

MAX_PER_STRATEGY = 0.35

def compute_strategy_metrics(trade_log, window=30):
    recent = trade_log.tail(window)
    return {
        "win_rate": recent["win"].mean(),
        "avg_pnl": recent["pnl"].mean(),
        "sharpe": recent["pnl"].mean() / (recent["pnl"].std()+1e-6)
    }

def strategy_weight(metrics):
    score = (0.4*metrics["win_rate"] + 0.4*np.tanh(metrics["sharpe"]) + 0.2*np.tanh(metrics["avg_pnl"]/1000))
    return max(score,0)

def allocate_capital(regime, trade_logs_by_strategy, total_capital):
    allowed = REGIME_ALLOWED_STRATEGIES.get(regime, [])
    raw_weights = {}
    for strat in allowed:
        metrics = compute_strategy_metrics(trade_logs_by_strategy[strat])
        raw_weights[strat] = strategy_weight(metrics)
    total_weight = sum(raw_weights.values())
    if total_weight == 0:
        return {"CASH": total_capital}
    allocations = {}
    for strat, w in raw_weights.items():
        allocation = min((w/total_weight)*total_capital, MAX_PER_STRATEGY*total_capital)
        allocations[strat] = allocation
    return allocations

