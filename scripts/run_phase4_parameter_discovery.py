#!/usr/bin/env python3
import json
import argparse
import itertools
import random
import subprocess
import os
import uuid
from pathlib import Path

def run_audits(strat_id, audit_script, is_smoke_test=False):
    scripts = [
        "scripts/audit_phase4_truth.py",
        "scripts/audit_phase4_7_integrity.py",
        "scripts/audit_phase4_8_selection_quality.py",
        "scripts/audit_phase4_10_accounting.py"
    ]
    if audit_script:
        scripts.append(audit_script)
        
    for s in scripts:
        cmd = ["python", s, "--strategy", strat_id]
        if s == audit_script and is_smoke_test:
            cmd.append("--is-smoke-test")
        subprocess.run(cmd, capture_output=True, text=True)

def get_metrics(strat_id, selectivity_limits):
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
        "percent_symbol_days_at_cap": 1.0,
        "zero_trade_symbol_days_ratio": 0.0,
        "blockers": []
    }
    
    summary_path = base_dir / "phase_4_trade_ledger_summary.json"
    if summary_path.exists():
        with open(summary_path, "r") as f:
            summ = json.load(f).get("metrics", {})
            metrics["cap_saturation_ratio"] = summ.get("cap_saturation_ratio", 1.0)
            metrics["percent_symbol_days_at_cap"] = summ.get("percent_symbol_days_at_cap", 1.0)
            metrics["zero_trade_symbol_days_ratio"] = summ.get("zero_trade_symbol_days_ratio", 0.0)
            metrics["selected_trades"] = summ.get("total_trades", metrics["selected_trades"])
            
    max_cap = selectivity_limits.get("max_cap_saturation_ratio", 0.35)
    max_percent_at_cap = selectivity_limits.get("max_percent_symbol_days_at_cap", 0.20)
    min_zero_trade_ratio = selectivity_limits.get("min_zero_trade_symbol_days_ratio", 0.25)
    min_trades = selectivity_limits.get("min_selected_trades", 50)
            
    if metrics["cap_saturation_ratio"] > max_cap:
        metrics["blockers"].append(f"{strat_id}_CAP_SATURATION_TOO_HIGH")
    if metrics["percent_symbol_days_at_cap"] > max_percent_at_cap:
        metrics["blockers"].append(f"{strat_id}_SYMBOL_DAY_AT_CAP_TOO_HIGH")
    if metrics["zero_trade_symbol_days_ratio"] < min_zero_trade_ratio:
        metrics["blockers"].append(f"{strat_id}_TOO_MANY_DAILY_TRADES")
    if metrics["selected_trades"] < min_trades:
        metrics["blockers"].append(f"{strat_id}_SELECTIVITY_NOT_PROVEN")
    
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

def run_pass(strat_id, generator_script, start_date, end_date, overrides, audit_script, selectivity_limits, is_smoke_test=False):
    override_json = json.dumps(overrides)
    cmd = [
        "python", generator_script,
        "--start-date", start_date,
        "--end-date", end_date,
        "--config-override", override_json
    ]
    env = dict(os.environ, PYTHONHASHSEED="42")
    subprocess.run(cmd, capture_output=True, text=True, env=env)
    run_audits(strat_id, audit_script, is_smoke_test)
    return get_metrics(strat_id, selectivity_limits)

def check_region_stability(combo, grid_def, all_results_dict, keys):
    neighbors_evaluated = 0
    neighbors_positive = 0
    
    for i, key in enumerate(keys):
        vals = grid_def[key]
        idx = vals.index(combo[i])
        
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
                    
    if neighbors_evaluated > 0 and neighbors_positive == 0:
        return False
    return True

