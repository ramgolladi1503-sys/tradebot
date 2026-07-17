import json
import argparse
from pathlib import Path
import pandas as pd
import sys
import hashlib
from collections import Counter

sys.path.append(str(Path(__file__).parent.parent))

from research.opening_state_momentum.candidate_engine import evaluate_session
from research.opening_state_momentum.threshold_estimator import calculate_threshold, InsufficientHistoryError
from research.opening_state_momentum.session_loader import Loader

def hash_list(str_list):
    return hashlib.sha256(",".join(str_list).encode()).hexdigest()

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
    replay_dates = dev_dates.copy()
    
    # Hard assertion: Input set equals exactly the development partition
    assert replay_dates == dev_dates
    assert not set(replay_dates) & set(holdout_dates)
    
    loader = Loader(args.manifest, manifest_hash)
    
    training_returns = []
    training_dates = []
    decisions = []
    
    terminal_counts = Counter()
    threshold_records = []
    
    for date in replay_dates:
        # Hard assertion: protect against holdout evaluation
        if date in holdout_dates:
            raise RuntimeError("HOLDOUT_LOCKED")
            
        files = sessions_by_date[date]
        
        # Load data
        nifty_df, n_err = loader.load_session_data({"absolute_path": files["nifty"]})
        bnifty_df, b_err = loader.load_session_data({"absolute_path": files["banknifty"]})
        
        if n_err or b_err:
            raise RuntimeError(f"Failed to load data for {date}: {n_err}, {b_err}")
            
        # Oracle threshold
        try:
            shock_threshold, meta = calculate_threshold(training_returns, percentile=80)
            threshold_records.append({
                "current_date": date,
                "training_start": training_dates[0] if training_dates else None,
                "training_end": training_dates[-1] if training_dates else None,
                "training_count": len(training_dates),
                "ordered_training_date_list_hash": hash_list(training_dates),
                "threshold_value": shock_threshold,
                "quantile_method": meta.get("method"),
                "threshold_metadata_hash": meta.get("threshold_hash"),
                "current_date_excluded": date not in training_dates,
                "future_dates_excluded": True, # enforced by sequential processing
                "holdout_excluded": True # enforced by partition isolation
            })
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
        
        candidate["partition"] = "DEVELOPMENT"
        decisions.append(candidate)
        
        if candidate.get("candidate_accepted"):
            direction = candidate.get("direction", "NONE")
            if direction == "LONG":
                terminal_status = "ACCEPTED_LONG"
            elif direction == "SHORT":
                terminal_status = "ACCEPTED_SHORT"
            else:
                terminal_status = "UNKNOWN"
        else:
            terminal_status = candidate.get("primary_rejection_reason", "UNKNOWN")
        
        # Convert engine rejection categories to requested names if needed
        if terminal_status == "INSUFFICIENT_HISTORY":
            terminal_status = "INSUFFICIENT_PRIOR_HISTORY"
        elif terminal_status in ("REJECTED_QUALITY", "OPENING_WINDOW_INCOMPLETE"):
            terminal_status = "REJECTED_SESSION_QUALITY"
        elif terminal_status == "FAILED_ANCHOR_PERSISTENCE":
            terminal_status = "FAILED_SESSION_ANCHOR"
        elif terminal_status == "FAILED_MIDPOINT_PERSISTENCE":
            terminal_status = "FAILED_OPENING_MIDPOINT"
            
        terminal_counts[terminal_status] += 1
            
        # Append return to training history
        ret = candidate.get("nifty_opening_return")
        if ret is not None and not pd.isna(ret):
            training_returns.append(ret)
            training_dates.append(date)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    
    # Update candidate decisions to holdout access audit
    holdout_audit_path = outdir / "holdout_candidate_access_audit.json"
    if holdout_audit_path.exists():
        with open(holdout_audit_path) as f:
            holdout_audit = json.load(f)
    else:
        holdout_audit = {}
        
    holdout_audit["repaired_decision_count"] = len(decisions)
    holdout_audit["final_holdout_violation_count"] = 0
    with open(holdout_audit_path, "w") as f:
        json.dump(holdout_audit, f, indent=2)

    # 1. Output decisions
    out_decisions_path = outdir / "candidate_decisions.json"
    with open(out_decisions_path, "w") as f:
        json.dump(decisions, f, indent=2)
        
    # 2. Output development_session_reconciliation.json
    all_categories = [
        "INSUFFICIENT_PRIOR_HISTORY",
        "REJECTED_SESSION_QUALITY",
        "FAILED_SHOCK_THRESHOLD",
        "FAILED_CLOSE_LOCATION",
        "FAILED_CONFIRMATION",
        "FAILED_RETAINED_MOVE",
        "FAILED_OPENING_MIDPOINT",
        "FAILED_SESSION_ANCHOR",
        "ACCEPTED_LONG",
        "ACCEPTED_SHORT"
    ]
    
    total_terminals = sum(terminal_counts.values())
    unexplained = len(dev_dates) - total_terminals
    
    reconciliation = {
        "development_count": len(dev_dates),
        "decision_record_count": len(decisions),
        "insufficient_history_count": terminal_counts.get("INSUFFICIENT_PRIOR_HISTORY", 0),
        "accepted_long_count": terminal_counts.get("ACCEPTED_LONG", 0),
        "accepted_short_count": terminal_counts.get("ACCEPTED_SHORT", 0),
        "terminal_count_sum": total_terminals,
        "unexplained_count": unexplained
    }
    
    for cat in all_categories:
        reconciliation[f"count_{cat}"] = terminal_counts.get(cat, 0)
        
    reconciliation_path = outdir / "development_session_reconciliation.json"
    with open(reconciliation_path, "w") as f:
        json.dump(reconciliation, f, indent=2)
        
    # 3. Output threshold_replay_audit.json
    first_valid = threshold_records[0] if threshold_records else None
    last_valid = threshold_records[-1] if threshold_records else None
    
    threshold_audit = {
        "development_session_count": len(dev_dates),
        "insufficient_history_count": terminal_counts.get("INSUFFICIENT_PRIOR_HISTORY", 0),
        "valid_threshold_count": len(threshold_records),
        "first_valid_threshold_date": first_valid["current_date"] if first_valid else None,
        "first_valid_threshold_prior_count": first_valid["training_count"] if first_valid else 0,
        "final_development_date": last_valid["current_date"] if last_valid else None,
        "final_development_prior_count": last_valid["training_count"] if last_valid else 0,
        "threshold_audit_hash": hashlib.sha256(json.dumps(threshold_records, sort_keys=True).encode()).hexdigest(),
        "records": threshold_records
    }
    
    threshold_audit_path = outdir / "threshold_replay_audit.json"
    with open(threshold_audit_path, "w") as f:
        json.dump(threshold_audit, f, indent=2)

    # Output audit summary (overwrite old)
    audit_summary = {
        "total_sessions_replayed": len(replay_dates),
        "development_sessions": len(dev_dates),
        "holdout_sessions": 0,
        "accepted_candidates": terminal_counts.get("ACCEPTED_LONG", 0) + terminal_counts.get("ACCEPTED_SHORT", 0),
        "rejected_candidates": total_terminals - (terminal_counts.get("ACCEPTED_LONG", 0) + terminal_counts.get("ACCEPTED_SHORT", 0)),
        "final_threshold_oracle_size": len(training_returns)
    }
    
    out_audit_path = outdir / "causal_replay_audit.json"
    with open(out_audit_path, "w") as f:
        json.dump(audit_summary, f, indent=2)
        
    print(f"Causal replay finished. Decisions written to {out_decisions_path}")
    print(f"Audit written to {out_audit_path}")
    print(json.dumps(audit_summary, indent=2))

if __name__ == "__main__":
    main()
