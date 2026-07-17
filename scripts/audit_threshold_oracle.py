import json
import argparse
from pathlib import Path
import pandas as pd
import numpy as np
import sys
import hashlib

def hash_list(str_list):
    return hashlib.sha256(",".join(str_list).encode()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", required=True)
    parser.add_argument("--partition", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--outdir", required=True)
    args = parser.parse_args()

    # We must not import the actual strategy modules.
    # We will load data directly via pandas

    with open(args.universe) as f:
        universe = json.load(f)
    with open(args.partition) as f:
        partition = json.load(f)
        
    dev_dates = partition["development"]
    
    sessions_by_date = {}
    for session in universe["sessions"]:
        if session["is_eligible"]:
            sessions_by_date[session["date"]] = session["nifty_file"]
            
    training_returns = []
    training_dates = []
    
    oracle_results = {}
    
    for i, date in enumerate(dev_dates):
        nifty_file = sessions_by_date[date]
        df = pd.read_parquet(nifty_file)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')
        
        n_times = df['timestamp'].dt.time
        open_start = pd.Timestamp("09:15:00").time()
        open_end = pd.Timestamp("09:44:00").time()
        
        n_open = df[(n_times >= open_start) & (n_times <= open_end)]
        session_open = float(n_open.iloc[0]["open"])
        opening_close = float(n_open.iloc[-1]["close"])
        ret = (opening_close / session_open) - 1.0
        
        if len(training_returns) < 60:
            threshold = None
        else:
            threshold = np.percentile(np.abs(training_returns), 80, method='linear')
            
        oracle_results[date] = {
            "training_count": len(training_returns),
            "threshold": threshold,
            "training_hash": hash_list(training_dates)
        }
        
        training_returns.append(ret)
        training_dates.append(date)

    outdir = Path(args.outdir)
    with open(outdir / "threshold_replay_audit.json") as f:
        replay_audit = json.load(f)
        
    replay_records = {r["current_date"]: r for r in replay_audit["records"]}
    
    comparison = {
        "mismatches": 0,
        "comparisons": []
    }
    
    # Check specific indices:
    # first (0), 60th (59), 61st (60), middle (199), final (-1)
    indices_to_check = [0, 59, 60, 199, len(dev_dates) - 1]
    
    for idx in indices_to_check:
        if idx >= len(dev_dates):
            continue
        date = dev_dates[idx]
        oracle_res = oracle_results[date]
        replay_res = replay_records.get(date, {})
        
        replay_thresh = replay_res.get("threshold_value")
        
        match = True
        if oracle_res["threshold"] is None and replay_thresh is not None:
            match = False
        elif oracle_res["threshold"] is not None and replay_thresh is None:
            match = False
        elif oracle_res["threshold"] is not None and replay_thresh is not None:
            if abs(oracle_res["threshold"] - replay_thresh) > 1e-9:
                match = False
                
        # Also check hash
        replay_hash = replay_res.get("ordered_training_date_list_hash")
        
        if oracle_res["training_count"] >= 60 and replay_hash != oracle_res["training_hash"]:
            match = False
            
        if not match:
            comparison["mismatches"] += 1
            
        comparison["comparisons"].append({
            "session_index": idx + 1,
            "date": date,
            "oracle_threshold": oracle_res["threshold"],
            "replay_threshold": replay_thresh,
            "oracle_training_count": oracle_res["training_count"],
            "replay_training_count": replay_res.get("training_count"),
            "hash_match": replay_hash == oracle_res["training_hash"] if oracle_res["training_count"] >= 60 else True,
            "match": match
        })
        
    with open(outdir / "threshold_oracle_comparison.json", "w") as f:
        json.dump(comparison, f, indent=2)
        
    print(f"Oracle comparison completed. Mismatches: {comparison['mismatches']}")

if __name__ == "__main__":
    main()
