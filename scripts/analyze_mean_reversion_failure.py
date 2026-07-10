#!/usr/bin/env python3
import json
from pathlib import Path
from collections import Counter
from datetime import datetime

def parse_iso(dt_str):
    if not dt_str: return None
    try:
        return datetime.fromisoformat(dt_str)
    except:
        return None

def main():
    strat_id = "MEAN_REVERSION_EXTENSION"
    base_dir = Path(f"runtime/strategy_validation/{strat_id}")
    ledger_path = base_dir / "phase_4_trade_ledger.jsonl"
    
    if not ledger_path.exists():
        classification = "MEAN_REVERSION_FAILURE_ATTRIBUTION_BLOCKED_LEDGER_MISSING"
        print(classification)
        with open(base_dir / "phase_4_failure_attribution.json", "w") as f:
            json.dump({"classification": classification}, f)
        return

    trades = []
    with open(ledger_path, "r") as f:
        for line in f:
            if line.strip():
                trades.append(json.loads(line))
                
    if not trades:
        classification = "MEAN_REVERSION_FAILURE_ATTRIBUTION_BLOCKED_LEDGER_MISSING"
        print(classification)
        with open(base_dir / "phase_4_failure_attribution.json", "w") as f:
            json.dump({"classification": classification}, f)
        return

    total_trades = len(trades)
    wins = 0
    losses = 0
    pnl_by_symbol = Counter()
    pnl_by_dir = Counter()
    pnl_by_hour = Counter()
    pnl_by_reason = Counter()
    exit_reasons = Counter()
    
    stop_hits = 0
    target_hits = 0
    time_stop_exits = 0
    session_end_exits = 0
    invalidated_exits = 0
    
    holding_times = []
    
    direction_inversion_profitable_count = 0
    cost_model_punitive_count = 0
    
    for t in trades:
        net_pnl = t.get("net_pnl", 0)
        gross_pnl = t.get("gross_pnl", 0)
        costs = t.get("costs", 0)
        direction = t.get("direction", "LONG")
        sym = t.get("symbol", "UNKNOWN")
        reason = t.get("exit_reason", "UNKNOWN")
        
        if net_pnl > 0:
            wins += 1
        else:
            losses += 1
            
        pnl_by_symbol[sym] += net_pnl
        pnl_by_dir[direction] += net_pnl
        pnl_by_reason[reason] += net_pnl
        exit_reasons[reason] += 1
        
        # Reason counts
        if reason == "STOP_LOSS": stop_hits += 1
        elif reason == "TARGET": target_hits += 1
        elif reason == "TIME_STOP": time_stop_exits += 1
        elif reason == "SESSION_END": session_end_exits += 1
        elif reason == "INVALIDATED": invalidated_exits += 1
        
        entry_t = parse_iso(t.get("entry_time"))
        exit_t = parse_iso(t.get("exit_time"))
        if entry_t and exit_t:
            holding_times.append((exit_t - entry_t).total_seconds())
            pnl_by_hour[entry_t.hour] += net_pnl
            
        # Inversion check
        # If we inverted direction, gross_pnl would be -gross_pnl
        inv_net = (-gross_pnl) - costs
        if net_pnl <= 0 and inv_net > 0:
            direction_inversion_profitable_count += 1
            
        if net_pnl <= 0 and gross_pnl > 0:
            cost_model_punitive_count += 1
            
    avg_holding_time = sum(holding_times) / len(holding_times) if holding_times else 0
    
    sorted_trades = sorted(trades, key=lambda x: x.get("net_pnl", 0))
    worst_trades = sorted_trades[:10]
    best_trades = sorted_trades[-10:]
    best_trades.reverse()
    
    # Heuristics
    direction_inversion_suspected = direction_inversion_profitable_count > (total_trades * 0.5)
    cost_model_too_punitive = cost_model_punitive_count > (total_trades * 0.5)
    
    all_pnl = [t.get("net_pnl", 0) for t in trades]
    constant_pnl_bug = len(set(all_pnl)) == 1 and total_trades > 1
    exit_logic_monoculture = len(exit_reasons) == 1 and total_trades > 1
    pnl_sign_bug = all(pnl < 0 for pnl in all_pnl) and total_trades > 10 # heuristic
    
    target_unreachable = target_hits == 0 and total_trades > 20
    stop_too_tight = stop_hits > (total_trades * 0.8)
    time_stop_too_early = time_stop_exits > (total_trades * 0.8)
    trend_continuation_suspected = direction_inversion_suspected and total_trades > 20
    
    # Classification logic
    if constant_pnl_bug or pnl_sign_bug or direction_inversion_suspected:
        classification = "MEAN_REVERSION_FAILURE_ATTRIBUTION_IMPLEMENTATION_BUG_SUSPECTED"
    elif stop_too_tight or time_stop_too_early or cost_model_too_punitive:
        classification = "MEAN_REVERSION_FAILURE_ATTRIBUTION_RISK_CONTRACT_SUSPECTED"
    elif target_unreachable or trend_continuation_suspected:
        classification = "MEAN_REVERSION_FAILURE_ATTRIBUTION_STRATEGY_EDGE_NOT_FOUND"
    else:
        classification = "MEAN_REVERSION_FAILURE_ATTRIBUTION_STRATEGY_EDGE_NOT_FOUND"
        
    report = {
        "classification": classification,
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "pnl_by_symbol": dict(pnl_by_symbol),
        "pnl_by_direction": dict(pnl_by_dir),
        "pnl_by_hour": dict(pnl_by_hour),
        "pnl_by_exit_reason": dict(pnl_by_reason),
        "exit_reason_distribution": dict(exit_reasons),
        "average_holding_time_seconds": avg_holding_time,
        "stop_hits": stop_hits,
        "target_hits": target_hits,
        "time_stop_exits": time_stop_exits,
        "session_end_exits": session_end_exits,
        "invalidated_exits": invalidated_exits,
        "direction_inversion_suspected": direction_inversion_suspected,
        "pnl_sign_bug_suspected": pnl_sign_bug,
        "constant_pnl_bug_suspected": constant_pnl_bug,
        "exit_logic_monoculture_suspected": exit_logic_monoculture,
        "cost_model_too_punitive": cost_model_too_punitive,
        "target_unreachable": target_unreachable,
        "stop_too_tight": stop_too_tight,
        "time_stop_too_early": time_stop_too_early,
        "trend_continuation_suspected": trend_continuation_suspected,
        "risk_contract_failure_suspected": classification == "MEAN_REVERSION_FAILURE_ATTRIBUTION_RISK_CONTRACT_SUSPECTED",
        "implementation_bug_suspected": classification == "MEAN_REVERSION_FAILURE_ATTRIBUTION_IMPLEMENTATION_BUG_SUSPECTED",
        "strategy_edge_not_found": classification == "MEAN_REVERSION_FAILURE_ATTRIBUTION_STRATEGY_EDGE_NOT_FOUND",
        "top_10_worst_trades": worst_trades,
        "top_10_best_trades": best_trades
    }

    with open(base_dir / "phase_4_failure_attribution.json", "w") as f:
        json.dump(report, f, indent=2)
        
    with open(base_dir / "phase_4_failure_attribution.md", "w") as f:
        f.write("# Failure Attribution Report\n\n")
        f.write(f"- Classification: {classification}\n")
        f.write(f"- Total Trades: {total_trades}\n")
        f.write(f"- Wins: {wins}, Losses: {losses}\n")
        f.write(f"- Direction Inversion Suspected: {direction_inversion_suspected}\n")
        f.write(f"- Constant PnL Bug: {constant_pnl_bug}\n")
        f.write(f"- Exit Monoculture: {exit_logic_monoculture}\n")
        
    print(f"Generated failure attribution. Result: {classification}")

if __name__ == "__main__":
    main()
