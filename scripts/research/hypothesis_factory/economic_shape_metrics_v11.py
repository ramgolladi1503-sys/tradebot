#!/usr/bin/env python3
"""
Economic-Shape Metrics and Control Severity Module V11 (TradeBot / MROS)
Provides reusable pure functions for computing R-multiple, expectancy, payoff ratio, 
and classifying negative control severity without mutating global state.
"""
import numpy as np
from typing import Dict, List, Any

def compute_trade_shape_metrics(returns_bps: List[float], cost_bps: float = 3.0, initial_risk_bps: float = 20.0) -> Dict[str, Any]:
    if not returns_bps:
        return {
            "trade_count": 0,
            "win_rate": 0.0,
            "loss_rate": 0.0,
            "expectancy_bps": 0.0,
            "cost_adjusted_expectancy_bps": 0.0,
            "average_win_bps": 0.0,
            "average_loss_bps": 0.0,
            "payoff_ratio": 0.0,
            "profit_factor": 0.0,
            "average_R": 0.0,
            "median_R": 0.0
        }

    arr = np.array(returns_bps)
    wins = arr[arr > 0]
    losses = arr[arr < 0]

    n = len(arr)
    win_cnt = len(wins)
    loss_cnt = len(losses)

    win_rate = win_cnt / n
    loss_rate = loss_cnt / n

    avg_win = float(np.mean(wins)) if win_cnt > 0 else 0.0
    avg_loss = float(np.mean(losses)) if loss_cnt > 0 else 0.0

    exp_gross = float(np.mean(arr))
    exp_net = exp_gross - cost_bps

    payoff = (avg_win / abs(avg_loss)) if abs(avg_loss) > 1e-6 else 1.0
    
    sum_win = float(np.sum(wins)) if win_cnt > 0 else 0.0
    sum_loss = abs(float(np.sum(losses))) if loss_cnt > 0 else 1e-6
    pf = sum_win / sum_loss

    r_multiples = arr / initial_risk_bps
    avg_r = float(np.mean(r_multiples))
    med_r = float(np.median(r_multiples))

    return {
        "trade_count": n,
        "win_rate": win_rate,
        "loss_rate": loss_rate,
        "expectancy_bps": exp_gross,
        "cost_adjusted_expectancy_bps": exp_net,
        "average_win_bps": avg_win,
        "average_loss_bps": avg_loss,
        "payoff_ratio": payoff,
        "profit_factor": pf,
        "average_R": avg_r,
        "median_R": med_r
    }

def classify_negative_control_severity(real_metrics: Dict[str, Any], control_metrics: Dict[str, Any]) -> Dict[str, Any]:
    real_exp = real_metrics.get("cost_adjusted_expectancy_bps", 0.0)
    ctrl_exp = control_metrics.get("cost_adjusted_expectancy_bps", 0.0)

    real_pf = real_metrics.get("profit_factor", 0.0)
    ctrl_pf = control_metrics.get("profit_factor", 0.0)

    ctrl_n = control_metrics.get("trade_count", 0)

    # Control sample too small -> Diagnostic Caution
    if ctrl_n < 10:
        return {
            "severity": "DIAGNOSTIC_CAUTION",
            "reason": "CONTROL_SAMPLE_TOO_SMALL",
            "candidate_status": "PROMISING_DIRECTIONAL_SHAPE_BUT_CONTROL_WEAK"
        }

    # Control outperforms real candidate -> Hard Reject
    if ctrl_exp >= real_exp or (ctrl_pf >= real_pf and abs(ctrl_exp - real_exp) < 2.0):
        return {
            "severity": "HARD_REJECT",
            "reason": "CONTROL_COMPARABLE_OR_STRONGER",
            "candidate_status": "CONTROL_REJECTED"
        }

    # Control is weaker but close -> Soft Reject
    if (real_exp - ctrl_exp) < 3.0:
        return {
            "severity": "SOFT_REJECT",
            "reason": "INSUFFICIENT_MARGIN_OVER_CONTROL",
            "candidate_status": "PROMISING_DIRECTIONAL_SHAPE_BUT_CONTROL_WEAK"
        }

    # Signal outclasses control cleanly -> Pass
    return {
        "severity": "PASS",
        "reason": "SIGNAL_OUTPERFORMS_CONTROL_CLEANLY",
        "candidate_status": "ECONOMIC_SHAPE_PASS_CONTROL_PENDING"
    }
