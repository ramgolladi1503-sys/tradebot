#!/usr/bin/env python3
import json
import argparse
from pathlib import Path
from collections import defaultdict
from datetime import datetime

def get_time_bucket(dt):
    time_str = dt.strftime("%H%M")
    val = int(time_str)
    if val < 1000: return "09:15-10:00"
    if val < 1130: return "10:00-11:30"
    if val < 1330: return "11:30-13:30"
    if val < 1445: return "13:30-14:45"
    return "14:45-15:15"

def get_dist_bucket(dist):
    if dist < 2.0: return "1.5-2.0 ATR"
    if dist < 2.5: return "2.0-2.5 ATR"
    if dist < 3.0: return "2.5-3.0 ATR"
    return ">3.0 ATR"

def get_score_bucket(score):
    if score < 80: return "70-80"
    if score < 90: return "80-90"
    return "90-100"

def get_atr_regime(atr, sym, meta):
    pcts = meta.get("atr_percentiles", {}).get(sym, {"p25": 0, "p75": 0, "p90": 0})
    if atr <= pcts["p25"]: return "low"
    if atr <= pcts["p75"]: return "normal"
    if atr <= pcts["p90"]: return "high"
    return "extreme"

def get_bars_held(entry, exit_dt):
    diff = (exit_dt - entry).total_seconds() / 60.0
    if diff <= 3: return "1-3"
    if diff <= 10: return "4-10"
    if diff <= 20: return "11-20"
    return "21-30"

