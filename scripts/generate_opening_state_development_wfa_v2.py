import argparse
import json
import os
from pathlib import Path
from collections import defaultdict
from research.opening_state_momentum.development_wfa_v2_contract import build_contract, assign_folds
from research.opening_state_momentum.development_wfa_metrics import calculate_metrics, validate_outcome_returns
from research.opening_state_momentum.development_wfa_controls import (
    bootstrap_confidence_intervals,
    inverted_direction_control,
    direction_randomization_control,
    chronological_concentration_control
)

def load_json(path: str):
    with open(path, "r") as f:
        return json.load(f)

def save_json(path: Path, data: dict):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=False, default="docs/agent_reviews/opening_state_momentum", help="Output directory")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    contract = build_contract()
    
    partition = load_json("docs/agent_reviews/opening_state_momentum/research_partition.json")
    holdout_dates = set(partition["holdout"])
    
    decisions = load_json("docs/agent_reviews/opening_state_momentum/candidate_decisions.json")
    outcomes = load_json("docs/agent_reviews/opening_state_momentum/development_outcome_labels.json")
    
    audit = {
        "holdout_dates_loaded": 0,
        "holdout_outcomes_loaded": 0,
        "holdout_metrics_generated": 0
    }
    
    dev_session_dates = []
    for d in decisions:
        date = d["session_date"]
        if date in holdout_dates:
            audit["holdout_dates_loaded"] += 1
        else:
            dev_session_dates.append(date)
            
    if audit["holdout_dates_loaded"] > 0:
        raise ValueError("Holdout dates loaded in decisions")
        
    for o in outcomes:
        date = o["session_date"]
        if date in holdout_dates:
            audit["holdout_outcomes_loaded"] += 1
            
    if audit["holdout_outcomes_loaded"] > 0:
        raise ValueError("Holdout outcomes loaded")

    save_json(out_dir / "development_wfa_holdout_access_audit.json", audit)

    mismatches = validate_outcome_returns(outcomes)
    if mismatches > 0:
        raise ValueError(f"Found {mismatches} mismatch(es) between stored returns and prices")

    save_json(out_dir / "development_wfa_contract.json", contract)

    dev_session_dates = list(set(dev_session_dates))
    dev_session_dates.sort()
    
    fold_mapping = assign_folds(dev_session_dates)
    save_json(out_dir / "development_wfa_fold_assignments.json", fold_mapping)
    
    outcomes.sort(key=lambda x: x["session_date"])
    
    def group_outcomes(data):
        return {
            "ALL": data,
            "LONG": [x for x in data if x["direction"] == "LONG"],
            "SHORT": [x for x in data if x["direction"] == "SHORT"]
        }
        
    folds = {i: [] for i in range(5)}
    for o in outcomes:
        f = fold_mapping[o["session_date"]]
        folds[f].append(o)
        
    def calc_group_metrics(outcome_list, friction_bps):
        field = f"net_return_{int(friction_bps)}bps"
        returns = [o[field] for o in outcome_list]
        return calculate_metrics(returns)

    metrics_out = {}
    frictions = [0.0, 2.0, 5.0, 10.0]
    
    for scope_name, scope_data in [("OVERALL", outcomes)] + [(f"FOLD_{i}", folds[i]) for i in range(5)]:
        metrics_out[scope_name] = {}
        grouped = group_outcomes(scope_data)
        for direction_name, direction_data in grouped.items():
            metrics_out[scope_name][direction_name] = {}
            for f in frictions:
                friction_str = f"{int(f)}bps"
                metrics_out[scope_name][direction_name][friction_str] = calc_group_metrics(direction_data, f)
                
    save_json(out_dir / "development_wfa_metrics.json", metrics_out)

    temporal = {}
    monthly = defaultdict(list)
    quarterly = defaultdict(list)
    yearly = defaultdict(list)
    
    for o in outcomes:
        date = o["session_date"]
        y, m, d = date.split('-')
        q = (int(m) - 1) // 3 + 1
        
        r = o["net_return_5bps"]
        monthly[f"{y}-{m}"].append(r)
        quarterly[f"{y}-Q{q}"].append(r)
        yearly[y].append(r)
        
    def aggregate(grouped_dict):
        res = {}
        for k, v in grouped_dict.items():
            m = calculate_metrics(v)
            res[k] = {"trade_count": m["trade_count"], "mean_return": m["mean_return"]}
        return res
        
    temporal["monthly"] = aggregate(monthly)
    temporal["quarterly"] = aggregate(quarterly)
    temporal["yearly"] = aggregate(yearly)
    
    pos_folds = sum(1 for i in range(5) if metrics_out[f"FOLD_{i}"]["ALL"]["5bps"]["mean_return"] and metrics_out[f"FOLD_{i}"]["ALL"]["5bps"]["mean_return"] > 0)
    neg_folds = sum(1 for i in range(5) if metrics_out[f"FOLD_{i}"]["ALL"]["5bps"]["mean_return"] and metrics_out[f"FOLD_{i}"]["ALL"]["5bps"]["mean_return"] < 0)
    sparse_folds = sum(1 for i in range(5) if metrics_out[f"FOLD_{i}"]["ALL"]["5bps"]["trade_count"] < 4)
    
    total_arithmetic = metrics_out["OVERALL"]["ALL"]["5bps"]["cumulative_arithmetic_return"]
    if total_arithmetic != 0:
        fold_returns = [metrics_out[f"FOLD_{i}"]["ALL"]["5bps"]["cumulative_arithmetic_return"] for i in range(5)]
        temporal["best_fold_contribution"] = max(fold_returns) / total_arithmetic
        temporal["worst_fold_contribution"] = min(fold_returns) / total_arithmetic
    else:
        temporal["best_fold_contribution"] = None
        temporal["worst_fold_contribution"] = None
        
    all_returns = [o["net_return_5bps"] for o in outcomes]
    pos_returns = [r for r in all_returns if r > 0]
    pos_returns.sort(reverse=True)
    total_pos = sum(pos_returns)
    
    if total_pos > 0:
        temporal["top_one_trade_contribution"] = pos_returns[0] / total_pos if len(pos_returns) > 0 else 0
        temporal["top_three_trade_contribution"] = sum(pos_returns[:3]) / total_pos if len(pos_returns) >= 3 else 0
    else:
        temporal["top_one_trade_contribution"] = None
        temporal["top_three_trade_contribution"] = None
        
    if total_pos > 0:
        best_month_return = max([sum([r for r in lst if r > 0]) for lst in monthly.values()])
        temporal["best_month_positive_fraction"] = best_month_return / total_pos
    else:
        temporal["best_month_positive_fraction"] = None
        
    temporal["LONG_vs_SHORT_contribution"] = {
        "LONG": metrics_out["OVERALL"]["LONG"]["5bps"]["cumulative_arithmetic_return"],
        "SHORT": metrics_out["OVERALL"]["SHORT"]["5bps"]["cumulative_arithmetic_return"]
    }
    
    save_json(out_dir / "development_wfa_temporal_stability.json", temporal)
    
    bootstraps = {}
    seeds = contract["deterministic_seeds"]
    
    for f in frictions:
        friction_str = f"{int(f)}bps"
        bootstraps[friction_str] = bootstrap_confidence_intervals(
            [o[f"net_return_{friction_str}"] for o in outcomes], 
            20000, seeds["bootstrap"], f
        )
    bootstraps["SMALL_SAMPLE_WARNING"] = True
    save_json(out_dir / "development_wfa_bootstrap.json", bootstraps)
    
    controls = {}
    controls["A_direction_inversion"] = {}
    for f in frictions:
        friction_str = f"{int(f)}bps"
        inv_metrics = inverted_direction_control(outcomes, f)
        actual_metrics = metrics_out["OVERALL"]["ALL"][friction_str]
        
        controls["A_direction_inversion"][friction_str] = {
            "mean_return_difference": actual_metrics["mean_return"] - inv_metrics["mean_return"] if actual_metrics["mean_return"] is not None else None,
            "median_return_difference": actual_metrics["median_return"] - inv_metrics["median_return"] if actual_metrics["median_return"] is not None else None,
            "win_rate_difference": actual_metrics["win_rate"] - inv_metrics["win_rate"] if actual_metrics["win_rate"] is not None else None,
            "profit_factor_difference": actual_metrics["profit_factor"] - inv_metrics["profit_factor"] if (isinstance(actual_metrics["profit_factor"], float) and isinstance(inv_metrics["profit_factor"], float)) else None
        }
        
    controls["B_direction_randomization"] = direction_randomization_control(
        outcomes, 20000, seeds["direction_randomization"], 5.0, metrics_out["OVERALL"]["ALL"]["5bps"]["mean_return"] or 0.0
    )
    
    controls["C_chronological_concentration"] = chronological_concentration_control(
        [o["net_return_5bps"] for o in outcomes], 20000, seeds["chronological_permutation"], 5.0,
        metrics_out["OVERALL"]["ALL"]["5bps"]["maximum_drawdown"],
        metrics_out["OVERALL"]["ALL"]["5bps"]["longest_losing_streak"]
    )
    
    save_json(out_dir / "development_wfa_negative_controls.json", controls)

    with open(out_dir / "development_wfa_report.md", "w") as f:
        f.write("# Development Walk-Forward Analysis (WFA) V2 Report\n\n")
        f.write("DEVELOPMENT ONLY. HOLDOUT UNTOUCHED.\n")
        f.write("Underlying returns only. No options. No capital assumptions. No production-readiness claim.\n")
        f.write("SMALL SAMPLE OF 32 OUTCOMES.\n")
        
        f.write("\n## Frozen Inputs\n")
        for k, v in contract["frozen_input_hashes"].items():
            f.write(f"- `{k}`: {v}\n")
            
        f.write("\n## Fold Sizes\n")
        for i in range(5):
            f.write(f"- FOLD {i}: {metrics_out[f'FOLD_{i}']['ALL']['5bps']['trade_count']}\n")

if __name__ == "__main__":
    main()
