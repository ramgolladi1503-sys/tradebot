import os
import sys
import json
import subprocess
from pathlib import Path

def run_cmd(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)

def verify_outcomes():
    repo_root = Path(__file__).parent.parent
    reviews_dir = repo_root / "docs" / "agent_reviews" / "opening_state_momentum"
    
    report = {
        "overall_pass": False,
        "failures": []
    }
    def fail(msg):
        report["failures"].append(msg)
        
    def check_true(cond, check_name, fail_msg):
        if not cond:
            fail(f"{check_name}: {fail_msg}")
            
    # Check tree clean before
    status_res = run_cmd(["git", "status", "--porcelain"], cwd=repo_root)
    is_clean = len(status_res.stdout.strip()) == 0
    check_true(is_clean, "Git", "Worktree is not clean at verifier start")
            
    # Check causal pass
    res = run_cmd(["python", str(repo_root / "scripts" / "verify_opening_state_causal_pass.py")], cwd=repo_root)
    check_true(res.returncode == 0, "CausalVerifier", "Causal verifier does not exit 0")
    
    # Contract Hash Check
    sys.path.insert(0, str(repo_root))
    from research.opening_state_momentum.outcome_contract import get_outcome_contract_hash
    expected_hash = get_outcome_contract_hash()
    
    try:
        with open(reviews_dir / "development_outcome_labels.json") as f:
            outcomes = json.load(f)
        for o in outcomes:
            check_true(o.get("outcome_contract_hash") == expected_hash, "ContractHash", "Outcome contract hash mismatch")
            
        with open(reviews_dir / "research_partition.json") as f:
            part = json.load(f)
        dev = set(part.get("development", []))
        holdout = set(part.get("holdout", []))
        
        outcome_dates = set(o.get("session_date") for o in outcomes if o.get("status") == "OUTCOME_LABELLED")
        check_true(outcome_dates.issubset(dev), "Dates", "Outcomes contain non-development dates")
        check_true(outcome_dates.isdisjoint(holdout), "Dates", "Holdout dates in labelled outcomes")
        
        with open(reviews_dir / "development_outcome_reconciliation.json") as f:
            recon = json.load(f)
            
        check_true(recon.get("holdout_outcome_count") == 0, "HoldoutCount", "Holdout outcome count is not 0")
        check_true(recon.get("unexplained_count") == 0, "Recon", "Unexplained count is not 0")
        
        with open(reviews_dir / "candidate_decisions.json") as f:
            decs = json.load(f)
        rej_dates = set(d["session_date"] for d in decs if d.get("status") != "ACCEPTED")
        labelled_dates = set(o["session_date"] for o in outcomes if o.get("status") == "OUTCOME_LABELLED")
        check_true(labelled_dates.isdisjoint(rej_dates), "Rejected", "Rejected decisions have outcomes")
        
        acc = recon.get("accepted_development_candidates")
        labs = recon.get("labelled_outcomes")
        failures = sum(v for k,v in recon.items() if k.startswith("count_"))
        check_true(acc == labs + failures, "ReconMath", f"Accepted ({acc}) != Labelled ({labs}) + Failures ({failures})")
        
        for o in outcomes:
            if o.get("status") == "OUTCOME_LABELLED":
                check_true("14:45:00" in o.get("entry_timestamp"), "Timestamp", "Entry not 14:45")
                check_true("15:15:00" in o.get("exit_timestamp"), "Timestamp", "Exit not 15:15")
                check_true(o.get("holding_minutes") == 30, "Holding", "Holding not 30")
                
        with open(reviews_dir / "outcome_oracle_comparison.json") as f:
            oracle = json.load(f)
        check_true(oracle.get("mismatches") == 0, "Oracle", "Oracle mismatches not 0")
        
        with open(reviews_dir / "outcome_label_determinism.json") as f:
            det = json.load(f)
        check_true(det.get("match"), "Determinism", "Two-directory determinism failed")
        
        prof_files = ["aggregate_profitability", "pnl", "expectancy"]
        for pf in prof_files:
            for f in reviews_dir.glob("*.json"):
                check_true(pf not in f.name.lower(), "Profitability", f"Profitability artifact found: {f.name}")
                
    except Exception as e:
        fail(f"Exception: {e}")
        
    report["overall_pass"] = len(report["failures"]) == 0
    return report

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=str)
    args = parser.parse_args()
    
    report = verify_outcomes()
    
    if args.report:
        with open(args.report, "w") as f:
            json.dump(report, f, indent=2)
            
    print(f"OUTCOME VERIFIER EXIT CODE: {0 if report['overall_pass'] else 1}")
    if report["overall_pass"]:
        print("OPENING_STATE_OUTCOME_LABELS_VERIFIED")
        sys.exit(0)
    else:
        print("OPENING_STATE_OUTCOME_LABELS_REJECTED")
        print(f"FAILURES: {report['failures']}")
        sys.exit(1)
        
if __name__ == "__main__":
    main()
