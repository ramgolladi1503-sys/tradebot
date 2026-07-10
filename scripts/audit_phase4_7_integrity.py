#!/usr/bin/env python3
import json
import argparse
from pathlib import Path
from collections import defaultdict

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", type=str, required=True)
    args = parser.parse_args()
    
    base_dir = Path(f"runtime/strategy_validation/{args.strategy}")
    ledger_path = base_dir / "phase_4_trade_ledger.jsonl"
    out_dir = base_dir
    
    if not ledger_path.exists():
        print("Trade ledger missing. Cannot run Phase 4.7 Integrity Audit.")
        return
        
    trades = []
    with open(ledger_path, "r") as f:
        for line in f:
            if line.strip():
                trades.append(json.loads(line))
                
    failed_blockers = set()
    
    if not trades:
        pass # Handle below
    else:
        trades_per_day_sym = defaultdict(int)
        overlaps_found = False
        same_candle_ambiguity = 0
        episodes_seen = defaultdict(int)
        
        # We need to sort trades by entry_time to check overlaps properly
        # But we can just check if any trade's entry_time is < previous trade's exit_time for the same symbol
        trades_by_sym = defaultdict(list)
        for t in trades:
            trades_by_sym[t['symbol']].append(t)
            
        for sym, sym_trades in trades_by_sym.items():
            sym_trades.sort(key=lambda x: x['entry_time'])
            
            for i in range(len(sym_trades)):
                t = sym_trades[i]
                
                # Check Overtrading
                day = t['entry_time'][:10]
                trades_per_day_sym[f"{sym}_{day}"] += 1
                
                # Check Overlaps
                if i > 0:
                    prev_t = sym_trades[i-1]
                    if t['entry_time'] < prev_t['exit_time']:
                        overlaps_found = True
                        
                # Check Same Episode Reentry
                ep_id = t.get('extension_episode_id')
                if ep_id:
                    episodes_seen[ep_id] += 1
                    
                # Check Same Candle Ambiguity
                if t.get('exit_reason') == "SAME_CANDLE_AMBIGUOUS_ASSUMED_STOP":
                    same_candle_ambiguity += 1
                    
        # Evaluate Blockers
        max_trades = max(trades_per_day_sym.values()) if trades_per_day_sym else 0
        avg_trades = sum(trades_per_day_sym.values()) / len(trades_per_day_sym) if trades_per_day_sym else 0
        
        if avg_trades > 6:
            failed_blockers.add("OVERTRADING_SANITY_FAILED")
            
        if overlaps_found:
            failed_blockers.add("OVERLAPPING_POSITION_SANITY_FAILED")
            
        max_reentries = max(episodes_seen.values()) if episodes_seen else 0
        if max_reentries > 1:
            failed_blockers.add("SAME_EXTENSION_REENTRY_FAILED")
            
        ambiguity_pct = same_candle_ambiguity / len(trades)
        if ambiguity_pct > 0.1:
            failed_blockers.add("SAME_CANDLE_FILL_AMBIGUITY_TOO_HIGH")
            
    failed_blockers = list(failed_blockers)
    classification = "PHASE_4_7_INTEGRITY_AUDIT_PASSED"
    
    if not trades:
        # If no trades but we ran Phase 4.7, it's passed but empty
        classification = "PHASE_4_7_INTEGRITY_AUDIT_PASSED"
    elif failed_blockers:
        classification = "PHASE_4_7_INTEGRITY_AUDIT_FAILED"
        
    report = {
        "classification": classification,
        "strategy_id": args.strategy,
        "trades_analyzed": len(trades),
        "blockers": failed_blockers
    }
    
    with open(out_dir / "phase_4_7_integrity_audit.json", "w") as f:
        json.dump(report, f, indent=2)
        
    with open(out_dir / "phase_4_7_integrity_audit.md", "w") as f:
        f.write("# Phase 4.7 Integrity Audit\n\n")
        f.write(f"- Classification: {classification}\n")
        f.write(f"- Trades Analyzed: {len(trades)}\n")
        if failed_blockers:
            f.write(f"- Blockers: {', '.join(failed_blockers)}\n")
            
    print(f"Phase 4.7 Integrity Audit complete. Result: {classification}")

if __name__ == "__main__":
    main()
