#!/usr/bin/env python3
import json
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", type=str, default="MEAN_REVERSION_EXTENSION")
    args = parser.parse_args()
    
    base_dir = Path(f"runtime/strategy_validation/{args.strategy}")
    ledger_path = base_dir / "phase_4_trade_ledger.jsonl"
    candidates_path = base_dir / "phase_4_candidates.jsonl"
    
    blockers = []
    
    if not ledger_path.exists():
        blockers.append("V2_LEDGER_MISSING")
        report(base_dir, blockers)
        return
        
    if not candidates_path.exists():
        blockers.append("CANDIDATE_LEDGER_MISSING")
    else:
        # Check candidate fields comprehensively
        base_reqs = ["signal_time", "symbol", "setup_type", "reject_reason", "wick_ratio", "or_high", "or_low", "signal_close"]
        next_open_reqs = ["entry_open", "stop_loss", "target", "planned_target_distance", "proxy_option_expected_move", "cost_hurdle_margin"]
        
        observed_reasons = set()
        
        with open(candidates_path, "r") as f:
            for line in f:
                if not line.strip(): continue
                c = json.loads(line)
                
                reason = c.get("reject_reason", "UNKNOWN")
                observed_reasons.add(reason)
                
                missing = False
                for req in base_reqs:
                    if req not in c:
                        missing = True
                        break
                        
                if reason not in ["WICK_TOO_WEAK"]:
                    if "htf_regime" not in c: missing = True
                    
                if reason in ["SELECTED", "NEXT_OPEN_COST_HURDLE_FAILED"]:
                    for req in next_open_reqs:
                        if req not in c:
                            missing = True
                            break
                            
                if missing:
                    if "CANDIDATE_LEDGER_FIELDS_MISSING" not in blockers:
                        blockers.append("CANDIDATE_LEDGER_FIELDS_MISSING")
                
    trades = []
    with open(ledger_path, "r") as f:
        for line in f:
            if line.strip():
                trades.append(json.loads(line))
                
    summary_path = base_dir / "phase_4_trade_ledger_summary.json"
    if summary_path.exists():
        with open(summary_path, "r") as f:
            summary = json.load(f)
            zts = summary.get("zero_trade_metrics", {}).get("zero_trade_symbol_days", 0)
            if zts == 0:
                blockers.append("ZERO_TRADE_SYMBOL_DAY_MISSING")
                
            cap = summary.get("cap_saturation_ratio", 1.0)
            if cap > 0.70:
                blockers.append("V2_CAP_SATURATION_FAILED")
                
    if len(trades) == 0:
        report(base_dir, blockers)
        return
        
    for t in trades:
        if t.get("v2_signal_version") != "1.0":
            if "V2_NOT_STRUCTURAL_REDESIGN_FAILED" not in blockers:
                blockers.append("V2_NOT_STRUCTURAL_REDESIGN_FAILED")
                
        if "setup_type" not in t or "failed_level" not in t or "rejection_quality" not in t:
            if "FAILED_BREAKOUT_CONFIRMATION_MISSING" not in blockers:
                blockers.append("FAILED_BREAKOUT_CONFIRMATION_MISSING")
                
        if "htf_regime" not in t:
            if "HTF_REGIME_FILTER_MISSING" not in blockers:
                blockers.append("HTF_REGIME_FILTER_MISSING")
                
        signal_time = t.get("signal_time")
        entry_time = t.get("entry_time")
        if not signal_time or not entry_time or signal_time == entry_time:
            if "SAME_CANDLE_ENTRY_RISK" not in blockers:
                blockers.append("SAME_CANDLE_ENTRY_RISK")
                
        if not t.get("next_open_recalculated"):
            if "NEXT_OPEN_COST_HURDLE_NOT_RECALCULATED" not in blockers:
                blockers.append("NEXT_OPEN_COST_HURDLE_NOT_RECALCULATED")
                
        target_dist = t.get("planned_target_distance")
        if target_dist is None or target_dist <= 0:
            if "COST_HURDLE_TARGET_MISMATCH" not in blockers:
                blockers.append("COST_HURDLE_TARGET_MISMATCH")
                
        entry = t.get("entry_price")
        stop = t.get("stop_loss")
        tgt = t.get("target")
        if entry and stop and tgt and entry != stop:
            rr = abs(tgt - entry) / abs(stop - entry)
            if rr < 1.4: 
                if "NEXT_OPEN_RR_MISMATCH" not in blockers:
                    blockers.append("NEXT_OPEN_RR_MISMATCH")
                
        if "cost_hurdle_margin" not in t:
            if "COST_HURDLE_FILTER_MISSING" not in blockers:
                blockers.append("COST_HURDLE_FILTER_MISSING")
        elif t["cost_hurdle_margin"] <= 0:
            if "COST_HURDLE_FILTER_FAILED" not in blockers:
                blockers.append("COST_HURDLE_FILTER_FAILED")
                
    report(base_dir, blockers)

def report(base_dir, blockers):
    out = {
        "classification": "V2_STRUCTURAL_AUDIT_PASSED" if not blockers else "V2_STRUCTURAL_AUDIT_FAILED",
        "blockers": blockers
    }
    with open(base_dir / "phase_4_v2_structural_audit.json", "w") as f:
        json.dump(out, f, indent=2)

if __name__ == "__main__":
    main()
