import argparse
import sys
import json
from pathlib import Path

# Ensure research package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.opening_state_momentum.session_loader import Loader
from research.opening_state_momentum.partition import partition_sessions, PartitionGuard
from research.opening_state_momentum.candidate_engine import evaluate_session
from research.opening_state_momentum.threshold_estimator import calculate_threshold, InsufficientHistoryError

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--hash", required=True)
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--eval-holdout-outcomes", action="store_true")
    args = parser.parse_args()
    
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    
    # 1. Initialize loader and check manifest hash
    loader = Loader(args.manifest, args.hash)
    
    # Group NIFTY and BANKNIFTY files by session date
    session_files = {}
    for f in loader.eligible_files:
        rel_path = f.get("relative_path", "")
        parts = rel_path.split("/")
        if len(parts) < 3:
            continue
        date_raw = parts[0]
        if len(date_raw) == 8 and date_raw.isdigit():
            date = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:]}"
        else:
            continue
            
        if date not in session_files:
            session_files[date] = {"nifty": None, "banknifty": None}
            
        # Exact matching using the file's base name which includes the date suffix
        filename = Path(rel_path).stem
        if filename == f"BANKNIFTY_{date_raw}":
            session_files[date]["banknifty"] = f
        elif filename == f"NIFTY_{date_raw}":
            session_files[date]["nifty"] = f
            
    # Statically eligible dates only
    eligible_dates = []
    for date in sorted(list(session_files.keys())):
        if session_files[date]["nifty"] is not None and session_files[date]["banknifty"] is not None:
            eligible_dates.append(date)
            
    # 2. Partition sessions
    dev_dates, holdout_dates, partition_meta = partition_sessions(eligible_dates)
    
    # Save partition metadata
    with open(outdir / "research_partition.json", "w") as f:
        json.dump({
            "partition_metadata": partition_meta,
            "development_sessions": dev_dates,
            "holdout_sessions": holdout_dates
        }, f, indent=2)
        
    # Guard holdout outcome evaluation
    guard = PartitionGuard(holdout_dates)
    if args.eval_holdout_outcomes:
        # Should raise HOLDOUT_LOCKED
        for date in holdout_dates:
            guard.check_access(date, "evaluate_outcome")
            
    # 3. Candidate Replay over DEVELOPMENT sessions
    results = []
    prior_returns = []
    
    for date in dev_dates:
        records = session_files[date]
        
        nifty_df, n_err = loader.load_session_data(records["nifty"])
        bnifty_df, b_err = loader.load_session_data(records["banknifty"])
        
        group_hash = loader.manifest_data.get("portable_dataset_hash")
        
        # Calculate shock threshold dynamically
        try:
            shock_threshold, meta = calculate_threshold(prior_returns, percentile=80)
        except InsufficientHistoryError:
            shock_threshold = None
            
        cand = evaluate_session(
            session_date=date,
            nifty_df=nifty_df,
            banknifty_df=bnifty_df,
            shock_threshold=shock_threshold,
            manifest_hash=args.hash,
            dataset_group_hash=group_hash
        )
        
        # Keep track of valid returns if the session data was actually loaded correctly and passed quality gates
        if cand["session_quality_status"] == "PASSED":
            prior_returns.append(cand["nifty_opening_return"])
            
        results.append(cand)
        
    # Save candidate decision rows
    # Sort by date for determinism
    results.sort(key=lambda x: x["session_date"])
    
    with open(outdir / "candidate_decisions.json", "w") as f:
        json.dump(results, f, indent=2)
        
    print(f"Replay completed. Processed {len(dev_dates)} dev sessions. Emitted {len(results)} candidate results.")

if __name__ == "__main__":
    main()
