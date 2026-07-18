import os
import sys
import json
import subprocess

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    if not os.environ.get("VERIFIER_TESTING"):
        status_out = subprocess.run(["git", "status", "--porcelain"], cwd=repo_root, capture_output=True, text=True).stdout
        if status_out.strip():
            print("ERROR: Worktree is not clean.")
            sys.exit(1)
            
    # Independently verify causal verifier
    if not os.environ.get("VERIFIER_TESTING"):
        env = os.environ.copy()
        env["VERIFIER_TESTING"] = "1" # prevent nested git status checks inside if needed
        causal_check = subprocess.run([sys.executable, os.path.join(repo_root, "scripts", "verify_opening_state_causal_pass.py")], cwd=repo_root, env=env)
        if causal_check.returncode != 0:
            print("ERROR: Causal verifier failed.")
            sys.exit(1)
            
    reviews_dir = os.path.join(repo_root, "docs", "agent_reviews", "opening_state_momentum")
    p_path = os.path.join(reviews_dir, "research_partition.json")
    
    with open(p_path) as f:
        partition = json.load(f)
    holdout_dates = set(partition["holdout"])
    
    with open(os.path.join(reviews_dir, "development_outcome_labels.json")) as f:
        labels = json.load(f)
        
    holdout_count = sum(1 for L in labels if L["session_date"] in holdout_dates)
    if holdout_count > 0:
        print(f"ERROR: {holdout_count} holdout dates found in outcome records.")
        sys.exit(1)
        
    with open(os.path.join(reviews_dir, "development_outcome_reconciliation.json")) as f:
        recon = json.load(f)
        
    if recon["unexplained_count"] != 0:
        print("ERROR: Unexplained count is not 0.")
        sys.exit(1)
        
    with open(os.path.join(reviews_dir, "outcome_oracle_comparison.json")) as f:
        oracle = json.load(f)
        
    with open(os.path.join(reviews_dir, "candidate_decisions.json")) as f:
        decisions = json.load(f)
    accepted_cands = [d for d in decisions if d.get("candidate_accepted")]
    if len(accepted_cands) != len(labels):
        print(f"ERROR: Accepted candidate count ({len(accepted_cands)}) != outcome record count ({len(labels)}).")
        sys.exit(1)
        
    labelled_count = 0
    from datetime import datetime, timezone
    
    for L in labels:
        if L["status"] == "OUTCOME_LABELLED":
            labelled_count += 1
            entry = datetime.fromisoformat(L["entry_timestamp"])
            exit_ts = datetime.fromisoformat(L["exit_timestamp"])
            
            if entry.tzinfo is None or exit_ts.tzinfo is None or "Asia/Kolkata" not in str(entry.tzinfo):
                # datetime.fromisoformat with +05:30 creates a timezone object. We just check if it's aware and +05:30.
                if entry.tzinfo is None or entry.utcoffset().total_seconds() != 19800:
                    print("ERROR: Timestamps are not timezone aware Asia/Kolkata.")
                    sys.exit(1)
                    
            if entry.hour != 14 or entry.minute != 45:
                print("ERROR: Entry time is not 14:45.")
                sys.exit(1)
            if exit_ts.hour != 15 or exit_ts.minute != 15:
                print("ERROR: Exit time is not 15:15.")
                sys.exit(1)
                
            duration = (exit_ts - entry).total_seconds()
            if duration != 1800:
                print("ERROR: Holding duration is not 1800 seconds.")
                sys.exit(1)
                
    if labelled_count == 0:
        print("ERROR: Labelled outcome count is 0.")
        sys.exit(1)
        
    if oracle["mismatch_count"] != 0:
        print("ERROR: Oracle mismatch count is not 0.")
        sys.exit(1)
        
    if len(oracle.get("comparisons", [])) == 0:
        print("ERROR: Oracle comparison count is 0.")
        sys.exit(1)
        
    with open(os.path.join(reviews_dir, "outcome_label_determinism.json")) as f:
        det = json.load(f)
        
    if not det["determinism_verified"]:
        print("ERROR: Determinism failed.")
        sys.exit(1)
        
    # Check profitability artifact does not exist
    if os.path.exists(os.path.join(reviews_dir, "aggregate_profitability.json")):
        print("ERROR: Aggregate profitability artifact exists.")
        sys.exit(1)
        
    # Pytest
    if not os.environ.get("VERIFIER_TESTING"):
        test_check = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests/research/opening_state_momentum/"], cwd=repo_root)
        if test_check.returncode != 0:
            print("ERROR: Tests failed.")
            sys.exit(1)
            
    print("OPENING_STATE_OUTCOME_LABELS_VERIFIED")
    sys.exit(0)

if __name__ == "__main__":
    main()