def convert_flat_to_nested_overrides(combo, keys, parameter_mapping):
    overrides = {}
    for idx, key in enumerate(keys):
        val = combo[idx]
        path = parameter_mapping.get(key, f"entry.{key}")
        parts = path.split(".")
        
        current = overrides
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[parts[-1]] = val
        
    return overrides

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", type=str, required=True)
    parser.add_argument("--generator-script", type=str, required=True)
    parser.add_argument("--audit-script", type=str, default="")
    parser.add_argument("--report-filename", type=str, default="phase_4_generic_grid_report.json")
    parser.add_argument("--grid-definition", type=str, required=True)
    parser.add_argument("--selectivity-limits", type=str, default="")
    parser.add_argument("--train-start", type=str, default="20240701")
    parser.add_argument("--train-end", type=str, default="20250331")
    parser.add_argument("--val-start", type=str, default="20250401")
    parser.add_argument("--val-end", type=str, default="20251231")
    parser.add_argument("--holdout-start", type=str, default="20260101")
    parser.add_argument("--holdout-end", type=str, default="20260703")
    parser.add_argument("--max-combinations", type=int, default=None)
    args = parser.parse_args()

    # Load Grid
    with open(args.grid_definition, "r") as f:
        grid_config = json.load(f)
    
    grid_def = grid_config.get("grid", {})
    parameter_mapping = grid_config.get("mapping", {})
    
    # Load Selectivity limits
    selectivity_limits = {}
    if args.selectivity_limits:
        with open(args.selectivity_limits, "r") as f:
            selectivity_limits = json.load(f)
    
    keys = list(grid_def.keys())
    values = list(grid_def.values())
    combinations = list(itertools.product(*values))
    
    random.seed(42)
    random.shuffle(combinations)
    
    if args.max_combinations and args.max_combinations < len(combinations):
        combinations = combinations[:args.max_combinations]
        
    print(f"Phase 4.11B Generic Discovery for {args.strategy}. Total combos: {len(combinations)}")
    
    all_results_dict = {}
    train_survivors = []
    
    for idx, combo in enumerate(combinations):
        overrides = convert_flat_to_nested_overrides(combo, keys, parameter_mapping)
        
        t_metrics = run_pass(args.strategy, args.generator_script, args.train_start, args.train_end, overrides, args.audit_script, selectivity_limits, is_smoke_test=bool(args.max_combinations))
        all_results_dict[combo] = {"train_metrics": t_metrics, "overrides": overrides}
        
        if t_metrics["proxy_option_net_expectancy"] > 0 and not t_metrics.get("blockers"):
            train_survivors.append(combo)
            
    print(f"Train pass complete. {len(train_survivors)} survived.")
    
    val_survivors = []
    for combo in train_survivors:
        overrides = all_results_dict[combo]["overrides"]
        v_metrics = run_pass(args.strategy, args.generator_script, args.val_start, args.val_end, overrides, args.audit_script, selectivity_limits)
        all_results_dict[combo]["val_metrics"] = v_metrics
        
        if v_metrics["proxy_option_net_expectancy"] > 0 and v_metrics["profit_factor"] > 1.15 and not v_metrics.get("blockers"):
            val_survivors.append(combo)
            
    print(f"Validation pass complete. {len(val_survivors)} survived.")
    
    val_survivors.sort(key=lambda c: all_results_dict[c]["val_metrics"]["profit_factor"], reverse=True)
    
    stable_candidates = []
    for combo in val_survivors:
        if check_region_stability(combo, grid_def, all_results_dict, keys):
            stable_candidates.append(combo)
            
    print(f"Region stability check complete. {len(stable_candidates)} stable candidates remain.")
    
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
            overrides = all_results_dict[combo]["overrides"]
            h_metrics = run_pass(args.strategy, args.generator_script, args.holdout_start, args.holdout_end, overrides, args.audit_script, selectivity_limits)
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
        
    conclusion = f"{args.strategy}_HOLDOUT_EVALUATED"
    if len(val_survivors) == 0:
        conclusion = f"{args.strategy}_PARAMETER_SPACE_FAILED"
    elif len(stable_candidates) == 0:
        conclusion = f"{args.strategy}_OVERFIT_REGION_FAILED"

    all_train = []
    for k, v in all_results_dict.items():
        if "train_metrics" in v:
            all_train.append({
                "params": v["overrides"],
                "expectancy": v["train_metrics"]["proxy_option_net_expectancy"],
                "profit_factor": v["train_metrics"]["profit_factor"]
            })
    all_train.sort(key=lambda x: x["expectancy"], reverse=True)

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

    out_path = Path(f"runtime/strategy_validation/{args.strategy}/{args.report_filename}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"Generic Grid run complete for {args.strategy}. Conclusion: {conclusion}")

if __name__ == "__main__":
    main()
