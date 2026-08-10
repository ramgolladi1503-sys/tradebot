#!/usr/bin/env python3
"""
V12 Hardening Runner Script - Trapped Push Snapback (H1) Expanded Controls
Executes missing negative controls (wrong time window, session permutation, 
symbol permutation, random subset placebo, prior failed-family comparator)
and writes hardened evidence artifacts.
"""
import os
import sys
import json
import numpy as np
import pandas as pd
from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root / "scripts" / "research" / "hypothesis_factory"))

from trader_observation_micro_features_v12 import load_and_align_v12_data
from economic_shape_metrics_v11 import compute_trade_shape_metrics, classify_negative_control_severity

def main():
    evidence_dir = "/Users/madhuram/tradebot-strategy-certification-kernel-v0/research/evidence/trader_observation_micro_patterns_v12_hardening"
    os.makedirs(evidence_dir, exist_ok=True)

    constituent_dir = '/Users/madhuram/tradebot-ml-evidence/context-transition-atlas-v1/context-transition-v3/constituent-structure-v1/selective-upstox-missing-v1'
    nifty_csv_path = '/Users/madhuram/tradebot-strategy-certification-kernel-v0/research/hypotheses/historical_corpus/kite_nifty_cache_v2/canonical/NIFTY.csv'

    df = load_and_align_v12_data(constituent_dir, nifty_csv_path)
    total_bars = len(df)
    dev_n = int(total_bars * 0.60)
    locked_n = int(total_bars * 0.20)

    locked_df = df.iloc[dev_n:dev_n+locked_n].copy()

    # H1 predicate: range_bps(t-1) > 12.0 & upper_wick_bps(t-1) > 4.0 & body_bps(t) < -2.0
    h1_mask = (locked_df['range_bps'].shift(1) > 12.0) & (locked_df['upper_wick_bps'].shift(1) > 4.0) & (locked_df['body_bps'] < -2.0)
    h1_sub = locked_df[h1_mask]
    
    # Real H1 DOWN returns
    real_rets = [-r for r in h1_sub['nifty_ret6'].tolist()]
    real_metrics = compute_trade_shape_metrics(real_rets, cost_bps=3.0, initial_risk_bps=20.0)

    missing_controls = []
    severities = []

    # Control 1: Direction Inversion (Already run, real rets negated)
    inv_rets = [-r for r in real_rets]
    c1_metrics = compute_trade_shape_metrics(inv_rets, cost_bps=3.0, initial_risk_bps=20.0)
    c1_sev = classify_negative_control_severity(real_metrics, c1_metrics)
    c1_sev["control_type"] = "DIRECTION_INVERSION"
    missing_controls.append({"control_type": "DIRECTION_INVERSION", "real_metrics": real_metrics, "control_metrics": c1_metrics, "sample_size": len(inv_rets), "severity": c1_sev["severity"], "reason": c1_sev["reason"], "candidate_status_after_control": c1_sev["candidate_status"]})
    severities.append(c1_sev["severity"])

    # Control 2: Wrong Time Window (Opening window 09:15-10:15 vs general)
    wrong_window_mask = h1_mask & (locked_df.index.time >= pd.to_datetime('09:15').time()) & (locked_df.index.time <= pd.to_datetime('10:15').time())
    ww_sub = locked_df[wrong_window_mask]
    ww_rets = [-r for r in ww_sub['nifty_ret6'].tolist()]
    c2_metrics = compute_trade_shape_metrics(ww_rets, cost_bps=3.0, initial_risk_bps=20.0)
    c2_sev = classify_negative_control_severity(real_metrics, c2_metrics)
    missing_controls.append({"control_type": "WRONG_TIME_WINDOW_CONTROL", "real_metrics": real_metrics, "control_metrics": c2_metrics, "sample_size": len(ww_rets), "severity": c2_sev["severity"], "reason": c2_sev["reason"], "candidate_status_after_control": c2_sev["candidate_status"]})
    severities.append(c2_sev["severity"])

    # Control 3: Session Permutation (Shuffle 6-bar return series within locked split)
    np.random.seed(42)
    shuffled_rets = np.random.choice(locked_df['nifty_ret6'].values, size=len(real_rets), replace=False)
    shuffled_rets = [-r for r in shuffled_rets]
    c3_metrics = compute_trade_shape_metrics(list(shuffled_rets), cost_bps=3.0, initial_risk_bps=20.0)
    c3_sev = classify_negative_control_severity(real_metrics, c3_metrics)
    missing_controls.append({"control_type": "SESSION_PERMUTATION_CONTROL", "real_metrics": real_metrics, "control_metrics": c3_metrics, "sample_size": len(shuffled_rets), "severity": c3_sev["severity"], "reason": c3_sev["reason"], "candidate_status_after_control": c3_sev["candidate_status"]})
    severities.append(c3_sev["severity"])

    # Control 4: Symbol Permutation / Constituent Shuffle (N/A for H1 single index candle shape, marked NOT_APPLICABLE)
    missing_controls.append({"control_type": "SYMBOL_PERMUTATION_CONTROL", "real_metrics": real_metrics, "control_metrics": compute_trade_shape_metrics([]), "sample_size": 0, "severity": "NOT_APPLICABLE", "reason": "H1_PREDICATE_SOURCES_ONLY_NIFTY_INDEX_BARS", "candidate_status_after_control": "PASS"})

    # Control 5: Random Subset Placebo (Random 26 bars from locked split)
    random_indices = np.random.choice(len(locked_df), size=len(real_rets), replace=False)
    random_rets = [-r for r in locked_df.iloc[random_indices]['nifty_ret6'].values]
    c5_metrics = compute_trade_shape_metrics(random_rets, cost_bps=3.0, initial_risk_bps=20.0)
    c5_sev = classify_negative_control_severity(real_metrics, c5_metrics)
    missing_controls.append({"control_type": "RANDOM_SUBSET_PLACEBO_CONTROL", "real_metrics": real_metrics, "control_metrics": c5_metrics, "sample_size": len(random_rets), "severity": c5_sev["severity"], "reason": c5_sev["reason"], "candidate_status_after_control": c5_sev["candidate_status"]})
    severities.append(c5_sev["severity"])

    # Control 6: Prior Failed-Family Comparator (V3 pre-close 30 min sequence baseline)
    v3_failed_mean_exp_bps = 0.67
    c6_metrics = {"cost_adjusted_expectancy_bps": v3_failed_mean_exp_bps, "profit_factor": 1.15, "trade_count": 26}
    c6_sev = classify_negative_control_severity(real_metrics, c6_metrics)
    missing_controls.append({"control_type": "PRIOR_FAILED_FAMILY_COMPARATOR", "real_metrics": real_metrics, "control_metrics": c6_metrics, "sample_size": 26, "severity": c6_sev["severity"], "reason": c6_sev["reason"], "candidate_status_after_control": c6_sev["candidate_status"]})
    severities.append(c6_sev["severity"])

    with open(os.path.join(evidence_dir, "missing_negative_controls.json"), "w") as f:
        json.dump({"schema_version": 1, "candidate_id": "H1_TRAPPED_PUSH_SNAPBACK", "controls": missing_controls}, f, indent=2)

    overall_severity = "PASS"
    if "HARD_REJECT" in severities:
        overall_severity = "HARD_REJECT"
    elif "SOFT_REJECT" in severities:
        overall_severity = "SOFT_REJECT"
    elif "DIAGNOSTIC_CAUTION" in severities:
        overall_severity = "DIAGNOSTIC_CAUTION"

    with open(os.path.join(evidence_dir, "expanded_control_severity_classification.json"), "w") as f:
        json.dump({
            "schema_version": 1,
            "candidate_id": "H1_TRAPPED_PUSH_SNAPBACK",
            "overall_severity": overall_severity,
            "severities_summary": severities,
            "controls_passed": len([s for s in severities if s in ["PASS", "NOT_APPLICABLE"]]),
            "total_controls_run": len(severities)
        }, f, indent=2)

    print(f"Hardening controls complete. Overall severity: {overall_severity}")

if __name__ == "__main__":
    main()
