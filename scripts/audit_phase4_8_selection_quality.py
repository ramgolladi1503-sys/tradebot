#!/usr/bin/env python3
import json
import argparse
import numpy as np
from pathlib import Path
from collections import defaultdict

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", type=str, required=True)
    args = parser.parse_args()
    
    base_dir = Path(f"runtime/strategy_validation/{args.strategy}")
    candidates_path = base_dir / "phase_4_candidates.jsonl"
    meta_path = base_dir / "simulation_metadata.json"
    out_dir = base_dir
    
    if not candidates_path.exists() or not meta_path.exists():
        print("Candidates log or metadata missing. Cannot run Phase 4.8 Selection Quality Audit.")
        return
        
    with open(meta_path, "r") as f:
        meta = json.load(f)
        
    active_symbol_days = meta.get("active_symbol_days", 0)
    max_trades_per_symbol_day = meta.get("max_trades_per_symbol_day", 6)
    max_possible_trades = active_symbol_days * max_trades_per_symbol_day
    
    selected_scores = []
    rejected_scores = []
    symbol_day_counts = defaultdict(int)
    
    with open(candidates_path, "r") as f:
        for line in f:
            if line.strip():
                cand = json.loads(line)
                score = cand.get('score', 0)
                if cand.get('selected'):
                    selected_scores.append(score)
                    
                    # Track cap
                    sym = cand.get('symbol')
                    ts = cand.get('timestamp')
                    if ts:
                        day = ts[:10]
                        symbol_day_counts[f"{sym}_{day}"] += 1
                else:
                    rejected_scores.append(score)
                    
    selected_count = len(selected_scores)
    
    # 1. Capacity accounting invariant
    failed_blockers = set()
    
    if selected_count > max_possible_trades:
        failed_blockers.add("CAPACITY_ACCOUNTING_INVARIANT_FAILED")
        
    cap_saturation_ratio = selected_count / max_possible_trades if max_possible_trades > 0 else 0
    capped_days = sum(1 for k, v in symbol_day_counts.items() if v >= max_trades_per_symbol_day)
    percent_symbol_days_at_cap = capped_days / active_symbol_days if active_symbol_days > 0 else 0
    
    zero_trade_days = active_symbol_days - len(symbol_day_counts)
    one_trade_days = sum(1 for k, v in symbol_day_counts.items() if v == 1)
    
    if selected_scores:
        sel_min = float(np.min(selected_scores))
        sel_p25 = float(np.percentile(selected_scores, 25))
        sel_p50 = float(np.percentile(selected_scores, 50))
        sel_p75 = float(np.percentile(selected_scores, 75))
        sel_max = float(np.max(selected_scores))
    else:
        sel_min = sel_p25 = sel_p50 = sel_p75 = sel_max = 0.0
        
    if rejected_scores:
        rej_p50 = float(np.percentile(rejected_scores, 50))
    else:
        rej_p50 = 0.0
        
    score_gap = sel_p50 - rej_p50
    
    if cap_saturation_ratio > 0.70:
        failed_blockers.add("SELECTION_CAP_SATURATION_FAILED")
    if percent_symbol_days_at_cap > 0.40:
        failed_blockers.add("SYMBOL_DAY_CAP_SATURATION_FAILED")
    if score_gap < 5 and selected_count > 0 and rejected_scores:
        failed_blockers.add("WEAK_SCORE_SEPARATION_FAILED")
        
    failed_blockers = list(failed_blockers)
    classification = "PHASE_4_8_SELECTION_QUALITY_PASSED" if not failed_blockers else "PHASE_4_8_SELECTION_QUALITY_FAILED"
    
    report = {
        "classification": classification,
        "strategy_id": args.strategy,
        "blockers": failed_blockers,
        "metrics": {
            "selected_score_min": sel_min,
            "selected_score_p25": sel_p25,
            "selected_score_p50": sel_p50,
            "selected_score_p75": sel_p75,
            "selected_score_max": sel_max,
            "rejected_score_p50": rej_p50,
            "selected_vs_rejected_score_gap": score_gap,
            
            # Accounting invariant metrics
            "parquet_symbol_days": active_symbol_days,
            "candidate_symbol_days": len(symbol_day_counts),
            "ledger_symbol_days": len(symbol_day_counts),
            "active_symbol_days_used_for_capacity": active_symbol_days,
            "selected_trades": selected_count,
            "max_trades_per_symbol_day": max_trades_per_symbol_day,
            "max_possible_trades": max_possible_trades,
            "selected_minus_capacity": selected_count - max_possible_trades,
            "symbol_days_missing_from_candidates": zero_trade_days,
            "symbol_days_missing_from_ledger": zero_trade_days,
            
            "cap_saturation_ratio": cap_saturation_ratio,
            "symbol_days_at_cap": capped_days,
            "percent_symbol_days_at_cap": percent_symbol_days_at_cap,
            "zero_trade_days": zero_trade_days,
            "one_trade_days": one_trade_days,
            "capped_trade_days": capped_days
        }
    }
    
    with open(out_dir / "phase_4_8_selection_quality_audit.json", "w") as f:
        json.dump(report, f, indent=2)
        
    print(f"Phase 4.8 Selection Quality Audit complete. Result: {classification}")

if __name__ == "__main__":
    main()
