import os
import sys
import json
import argparse
from pathlib import Path

repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from research.opening_state_momentum.contract import STRATEGY_ID, STRATEGY_VERSION, get_contract_hash, CONTRACT_PARAMS as STRAT_PARAMS
from research.opening_state_momentum.outcome_contract import OUTCOME_ID, OUTCOME_VERSION, get_outcome_contract_hash, CONTRACT_PARAMS as OUTCOME_PARAMS
from research.opening_state_momentum.session_loader import Loader
from research.opening_state_momentum.outcome_labeler import label_outcome
from research.opening_state_momentum.outcome_fingerprints import compute_outcome_fingerprint

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--decisions", required=True)
    parser.add_argument("--partition", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--manifest-hash", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    
    with open(args.partition) as f:
        partition = json.load(f)
    
    with open(args.decisions) as f:
        decisions = json.load(f)
        
    dev_dates = set(partition.get("development", []))
    holdout_dates = set(partition.get("holdout", []))
    part_hash = partition.get("metadata", {}).get("partition_hash", "UNKNOWN")
    dataset_group_hash = partition.get("metadata", {}).get("dataset_group_hash", "UNKNOWN")
    
    loader = Loader(args.manifest, args.manifest_hash)
    
    outcomes = []
    recon = {
        "accepted_development_candidates": 0,
        "labelled_outcomes": 0,
        "accepted_long_labels": 0,
        "accepted_short_labels": 0,
        "count_ENTRY_BAR_MISSING": 0,
        "count_EXIT_BAR_MISSING": 0,
        "count_ENTRY_PRICE_INVALID": 0,
        "count_EXIT_PRICE_INVALID": 0,
        "count_ENTRY_EXIT_ORDER_INVALID": 0,
        "count_SOURCE_MANIFEST_MISMATCH": 0,
        "count_HOLDOUT_LOCKED": 0,
        "holdout_outcome_count": 0,
        "unexplained_count": 0
    }
    
    outcome_dates = set()
    
    strat_hash = get_contract_hash()
    out_hash = get_outcome_contract_hash()
    
    for cand in decisions:
        if cand.get("status") != "ACCEPTED":
            continue
            
        date = cand["session_date"]
        
        if date in holdout_dates:
            recon["count_HOLDOUT_LOCKED"] += 1
            recon["holdout_outcome_count"] += 1
            out = {"status": "HOLDOUT_LOCKED"}
        elif date not in dev_dates:
            recon["unexplained_count"] += 1
            continue
        else:
            recon["accepted_development_candidates"] += 1
            outcome_dates.add(date)
            
            # Find NIFTY file
            file_record = None
            for f in loader.eligible_files:
                if f["session_date"] == date and "NIFTY" in f["instruments"]:
                    file_record = f
                    break
                    
            if not file_record:
                out = {"status": "SOURCE_MANIFEST_MISMATCH"}
                recon["count_SOURCE_MANIFEST_MISMATCH"] += 1
            else:
                df, errs = loader.load_session_data(file_record)
                if errs:
                    out = {"status": "SOURCE_MANIFEST_MISMATCH"}
                    recon["count_SOURCE_MANIFEST_MISMATCH"] += 1
                else:
                    out = label_outcome(df, cand["direction"], date)
                    
                    if out["status"] == "OUTCOME_LABELLED":
                        recon["labelled_outcomes"] += 1
                        if cand["direction"] > 0:
                            recon["accepted_long_labels"] += 1
                        else:
                            recon["accepted_short_labels"] += 1
                    else:
                        recon[f"count_{out['status']}"] += 1
                        
        # Construct immutable record
        record = {
            "strategy_id": STRATEGY_ID,
            "strategy_version": STRATEGY_VERSION,
            "strategy_contract_hash": strat_hash,
            "outcome_id": OUTCOME_ID,
            "outcome_version": OUTCOME_VERSION,
            "outcome_contract_hash": out_hash,
            "source_manifest_hash": args.manifest_hash,
            "dataset_group_hash": dataset_group_hash,
            "partition_hash": part_hash,
            "session_date": cand["session_date"],
            "direction": cand["direction"],
            "candidate_fingerprint": cand["candidate_fingerprint"],
            "feature_cutoff": STRAT_PARAMS["decision_cutoff_time"],
            "source_logical_identity": file_record["relative_path"] if file_record else "UNKNOWN",
        }
        record.update(out)
        record["outcome_fingerprint"] = compute_outcome_fingerprint(record)
        outcomes.append(record)
        
    assert outcome_dates.issubset(dev_dates)
    assert outcome_dates.isdisjoint(holdout_dates)
    
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    with open(out_dir / "development_outcome_labels.json", "w") as f:
        json.dump(outcomes, f, indent=2)
        
    with open(out_dir / "development_outcome_reconciliation.json", "w") as f:
        json.dump(recon, f, indent=2)
        
    with open(out_dir / "outcome_contract.json", "w") as f:
        json.dump(OUTCOME_PARAMS, f, indent=2)
        
    with open(out_dir / "outcome_contract.md", "w") as f:
        f.write(f"# Outcome Contract {OUTCOME_ID} v{OUTCOME_VERSION}\n")
        
    print("Labelling complete.")

if __name__ == "__main__":
    main()
