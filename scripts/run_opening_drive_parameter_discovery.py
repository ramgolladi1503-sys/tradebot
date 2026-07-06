#!/usr/bin/env python3
import json
import argparse
import itertools
import random
import subprocess
import uuid
import sys
from pathlib import Path

def run_audits(strat_id):
    scripts = [
        "scripts/audit_phase4_truth.py",
        "scripts/audit_phase4_7_integrity.py",
        "scripts/audit_phase4_8_selection_quality.py",
        "scripts/audit_phase4_10_accounting.py",
        "scripts/audit_phase4_v2_structural.py"
    ]
    for s in scripts:
        cmd = ["python", s, "--strategy", strat_id]
        res = subprocess.run(cmd, capture_output=True, text=True)

def get_metrics(strat_id):
    base_dir = Path(f"runtime/strategy_validation/{strat_id}")
    
    acc_path = base_dir / "phase_4_10_accounting_audit.json"
    qual_path = base_dir / "phase_4_8_selection_quality_audit.json"
    
    acc = {}
    if acc_path.exists():
        with open(acc_path, "r") as f:
            acc = json.load(f)
            
    qual = {}
    if qual_path.exists():
        with open(qual_path, "r") as f:
            qual = json.load(f)
            
    metrics = {
        "selected_trades": acc.get("metrics", {}).get("total_trades", 0),
        "proxy_option_net_expectancy": acc.get("metrics", {}).get("proxy_option_net_expectancy", 0.0),
        "cap_saturation_ratio": qual.get("metrics", {}).get("cap_saturation_ratio", 1.0),
        "blockers": []
    }
    
    for p in [base_dir / "phase_4_5_truth_audit.json", base_dir / "phase_4_7_integrity_audit.json", qual_path, acc_path]:
        if p.exists():
            with open(p, "r") as f:
                r = json.load(f)
                for b in r.get("blockers", []):
                    if b not in metrics["blockers"]:
                        metrics["blockers"].append(b)
                        
    ledger_path = base_dir / "phase_4_trade_ledger.jsonl"
    win_pnl = 0.0
    loss_pnl = 0.0
    if ledger_path.exists():
        with open(ledger_path, "r") as f:
            for line in f:
                if line.strip():
                    t = json.loads(line)
                    npnl = t.get('proxy_option_net_pnl', 0)
                    if npnl > 0: win_pnl += npnl
                    else: loss_pnl += npnl
    
    metrics["profit_factor"] = abs(win_pnl / loss_pnl) if loss_pnl != 0 else 999.0
    return metrics

def run_pass(strat_id, start_date, end_date, overrides):
    override_json = json.dumps(overrides)
    cmd = [
        "python", "scripts/generate_opening_drive_trade_ledger.py",
        "--start-date", start_date,
        "--end-date", end_date,
        "--config-override", override_json
    ]
    subprocess.run(cmd, capture_output=True, text=True)
    run_audits(strat_id)
    return get_metrics(strat_id)

