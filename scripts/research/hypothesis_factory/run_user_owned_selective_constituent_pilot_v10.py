#!/usr/bin/env python3
"""
Run Selective Constituent Pilot V10 Script
Executes development screen (60%), locked validation (20%), negative controls, 
and applies V11 economic shape metrics scoring. Writes all mandatory artifacts.
"""
import os
import sys
import json
import numpy as np
import pandas as pd
from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root / "scripts" / "research" / "hypothesis_factory"))

from user_owned_selective_constituent_features_v10 import load_and_align_pilot_data, generate_v10_candidate_specs
from economic_shape_metrics_v11 import compute_trade_shape_metrics, classify_negative_control_severity

def main():
    evidence_dir = "/Users/madhuram/tradebot-strategy-certification-kernel-v0/research/evidence/user_owned_selective_constituent_pilot_v10"
    os.makedirs(evidence_dir, exist_ok=True)

    constituent_dir = '/Users/madhuram/tradebot-ml-evidence/context-transition-atlas-v1/context-transition-v3/constituent-structure-v1/selective-upstox-missing-v1'
    nifty_csv_path = '/Users/madhuram/tradebot-strategy-certification-kernel-v0/research/hypotheses/historical_corpus/kite_nifty_cache_v2/canonical/NIFTY.csv'

    df = load_and_align_pilot_data(constituent_dir, nifty_csv_path)
    total_bars = len(df)

    # Split 60% Dev, 20% Locked, 20% Prospective Holdout
    dev_n = int(total_bars * 0.60)
    locked_n = int(total_bars * 0.20)

    dev_df = df.iloc[:dev_n].copy()
    locked_df = df.iloc[dev_n:dev_n+locked_n].copy()

    candidates = generate_v10_candidate_specs()

    # 1. Candidate Registry
    registry_file = os.path.join(evidence_dir, "candidate_registry.jsonl")
    with open(registry_file, "w") as f:
        for c in candidates:
            rec = {
                "candidate_id": c["candidate_id"],
                "family": c["family"],
                "target_direction": c["target_direction"],
                "pilot_scope": c["pilot_scope"],
                "not_full_nifty_breadth": c["not_full_nifty_breadth"],
                "execution_viability": c["execution_viability"],
                "edge_claimed": c["edge_claimed"],
                "structural_edge_certified": c["structural_edge_certified"]
            }
            f.write(json.dumps(rec) + "\n")

    # 2. Development Screen
    dev_results = []
    dev_survivors = []

    for c in candidates:
        mask = c["predicate"](dev_df)
        sub_df = dev_df[mask]
        n_trades = len(sub_df)
        
        if n_trades >= 5:
            rets = sub_df["nifty_ret6"].tolist()
            if c["target_direction"] == "DOWN":
                rets = [-r for r in rets]
            
            metrics = compute_trade_shape_metrics(rets, cost_bps=3.0, initial_risk_bps=20.0)
            passed = metrics["cost_adjusted_expectancy_bps"] > 0 and metrics["trade_count"] >= 5
            
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

    dev_survivor_file = os.path.join(evidence_dir, "development_survivors.jsonl")
    with open(dev_survivor_file, "w") as f:
        for s in dev_survivors:
            f.write(json.dumps({"candidate_id": s["candidate_id"], "family": s["family"]}) + "\n")

    locked_results = []
    locked_survivors = []
    controls_results = []
    economic_shape_results = []

    if dev_survivors:
        # Run Locked Validation only on dev survivors
        for s in dev_survivors:
            mask = s["predicate"](locked_df)
            sub_df = locked_df[mask]
            rets = sub_df["nifty_ret6"].tolist()
            if s["target_direction"] == "DOWN":
                rets = [-r for r in rets]
            
            metrics = compute_trade_shape_metrics(rets, cost_bps=3.0, initial_risk_bps=20.0)
            passed_locked = metrics["cost_adjusted_expectancy_bps"] > 0 and metrics["trade_count"] >= 3
            
            locked_rec = {
                "candidate_id": s["candidate_id"],
                "locked_trade_count": len(rets),
                "metrics": metrics,
                "passed_locked": passed_locked
            }
            locked_results.append(locked_rec)
            
            if passed_locked:
                locked_survivors.append(s)
                
                # Negative Controls
                # Control 1: Direction inversion
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
                
                # Economic Shape Scoring
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

    with open(os.path.join(evidence_dir, "campaign_manifest.json"), "w") as f:
        json.dump({
            "schema_version": 1,
            "campaign_id": "user_owned_selective_constituent_pilot_v10",
            "symbols_used": ["BEL", "INDIGO", "JIOFIN", "TRENT", "ZOMATO"],
            "total_aligned_bars": total_bars,
            "dev_bars": dev_n,
            "locked_bars": locked_n
        }, f, indent=2)

    with open(os.path.join(evidence_dir, "selection_pressure.json"), "w") as f:
        json.dump({
            "schema_version": 1,
            "total_evaluated": len(candidates),
            "dev_survivors": len(dev_survivors),
            "locked_survivors": len(locked_survivors)
        }, f, indent=2)

    with open(os.path.join(evidence_dir, "failure_registry.md"), "w") as f:
        f.write("# V10 Pilot Failure Registry\n\n")
        if not dev_survivors:
            f.write("- All 4 V10 candidates failed development screening due to insufficient trade count or negative cost-adjusted expectancy in 60% dev split.\n")
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

    # Determine final verdict
    if not dev_survivors:
        final_verdict = "V11_PROVENANCE_REPAIRED_V10_NO_PILOT_DEVELOPMENT_SURVIVORS"
    elif not locked_survivors:
        final_verdict = "V11_PROVENANCE_REPAIRED_V10_PILOT_LOCKED_VALIDATION_FAILED"
    else:
        final_verdict = "V11_PROVENANCE_REPAIRED_V10_PROMISING_NOT_CERTIFIED"

    controlled_verdict_rec = {
        "schema_version": 1,
        "controlled_verdict": final_verdict,
        "latest_commit": "1ae8204b95fe874d55569e9bf853476c5f8a2ab0",
        "v11_provenance_repaired": True,
        "v10_pilot_run": True,
        "user_owned_selective_data_found": True,
        "symbols": ["BEL", "INDIGO", "ITCHOTELS", "JIOFIN", "KWIL", "MAXHEALTH", "TMCV", "TRENT", "ZOMATO"],
        "files_audited": 118,
        "data_quality_status": "DATA_QUALITY_PASS_WITH_WARNINGS",
        "overlap_with_nifty_index": "1899 5-min bars (core 5 symbols)",
        "development_survivors": len(dev_survivors),
        "locked_validation_run": len(dev_survivors) > 0,
        "locked_survivors": len(locked_survivors),
        "negative_controls_status": "NO_SURVIVORS_EVALUATED" if not locked_survivors else "EVALUATED",
        "economic_shape_status": "APPLIED_V11_METRICS",
        "historical_pilot_signal_supported": False,
        "full_nifty_breadth_supported": False,
        "structural_edge_certified": False,
        "edge_claimed": False,
        "execution_viable": False,
        "prospective_supported": False,
        "vendor_contact_recommended_now": False,
        "tick_bidask_required_now": False,
        "next_action": "EXPAND_USER_OWNED_CONSTITUENT_COVERAGE_OR_EXPLORE_CROSS_ASSET_SHOCKS"
    }

    with open(os.path.join(evidence_dir, "CONTROLLED_VERDICT.json"), "w") as f:
        json.dump(controlled_verdict_rec, f, indent=2)

    print(f"RUN COMPLETE. FINAL CONTROLLED VERDICT: {final_verdict}")

if __name__ == "__main__":
    main()
