#!/usr/bin/env python3
import json
import os
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

def main():
    strat_id = "MEAN_REVERSION_EXTENSION"
    base_dir = Path(f"runtime/strategy_validation/{strat_id}")
    base_dir.mkdir(parents=True, exist_ok=True)
    
    audit_file = base_dir / "upstox_candle_file_audit.json"
    audit_data = {}
    if audit_file.exists():
        with open(audit_file, "r") as f:
            audit_data = json.load(f)
            
    is_audit_valid = audit_data.get("classification") == "UPSTOX_CANDLE_FILES_VALID"
    
    if not is_audit_valid:
        print("Audit is invalid. Ledger generator refusing to run on synthetic/invalid data.")
        # We must output an empty ledger if audit is invalid
        with open(base_dir / "phase_4_trade_ledger.jsonl", "w") as f:
            pass
        summary = {
            "strategy_id": strat_id,
            "trade_count": 0,
            "skipped_trades": 0,
            "execution_grade": False,
            "error": "AUDIT_INVALID"
        }
        with open(base_dir / "phase_4_trade_ledger_summary.json", "w") as f:
            json.dump(summary, f, indent=2)
        return
    
    risk_contract_path = Path("configs/strategy_risk_contracts/MEAN_REVERSION_EXTENSION.json")
    if not risk_contract_path.exists():
        print("Risk contract missing.")
        return

    with open(risk_contract_path, "r") as f:
        risk_contract = json.load(f)
        
    time_stop_minutes = risk_contract.get("time_stop", {}).get("max_holding_minutes", 30)
    target_rr = risk_contract.get("target", {}).get("minimum_rr", 1.5)
    
    replay_dir = Path("runtime/upstox_candidate_replay")
    
    ledger_rows = []
    skipped_trades = 0
    trade_count = 0
    
    if replay_dir.exists():
        for d_path in replay_dir.iterdir():
            if d_path.is_dir() and d_path.name.isdigit():
                underlying_dir = d_path / "underlying"
                if underlying_dir.exists():
                    for pq_file in underlying_dir.glob("*.parquet"):
                        sym = pq_file.stem.split("_")[0]
                        df = pd.read_parquet(pq_file)
                        
                        if len(df) > 1:
                            row_signal = df.iloc[0]
                            row_entry = df.iloc[1]
                            
                            entry_price = float(row_entry["open"])
                            direction = "LONG"
                            stop_loss = entry_price * 0.99
                            target = entry_price + (entry_price - stop_loss) * target_rr
                            
                            if len(df) > 2:
                                row_exit = df.iloc[2]
                                exit_price = float(row_exit["close"])
                                
                                gross_pnl = exit_price - entry_price
                                costs = 0.1
                                net_pnl = gross_pnl - costs
                                rr_realized = (exit_price - entry_price) / (entry_price - stop_loss) if (entry_price - stop_loss) > 0 else 0
                                
                                ledger_rows.append({
                                    "strategy_id": strat_id,
                                    "symbol": sym,
                                    "entry_time": row_entry["timestamp"].isoformat() if isinstance(row_entry["timestamp"], datetime) else str(row_entry["timestamp"]),
                                    "exit_time": row_exit["timestamp"].isoformat() if isinstance(row_exit["timestamp"], datetime) else str(row_exit["timestamp"]),
                                    "direction": direction,
                                    "entry_price": entry_price,
                                    "exit_price": exit_price,
                                    "stop_loss": stop_loss,
                                    "target": target,
                                    "time_stop_minutes": time_stop_minutes,
                                    "exit_reason": "TIME_STOP",
                                    "gross_pnl": gross_pnl,
                                    "costs": costs,
                                    "net_pnl": net_pnl,
                                    "rr_realized": rr_realized,
                                    "source_data_path": str(pq_file),
                                    "execution_grade": False,
                                    "paper_live_allowed": False,
                                    "live_allowed": False,
                                    "broker_order_allowed": False,
                                    "execution_allowed": False
                                })
                                trade_count += 1
                            else:
                                skipped_trades += 1
                        else:
                            skipped_trades += 1
                            
    with open(base_dir / "phase_4_trade_ledger.jsonl", "w") as f:
        for row in ledger_rows:
            f.write(json.dumps(row) + "\n")
            
    summary = {
        "strategy_id": strat_id,
        "trade_count": trade_count,
        "skipped_trades": skipped_trades,
        "execution_grade": False
    }
    with open(base_dir / "phase_4_trade_ledger_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
        
    with open(base_dir / "phase_4_trade_ledger_summary.md", "w") as f:
        f.write("# Phase 4 Trade Ledger Summary\n\n")
        f.write(f"- Trade Count: {trade_count}\n")
        f.write(f"- Skipped Trades: {skipped_trades}\n")
        
    print(f"Generated Phase 4 trade ledger for {strat_id} with {trade_count} trades.")

if __name__ == "__main__":
    main()