class Bucket:
    def __init__(self):
        self.trades = 0
        self.wins = 0
        self.underlying_gpnl = 0.0
        self.underlying_npnl = 0.0
        self.proxy_gpnl = 0.0
        self.proxy_npnl = 0.0
        self.underlying_win_pnl = 0.0
        self.underlying_loss_pnl = 0.0
        self.same_candle_ambiguous = 0
        
    def add(self, t):
        self.trades += 1
        
        ugpnl = t.get('underlying_gross_pnl', 0)
        unpnl = t.get('underlying_net_pnl_after_index_cost', 0)
        pgpnl = t.get('proxy_option_gross_pnl', 0)
        pnpnl = t.get('proxy_option_net_pnl', 0)
        
        self.underlying_gpnl += ugpnl
        self.underlying_npnl += unpnl
        self.proxy_gpnl += pgpnl
        self.proxy_npnl += pnpnl
        
        if ugpnl > 0:
            self.wins += 1
            self.underlying_win_pnl += ugpnl
        else:
            self.underlying_loss_pnl += ugpnl
            
        if t.get('exit_reason') == "SAME_CANDLE_AMBIGUOUS_ASSUMED_STOP":
            self.same_candle_ambiguous += 1

    def metrics(self, total_trades):
        wr = self.wins / self.trades if self.trades > 0 else 0
        losses = self.trades - self.wins
        
        avg_win = self.underlying_win_pnl / self.wins if self.wins > 0 else 0
        avg_loss = self.underlying_loss_pnl / losses if losses > 0 else 0
        
        pf = abs(self.underlying_win_pnl / self.underlying_loss_pnl) if self.underlying_loss_pnl != 0 else 999.0
        
        return {
            "trades": self.trades,
            "win_rate": wr,
            "underlying_gross_expectancy": self.underlying_gpnl / self.trades if self.trades > 0 else 0,
            "underlying_net_expectancy": self.underlying_npnl / self.trades if self.trades > 0 else 0,
            "proxy_option_gross_expectancy": self.proxy_gpnl / self.trades if self.trades > 0 else 0,
            "proxy_option_net_expectancy": self.proxy_npnl / self.trades if self.trades > 0 else 0,
            "profit_factor": pf,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "cap_saturation_contribution": self.trades / total_trades if total_trades > 0 else 0,
            "same_candle_ambiguity_rate": self.same_candle_ambiguous / self.trades if self.trades > 0 else 0
        }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", type=str, required=True)
    args = parser.parse_args()
    
    base_dir = Path(f"runtime/strategy_validation/{args.strategy}")
    ledger_path = base_dir / "phase_4_trade_ledger.jsonl"
    meta_path = base_dir / "simulation_metadata.json"
    out_dir = base_dir
    
    if not ledger_path.exists() or not meta_path.exists():
        print("Trade ledger or metadata missing.")
        return
        
    with open(meta_path, "r") as f:
        meta = json.load(f)
        
    trades = []
    with open(ledger_path, "r") as f:
        for line in f:
            if line.strip():
                trades.append(json.loads(line))
                
    total_trades = len(trades)
    cohorts = defaultdict(lambda: defaultdict(Bucket))
    
    for t in trades:
        entry_dt = datetime.fromisoformat(t['entry_time'])
        exit_dt = datetime.fromisoformat(t['exit_time'])
        sym = t['symbol']
        
        dims = {
            "symbol": sym,
            "year": str(entry_dt.year),
            "month": str(entry_dt.month).zfill(2),
            "time_bucket": get_time_bucket(entry_dt),
            "direction": t['direction'],
            "extension_distance_bucket": get_dist_bucket(t.get('extension_distance', 0)),
            "selection_score_bucket": get_score_bucket(t.get('selection_score', 0)),
            "atr_regime": get_atr_regime(t.get('atr_at_entry', 0), sym, meta),
            "exit_reason": t.get('exit_reason', 'UNKNOWN'),
            "bars_held": get_bars_held(entry_dt, exit_dt)
        }
        
        for dim_name, dim_val in dims.items():
            cohorts[dim_name][dim_val].add(t)
            
    report_cohorts = {}
    for dim_name, dim_buckets in cohorts.items():
        report_cohorts[dim_name] = {}
        for dim_val, bucket in dim_buckets.items():
            report_cohorts[dim_name][dim_val] = bucket.metrics(total_trades)
            
    blockers = []
    
    edge_found = False
    for dim_name, dim_buckets in report_cohorts.items():
        for dim_val, mets in dim_buckets.items():
            if mets['trades'] >= 100 and mets['underlying_net_expectancy'] > 0:
                edge_found = True
                break
        if edge_found: break
        
    if not edge_found and total_trades > 0:
        blockers.append("COHORT_EDGE_NOT_FOUND")
        
    score_buckets = report_cohorts.get("selection_score_bucket", {})
    if score_buckets:
        top_bucket = score_buckets.get("90-100")
        if top_bucket and top_bucket['underlying_net_expectancy'] <= 0:
            blockers.append("SCORE_BUCKET_EDGE_FAILED")
            
    time_buckets = report_cohorts.get("time_bucket", {})
    all_time_negative = True
    for tb, mets in time_buckets.items():
        if mets['underlying_net_expectancy'] > 0:
            all_time_negative = False
            break
    if all_time_negative and time_buckets:
        blockers.append("TIME_BUCKET_EDGE_FAILED")
        
    sym_buckets = report_cohorts.get("symbol", {})
    if sym_buckets:
        nifty = sym_buckets.get("NIFTY")
        bank = sym_buckets.get("BANKNIFTY")
        nifty_neg = nifty['underlying_net_expectancy'] <= 0 if nifty else True
        bank_neg = bank['underlying_net_expectancy'] <= 0 if bank else True
        if nifty_neg and bank_neg:
            blockers.append("SYMBOL_EDGE_FAILED")
            
    if total_trades > 0:
        gross_pnl_total = sum(t.get('underlying_gross_pnl', 0) for t in trades)
        net_pnl_total = sum(t.get('underlying_net_pnl_after_index_cost', 0) for t in trades)
        if gross_pnl_total > 0 and net_pnl_total <= 0:
            blockers.append("COST_HURDLE_FAILED")
            
    classification = "PHASE_4_9_COHORT_EDGE_PASSED" if not blockers else "PHASE_4_9_COHORT_EDGE_FAILED"
    
    report = {
        "classification": classification,
        "strategy_id": args.strategy,
        "total_trades_analyzed": total_trades,
        "blockers": blockers,
        "cohorts": report_cohorts,
        "atr_percentiles_used": meta.get("atr_percentiles")
    }
    
    with open(out_dir / "phase_4_9_cohort_edge.json", "w") as f:
        json.dump(report, f, indent=2)
        
    print(f"Phase 4.9 Cohort Edge complete. Result: {classification}")

if __name__ == "__main__":
    main()
