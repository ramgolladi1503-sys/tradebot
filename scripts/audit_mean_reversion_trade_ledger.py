#!/usr/bin/env python3
import json
import os
from pathlib import Path
from datetime import datetime

def parse_iso(dt_str):
    try:
        return datetime.fromisoformat(dt_str)
    except:
        return None

def main():
    strat_id = "MEAN_REVERSION_EXTENSION"
    base_dir = Path(f"runtime/strategy_validation/{strat_id}")
    ledger_path = base_dir / "phase_4_trade_ledger.jsonl"
    
    if not ledger_path.exists():
        print("No trade ledger to audit.")
        return
        
    trades = []
    with open(ledger_path, "r") as f:
        for line in f:
            if line.strip():
                trades.append(json.loads(line))
                
    trade_count = len(trades)
    suspicious_blockers = []
    failed_blockers = []
    
    if trade_count == 0:
        print("Empty ledger.")
        return
        
    wins = 0
    gross_pnl_sum = 0
    net_pnl_sum = 0
    gross_losses = 0
    gross_wins = 0
    
    for t in trades:
        entry_time = parse_iso(t.get("entry_time"))
        exit_time = parse_iso(t.get("exit_time"))
        
        # 1. No same-candle entry/exit unless explicitly allowed (not allowed here)
        if entry_time and exit_time and entry_time == exit_time:
            failed_blockers.append("LOOKAHEAD_OR_SAME_CANDLE_FILL_RISK")
            
        # 8. PnL recomputation
        expected_gross = t["exit_price"] - t["entry_price"] if t["direction"] == "LONG" else t["entry_price"] - t["exit_price"]
        if abs(expected_gross - t.get("gross_pnl", 0)) > 0.001:
            failed_blockers.append("PNL_MISMATCH")
            
        expected_net = expected_gross - t.get("costs", 0)
        if abs(expected_net - t.get("net_pnl", 0)) > 0.001:
            failed_blockers.append("PNL_MISMATCH")
            
        # 9. RR formula
        # risk = entry - stop_loss (for LONG)
        risk = t["entry_price"] - t["stop_loss"] if t["direction"] == "LONG" else t["stop_loss"] - t["entry_price"]
        expected_rr = expected_gross / risk if risk > 0 else 0
        if abs(expected_rr - t.get("rr_realized", 0)) > 0.001:
            failed_blockers.append("RR_MISMATCH")
            
        if t.get("net_pnl", 0) > 0:
            wins += 1
            gross_wins += t.get("net_pnl", 0)
        else:
            gross_losses += abs(t.get("net_pnl", 0))
            
    win_rate = wins / trade_count
    
    # 11. Suspicious perfect win rate
    if win_rate == 1.0 and trade_count > 20:
        suspicious_blockers.append("SUSPICIOUS_PERFECT_WIN_RATE")
        
    # 10. Profit factor formula and > 50 check
    profit_factor = gross_wins / gross_losses if gross_losses > 0 else 999.0
    if profit_factor > 50:
        suspicious_blockers.append("SUSPICIOUS_PROFIT_FACTOR")
        
    failed_blockers = list(set(failed_blockers))
    suspicious_blockers = list(set(suspicious_blockers))
    
    if failed_blockers:
        classification = "TRADE_LEDGER_AUDIT_FAILED"
    elif suspicious_blockers:
        classification = "TRADE_LEDGER_AUDIT_SUSPICIOUS"
    else:
        classification = "TRADE_LEDGER_AUDIT_PASSED"
        
    audit_report = {
        "classification": classification,
        "trade_count": trade_count,
        "failed_blockers": failed_blockers,
        "suspicious_blockers": suspicious_blockers,
        "win_rate": win_rate,
        "profit_factor": profit_factor
    }
    
    with open(base_dir / "phase_4_trade_ledger_audit.json", "w") as f:
        json.dump(audit_report, f, indent=2)
        
    with open(base_dir / "phase_4_trade_ledger_audit.md", "w") as f:
        f.write("# Phase 4 Trade Ledger Audit\n\n")
        f.write(f"- Classification: {classification}\n")
        f.write(f"- Trade Count: {trade_count}\n")
        if failed_blockers:
            f.write(f"- Failed Blockers: {', '.join(failed_blockers)}\n")
        if suspicious_blockers:
            f.write(f"- Suspicious Blockers: {', '.join(suspicious_blockers)}\n")

    print(f"Audited Phase 4 trade ledger. Result: {classification}")

if __name__ == "__main__":
    main()
