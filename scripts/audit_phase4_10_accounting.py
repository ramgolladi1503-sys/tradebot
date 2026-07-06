#!/usr/bin/env python3
import json
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", type=str, required=True)
    args = parser.parse_args()
    
    base_dir = Path(f"runtime/strategy_validation/{args.strategy}")
    ledger_path = base_dir / "phase_4_trade_ledger.jsonl"
    out_dir = base_dir
    
    if not ledger_path.exists():
        print("Trade ledger missing. Cannot run Phase 4.10 Accounting Audit.")
        return
        
    trades = []
    with open(ledger_path, "r") as f:
        for line in f:
            if line.strip():
                trades.append(json.loads(line))
                
    total_trades = len(trades)
    if total_trades == 0:
        print("No trades to audit.")
        return
        
    # Calculate dimensional expectancy
    underlying_gpnl = sum(t.get('underlying_gross_pnl', 0) for t in trades)
    underlying_npnl = sum(t.get('underlying_net_pnl_after_index_cost', 0) for t in trades)
    proxy_gpnl = sum(t.get('proxy_option_gross_pnl', 0) for t in trades)
    proxy_npnl = sum(t.get('proxy_option_net_pnl', 0) for t in trades)
    
    underlying_g_exp = underlying_gpnl / total_trades
    underlying_n_exp = underlying_npnl / total_trades
    proxy_g_exp = proxy_gpnl / total_trades
    proxy_n_exp = proxy_npnl / total_trades
    
    cost_mode = trades[0].get('pnl_model', 'UNKNOWN')
    
    blockers = []
    
    # Require clear proxy option model logic for live execution if we want to claim option edge
    if cost_mode not in ["UNDERLYING_INDEX_PROXY_FIXED_HURDLE", "DELTA_PROXY_OPTION"]:
        blockers.append("UNKNOWN_COST_MODEL_USED")
        
    if cost_mode == "UNDERLYING_INDEX_PROXY_FIXED_HURDLE":
        gated_expectancy = underlying_n_exp
    else:
        gated_expectancy = proxy_n_exp
        
    if gated_expectancy <= 0:
        blockers.append("MINIMUM_DIMENSIONAL_EXPECTANCY_NOT_MET")
        
    classification = "PHASE_4_10_ACCOUNTING_PASSED" if not blockers else "PHASE_4_10_ACCOUNTING_FAILED"
    
    report = {
        "classification": classification,
        "strategy_id": args.strategy,
        "blockers": blockers,
        "metrics": {
            "total_trades": total_trades,
            "underlying_gross_expectancy": underlying_g_exp,
            "underlying_net_expectancy_after_index_cost": underlying_n_exp,
            "proxy_option_gross_expectancy": proxy_g_exp,
            "proxy_option_net_expectancy": proxy_n_exp,
            "cost_hurdle_used": 8.5 if cost_mode == "UNDERLYING_INDEX_PROXY_FIXED_HURDLE" else 1.5,
            "pnl_model_used_for_gate": cost_mode,
            "gated_expectancy": gated_expectancy
        }
    }
    
    with open(out_dir / "phase_4_10_accounting_audit.json", "w") as f:
        json.dump(report, f, indent=2)
        
    print(f"Phase 4.10 Accounting Audit complete. Result: {classification}")

if __name__ == "__main__":
    main()
