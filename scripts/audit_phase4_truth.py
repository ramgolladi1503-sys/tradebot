#!/usr/bin/env python3
import json
import argparse
from pathlib import Path
from collections import Counter
import statistics

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", type=str, required=True)
    args = parser.parse_args()
    
    base_dir = Path(f"runtime/strategy_validation/{args.strategy}")
    ledger_path = base_dir / "phase_4_trade_ledger.jsonl"
    out_dir = base_dir
    
    if not ledger_path.exists():
        print("Trade ledger missing. Cannot run Phase 4.5 Truth Audit.")
        return
        
    trades = []
    with open(ledger_path, "r") as f:
        for line in f:
            if line.strip():
                trades.append(json.loads(line))
                
    failed_blockers = []
    
    if not trades:
        failed_blockers.append("TRADES_MISSING")
    else:
        # Trade Frequency Sanity Check
        trades_per_day = Counter()
        for t in trades:
            day = t.get("entry_time")[:10] if t.get("entry_time") else "UNKNOWN"
            trades_per_day[day] += 1
            
        counts = list(trades_per_day.values())
        if counts:
            if len(counts) > 1:
                variance = statistics.variance(counts)
            else:
                variance = 0.0
                
            if variance == 0.0 and len(counts) > 10:
                # If it's a mechanical generator outputting exactly X trades every day without fail
                failed_blockers.append("TRADE_FREQUENCY_SANITY_FAILED_MECHANICAL_MOCK")
                
        # Option Realism Check
        for t in trades:
            if t.get("is_index_proxy"):
                if t.get("costs", 8.5) < 5.0:
                    if "OPTION_REALISM_FAILED_INSUFFICIENT_INDEX_PROXY_SLIPPAGE" not in blockers: blockers.append("OPTION_REALISM_FAILED_INSUFFICIENT_INDEX_PROXY_SLIPPAGE")
                    break
                    
    classification = "PHASE_4_5_TRUTH_AUDIT_PASSED"
    if failed_blockers:
        classification = "PHASE_4_5_TRUTH_AUDIT_FAILED"
        
    report = {
        "classification": classification,
        "strategy_id": args.strategy,
        "trades_analyzed": len(trades),
        "blockers": failed_blockers
    }
    
    with open(out_dir / "phase_4_5_truth_audit.json", "w") as f:
        json.dump(report, f, indent=2)
        
    with open(out_dir / "phase_4_5_truth_audit.md", "w") as f:
        f.write("# Phase 4.5 Truth Audit\n\n")
        f.write(f"- Classification: {classification}\n")
        f.write(f"- Trades Analyzed: {len(trades)}\n")
        if failed_blockers:
            f.write(f"- Blockers: {', '.join(failed_blockers)}\n")
            
    print(f"Phase 4.5 Truth Audit complete. Result: {classification}")

if __name__ == "__main__":
    main()