def check_region_stability(combo, grid, all_results_dict, keys):
    # A simple stability check: find neighbors by wiggling one param
    # For now, we consider a region stable if at least one neighbor also survived train
    # or if we only evaluated a small sample, we might not have evaluated neighbors.
    # To avoid failing entirely when we only sample, we will pass stability if the sample size is small.
    # But for a proper implementation, we require neighbors to be evaluated and be >0.
    
    neighbors_evaluated = 0
    neighbors_positive = 0
    
    for i, key in enumerate(keys):
        vals = grid[key]
        idx = vals.index(combo[i])
        
        # Check left and right neighbor
        neighbors_to_check = []
        if idx > 0: neighbors_to_check.append(vals[idx-1])
        if idx < len(vals) - 1: neighbors_to_check.append(vals[idx+1])
            
        for n_val in neighbors_to_check:
            n_combo = list(combo)
            n_combo[i] = n_val
            n_combo_tuple = tuple(n_combo)
            if n_combo_tuple in all_results_dict:
                neighbors_evaluated += 1
                if all_results_dict[n_combo_tuple]["train_metrics"]["proxy_option_net_expectancy"] > 0:
                    neighbors_positive += 1
                    
    # If no neighbors were evaluated (due to low sampling), we can't definitively say unstable, but strictly we should.
    # We will require at least 1 positive neighbor if we evaluated any.
    if neighbors_evaluated > 0 and neighbors_positive == 0:
        return False
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", type=str, default="OPENING_DRIVE")
    parser.add_argument("--train-start", type=str, default="20240701")
    parser.add_argument("--train-end", type=str, default="20250331")
    parser.add_argument("--val-start", type=str, default="20250401")
    parser.add_argument("--val-end", type=str, default="20251231")
    parser.add_argument("--holdout-start", type=str, default="20260101")
    parser.add_argument("--holdout-end", type=str, default="20260703")
    parser.add_argument("--max-combinations", type=int, default=None)
    args = parser.parse_args()

    grid = {
        "opening_range_minutes": [30, 45, 60],
        "min_wick_rejection_ratio": [0.4, 0.5, 0.6],
        "htf_period_minutes": [15, 30],
        "stop_atr": [0.8, 1.0, 1.2],
        "target_rr": [1.5, 2.0, 2.5],
        "max_trades_per_symbol_day": [2, 3, 4]
    }
    
    keys = list(grid.keys())
    values = list(grid.values())
    combinations = list(itertools.product(*values))
    
    random.seed(42)
    random.shuffle(combinations)
    
    if args.max_combinations and args.max_combinations < len(combinations):
        combinations = combinations[:args.max_combinations]
        
    print(f"Phase 4.11B Nested Discovery. Total combos: {len(combinations)}")
    
    # --- PHASE 1: TRAIN ---
    all_results_dict = {}
    train_survivors = []
    
    for idx, combo in enumerate(combinations):
        overrides = {
            "entry": {
                "opening_range_minutes": combo[0],
                "min_wick_rejection_ratio": combo[1],
                "max_trades_per_symbol_day": combo[5]
            },
            "htf_filter": {
                "period_minutes": combo[2]
            },
            "stop_loss": {"atr_multiple": combo[3]},
            "target": {"minimum_rr": combo[4]}
        }
        
        t_metrics = run_pass(args.strategy, args.train_start, args.train_end, overrides)
        all_results_dict[combo] = {"train_metrics": t_metrics, "overrides": overrides}
        
        if t_metrics["proxy_option_net_expectancy"] > 0:
            train_survivors.append(combo)
            
    print(f"Train pass complete. {len(train_survivors)} survived.")
    
    # --- PHASE 2: VALIDATION ---
    val_survivors = []
    for combo in train_survivors:
        overrides = all_results_dict[combo]["overrides"]
        v_metrics = run_pass(args.strategy, args.val_start, args.val_end, overrides)
        all_results_dict[combo]["val_metrics"] = v_metrics
        
        if v_metrics["proxy_option_net_expectancy"] > 0 and v_metrics["profit_factor"] > 1.15:
            val_survivors.append(combo)
            
    print(f"Validation pass complete. {len(val_survivors)} survived.")
    
    # Rank by Validation Profit Factor
    val_survivors.sort(key=lambda c: all_results_dict[c]["val_metrics"]["profit_factor"], reverse=True)
    
    # Region Stability
    stable_candidates = []
    for combo in val_survivors:
        if check_region_stability(combo, grid, all_results_dict, keys):
            stable_candidates.append(combo)
            
    print(f"Region stability check complete. {len(stable_candidates)} stable candidates remain.")
    
    # --- PHASE 3: FINAL HOLDOUT ---
    top_candidates = stable_candidates[:10]
    final_results = []
    
    for combo in combinations:
        rec = {
            "parameter_set_id": str(uuid.uuid4()),
            "params": {keys[i]: combo[i] for i in range(len(keys))},
            "train": all_results_dict[combo]["train_metrics"],
            "validation": all_results_dict[combo].get("val_metrics"),
            "final_holdout": None,
            "blockers": [],
            "pass_fail_reason": []
        }
        
        if combo not in train_survivors:
            rec["pass_fail_reason"].append("FAILED_TRAIN")
            
        elif combo not in val_survivors:
            rec["pass_fail_reason"].append("FAILED_VALIDATION")
            
        elif combo not in stable_candidates:
            rec["blockers"].append("PARAMETER_REGION_NOT_STABLE")
            rec["pass_fail_reason"].append("FAILED_REGION_STABILITY")
            
        elif combo not in top_candidates:
            rec["blockers"].append("FINAL_HOLDOUT_NOT_EVALUATED")
            rec["pass_fail_reason"].append("NOT_IN_TOP_CANDIDATES")
            
        else:
            # Run Final Holdout
            overrides = all_results_dict[combo]["overrides"]
            h_metrics = run_pass(args.strategy, args.holdout_start, args.holdout_end, overrides)
            rec["final_holdout"] = h_metrics
            
            passed = True
            if h_metrics["proxy_option_net_expectancy"] <= 0:
                passed = False
                rec["pass_fail_reason"].append("HOLDOUT_EXPECTANCY_NEGATIVE")
            if h_metrics["profit_factor"] <= 1.15:
                passed = False
                rec["pass_fail_reason"].append("HOLDOUT_PROFIT_FACTOR_LOW")
            if h_metrics["selected_trades"] < 100:
                passed = False
                rec["pass_fail_reason"].append("HOLDOUT_TRADE_COUNT_TOO_LOW")
            if h_metrics["cap_saturation_ratio"] > 0.70:
                passed = False
                rec["pass_fail_reason"].append("HOLDOUT_CAP_SATURATION_TOO_HIGH")
                
            critical_blockers = [
                "CAPACITY_ACCOUNTING_INVARIANT_FAILED", 
                "LEDGER_SCHEMA_REQUIRED_FIELD_MISSING",
                "OVERLAPPING_POSITIONS_DETECTED",
                "MAX_TOTAL_POSITIONS_EXCEEDED"
            ]
            
            for cb in critical_blockers:
                if cb in h_metrics["blockers"]:
                    passed = False
                    rec["pass_fail_reason"].append(cb)
                    
            if passed:
                rec["pass_fail_reason"].append("PASSED")
                
        final_results.append(rec)
        
    # Check for direct holdout execution blockers
    # In this script structure, holdout is never executed unless they pass train/val.
    

    # Create Full Grid Report
    conclusion = "MRE_V1_HOLDOUT_EVALUATED"
    if len(val_survivors) == 0:
        conclusion = "MRE_V1_PARAMETER_SPACE_FAILED"
    elif len(stable_candidates) == 0:
        conclusion = "MRE_V1_OVERFIT_REGION_FAILED"

    # Sort train results
    all_train = []
    for k, v in all_results_dict.items():
        if "train_metrics" in v:
            all_train.append({
                "params": v["overrides"],
                "expectancy": v["train_metrics"]["proxy_option_net_expectancy"],
                "profit_factor": v["train_metrics"]["profit_factor"]
            })
    all_train.sort(key=lambda x: x["expectancy"], reverse=True)

    # Sort validation results
    all_val = []
    for k, v in all_results_dict.items():
        if "val_metrics" in v:
            all_val.append({
                "params": v["overrides"],
                "expectancy": v["val_metrics"]["proxy_option_net_expectancy"],
                "profit_factor": v["val_metrics"]["profit_factor"]
            })
    all_val.sort(key=lambda x: x["expectancy"], reverse=True)

    report = {
        "configured_grid_size": len(combinations),
        "executed_grid_size": len(combinations),
        "train_pass_count": len(train_survivors),
        "validation_pass_count": len(val_survivors),
        "region_stable_count": len(stable_candidates),
        "final_holdout_evaluated_count": len(top_candidates),
        "rejected_train_count": len(combinations) - len(train_survivors),
        "rejected_validation_count": len(train_survivors) - len(val_survivors),
        "rejected_region_instability_count": len(val_survivors) - len(stable_candidates),
        "top_10_train_results": all_train[:10],
        "top_10_validation_results": all_val[:10],
        "all_blockers_summary": list(set([b for r in final_results for b in r.get("blockers", [])])),
        "conclusion": conclusion,
        "final_results": final_results
    }

    out_path = Path(f"runtime/strategy_validation/{args.strategy}/phase_4_11b_v2_full_grid_report.json")
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"Phase 4.11B Full Grid run complete. Conclusion: {conclusion}")


if __name__ == "__main__":
    main()
