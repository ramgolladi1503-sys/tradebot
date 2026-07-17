import json
import argparse
from pathlib import Path
import pandas as pd
import sys
import hashlib

sys.path.append(str(Path(__file__).parent.parent))

from research.opening_state_momentum.candidate_engine import evaluate_session
from research.opening_state_momentum.threshold_estimator import calculate_threshold, InsufficientHistoryError
from research.opening_state_momentum.session_loader import Loader

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", required=True)
    parser.add_argument("--partition", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--outdir", required=True)
    args = parser.parse_args()

    # Load inputs
    with open(args.universe) as f:
        universe = json.load(f)
    with open(args.partition) as f:
        partition = json.load(f)
    with open(args.manifest) as f:
        manifest_data = json.load(f)
        
    manifest_hash = manifest_data.get("portable_dataset_hash", "UNKNOWN")
    
    # fast lookup for files by date
    sessions_by_date = {}
    for session in universe["sessions"]:
        if session["is_eligible"]:
            sessions_by_date[session["date"]] = {
                "nifty": session["nifty_file"],
                "banknifty": session["banknifty_file"]
            }

    dev_dates = partition["development"]
    holdout_dates = partition["holdout"]
    ordered_dates = dev_dates + holdout_dates
    
    loader = Loader(args.manifest, manifest_hash)
    
    training_returns = []
    decisions = []
    
    accepted_count = 0
    rejected_count = 0
    
    for date in ordered_dates:
        files = sessions_by_date[date]
        
        # Load data
        nifty_df, n_err = loader.load_session_data({"absolute_path": files["nifty"]})
        bnifty_df, b_err = loader.load_session_data({"absolute_path": files["banknifty"]})
        
        if n_err or b_err:
            raise RuntimeError(f"Failed to load data for {date}: {n_err}, {b_err}")
            
        # Oracle threshold
        try:
            shock_threshold, _ = calculate_threshold(training_returns, percentile=80)
        except InsufficientHistoryError:
            shock_threshold = None
            
        dataset_group_hash = hashlib.sha256((files["nifty"] + files["banknifty"]).encode()).hexdigest()
        
        candidate = evaluate_session(
            session_date=date,
            nifty_df=nifty_df,
            banknifty_df=bnifty_df,
            shock_threshold=shock_threshold,
            manifest_hash=manifest_hash,
            dataset_group_hash=dataset_group_hash
        )
        
        candidate["partition"] = "DEVELOPMENT" if date in dev_dates else "HOLDOUT"
        decisions.append(candidate)
        
        if candidate["candidate_accepted"]:
            accepted_count += 1
        else:
            rejected_count += 1
            
        # If development, its return is appended to training_returns for FUTURE thresholds
        if date in dev_dates:
            # We must use its true NIFTY return, which is extracted by engine even if rejected
            ret = candidate.get("nifty_opening_return")
            if ret is not None and not pd.isna(ret):
                training_returns.append(ret)

    # Output decisions
    out_decisions_path = Path(args.outdir) / "candidate_decisions.json"
    with open(out_decisions_path, "w") as f:
        json.dump(decisions, f, indent=2)
        
    # Output audit summary
    audit_summary = {
        "total_sessions_replayed": len(ordered_dates),
        "development_sessions": len(dev_dates),
        "holdout_sessions": len(holdout_dates),
        "accepted_candidates": accepted_count,
        "rejected_candidates": rejected_count,
        "final_threshold_oracle_size": len(training_returns)
    }
    
    out_audit_path = Path(args.outdir) / "causal_replay_audit.json"
    with open(out_audit_path, "w") as f:
        json.dump(audit_summary, f, indent=2)
        
    print(f"Causal replay finished. Decisions written to {out_decisions_path}")
    print(f"Audit written to {out_audit_path}")
    print(json.dumps(audit_summary, indent=2))

if __name__ == "__main__":
    main()
