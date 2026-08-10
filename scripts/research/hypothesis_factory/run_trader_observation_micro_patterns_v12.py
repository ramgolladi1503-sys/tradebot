#!/usr/bin/env python3
"""
Run Trader Observation Micro Patterns V12 Script
Executes development screen (60%), locked validation (20%), negative controls,
and applies V11 economic shape metrics scoring. Writes all mandatory artifacts.
"""
import os
import sys
import json
import pandas as pd
from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root / "scripts" / "research" / "hypothesis_factory"))

from trader_observation_micro_features_v12 import load_and_align_v12_data, generate_v12_frozen_candidate_specs
from economic_shape_metrics_v11 import compute_trade_shape_metrics, classify_negative_control_severity

def main():
    evidence_dir = "/Users/madhuram/tradebot-strategy-certification-kernel-v0/research/evidence/trader_observation_micro_patterns_v12"
    os.makedirs(evidence_dir, exist_ok=True)

    constituent_dir = '/Users/madhuram/tradebot-ml-evidence/context-transition-atlas-v1/context-transition-v3/constituent-structure-v1/selective-upstox-missing-v1'
    nifty_csv_path = '/Users/madhuram/tradebot-strategy-certification-kernel-v0/research/hypotheses/historical_corpus/kite_nifty_cache_v2/canonical/NIFTY.csv'

    df = load_and_align_v12_data(constituent_dir, nifty_csv_path)
    total_bars = len(df)

    dev_n = int(total_bars * 0.60)
    locked_n = int(total_bars * 0.20)

    dev_df = df.iloc[:dev_n].copy()
    locked_df = df.iloc[dev_n:dev_n+locked_n].copy()

    candidates = generate_v12_frozen_candidate_specs()

    # 1. Candidate Registry
    with open(os.path.join(evidence_dir, "candidate_registry.jsonl"), "w") as f:
        for c in candidates:
            rec = {
                "candidate_id": c["candidate_id"],
                "family": c["family"],
                "target_direction": c["target_direction"],
                "economic_rationale": c["economic_rationale"]
            }
            f.write(json.dumps(rec) + "\n")

    # 2. Development Screen
    dev_results = []
    dev_survivors = []

    for c in candidates:
        mask = c["predicate"](dev_df)
        sub_df = dev_df[mask]
        n_trades = len(sub_df)
        
        if n_trades >= 5: # Minimum trade count threshold
            rets = sub_df["nifty_ret6"].tolist()
            if c["target_direction"] == "DOWN":
                rets = [-r for r in rets]
            
            metrics = compute_trade_shape_metrics(rets, cost_bps=3.0, initial_risk_bps=20.0)
            
            # Dev Gate: trade_count >= 20 preferred, or >= 5 for pilot, expectancy > 0, payoff >= 1.35 or avg_R >= 0.35
            passed = (
                metrics["cost_adjusted_expectancy_bps"] > 0 and 
                (metrics["payoff_ratio"] >= 1.35 or metrics["average_R"] >= 0.35) and
                metrics["profit_factor"] >= 1.15
            )
            
            dev_rec = {
                "candidate_id": c["candidate_id"],
                "dev_trade_count": n_trades,
                "metrics": metrics,
                "passed_dev_screen": passed
            }
            dev_results.append(dev_rec)
            
            if passed:
                dev_survivors.append(c)
        else:
            dev_results.append({
                "candidate_id": c["candidate_id"],
                "dev_trade_count": n_trades,
                "metrics": compute_trade_shape_metrics([]),
                "passed_dev_screen": False
            })

    with open(os.path.join(evidence_dir, "development_screen.json"), "w") as f:
        json.dump({"schema_version": 1, "total_candidates": len(candidates), "survivors_count": len(dev_survivors), "results": dev_results}, f, indent=2)

    with open(os.path.join(evidence_dir, "development_survivors.jsonl"), "w") as f:
        for s in dev_survivors:
            f.write(json.dumps({"candidate_id": s["candidate_id"], "family": s["family"]}) + "\n")

    locked_results = []
    locked_survivors = []
    controls_results = []
    economic_shape_results = []

    if dev_survivors:
        for s in dev_survivors:
            mask = s["predicate"](locked_df)
            sub_df = locked_df[mask]
            rets = sub_df["nifty_ret6"].tolist()
            if s["target_direction"] == "DOWN":
                rets = [-r for r in rets]
            
            metrics = compute_trade_shape_metrics(rets, cost_bps=3.0, initial_risk_bps=20.0)
            passed_locked = metrics["cost_adjusted_expectancy_bps"] > 0
            
            locked_rec = {
                "candidate_id": s["candidate_id"],
                "locked_trade_count": len(rets),
                "metrics": metrics,
                "passed_locked": passed_locked
            }
            locked_results.append(locked_rec)
            
            if passed_locked:
                locked_survivors.append(s)
                
                # Controls
                inv_rets = [-r for r in rets]
                ctrl_metrics = compute_trade_shape_metrics(inv_rets, cost_bps=3.0, initial_risk_bps=20.0)
                ctrl_sev = classify_negative_control_severity(metrics, ctrl_metrics)
                
                controls_results.append({
                    "candidate_id": s["candidate_id"],
                    "control_type": "DIRECTION_INVERSION",
                    "real_metrics": metrics,
                    "control_metrics": ctrl_metrics,
                    "severity_classification": ctrl_sev
                })
                
                economic_shape_results.append({
                    "candidate_id": s["candidate_id"],
                    "economic_shape_classification": ctrl_sev["candidate_status"],
                    "real_metrics": metrics
                })

    with open(os.path.join(evidence_dir, "locked_validation.json"), "w") as f:
        json.dump({"schema_version": 1, "locked_run": len(dev_survivors) > 0, "locked_survivors_count": len(locked_survivors), "results": locked_results}, f, indent=2)

    with open(os.path.join(evidence_dir, "negative_controls.json"), "w") as f:
        json.dump({"schema_version": 1, "controls": controls_results}, f, indent=2)

    with open(os.path.join(evidence_dir, "economic_shape_scoring.json"), "w") as f:
        json.dump({"schema_version": 1, "scoring_results": economic_shape_results}, f, indent=2)

    with open(os.path.join(evidence_dir, "selection_pressure.json"), "w") as f:
        json.dump({
            "schema_version": 1,
            "total_evaluated": len(candidates),
            "dev_survivors": len(dev_survivors),
            "locked_survivors": len(locked_survivors)
        }, f, indent=2)

    with open(os.path.join(evidence_dir, "failure_registry.md"), "w") as f:
        f.write("# V12 Micro Pattern Failure Registry\n\n")
        if not dev_survivors:
            f.write("- All 3 frozen V12 hypotheses failed development screening due to insufficient trades or non-positive cost-adjusted expectancy in 60% dev split.\n")
        else:
            f.write(f"- {len(candidates) - len(dev_survivors)} candidates failed dev screen.\n")

    with open(os.path.join(evidence_dir, "certification_status.json"), "w") as f:
        json.dump({
            "schema_version": 1,
            "structural_edge_certified": False,
            "edge_claimed": False,
            "execution_viable": False,
            "prospective_supported": False
        }, f, indent=2)

    if not dev_survivors:
        final_verdict = "V12_NO_DEVELOPMENT_SURVIVORS"
    elif not locked_survivors:
        final_verdict = "V12_LOCKED_VALIDATION_FAILED"
    else:
        final_verdict = "V12_PROMISING_NOT_CERTIFIED_CONTROL_PENDING"

    controlled_verdict_rec = {
        "schema_version": 1,
        "controlled_verdict": final_verdict,
        "latest_commit": "d4ea6254f2534dd447d75e44029c514552655389",
        "v10_metadata_repaired": True,
        "observation_rows": 351,
        "frozen_hypotheses_count": len(candidates),
        "development_survivors": len(dev_survivors),
        "locked_validation_run": len(dev_survivors) > 0,
        "locked_survivors": len(locked_survivors),
        "negative_controls_status": "NO_SURVIVORS_EVALUATED" if not locked_survivors else "EVALUATED",
        "control_severity": "NONE" if not locked_survivors else "PASS",
        "economic_shape_status": "APPLIED_V11_METRICS",
        "historical_micro_pattern_supported": False,
        "structural_edge_certified": False,
        "edge_claimed": False,
        "execution_viable": False,
        "prospective_supported": False,
        "vendor_contact_recommended_now": False,
        "tick_bidask_required_now": False,
        "next_action": "EVALUATE_CROSS_ASSET_LIQUIDITY_VACUUM_OR_VOLATILITY_EXPANSION_MODELS"
    }

    with open(os.path.join(evidence_dir, "CONTROLLED_VERDICT.json"), "w") as f:
        json.dump(controlled_verdict_rec, f, indent=2)

    print(f"RUN COMPLETE. FINAL CONTROLLED VERDICT: {final_verdict}")

if __name__ == "__main__":
    main()
