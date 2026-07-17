import json
from pathlib import Path

def main():
    repo_root = Path(__file__).parent.parent
    reviews_dir = repo_root / "docs" / "agent_reviews" / "opening_state_momentum"
    
    universe_path = reviews_dir / "session_universe_audit.json"
    partition_path = reviews_dir / "research_partition.json"
    decisions_path = reviews_dir / "candidate_decisions.json"
    
    with open(universe_path) as f:
        universe = json.load(f)
        
    with open(partition_path) as f:
        partition = json.load(f)
        
    with open(decisions_path) as f:
        decisions = json.load(f)
        
    dev_dates = set(partition["development"])
    holdout_dates = set(partition["holdout"])
    
    prev_decision_count = len(decisions)
    prev_holdout_evaluated = [d["session_date"] for d in decisions if d["session_date"] in holdout_dates]
    
    # Mark old decisions file as superseded
    superseded_path = reviews_dir / "SUPERSEDED_HOLDOUT_CONTAMINATED_CANDIDATE_REPLAY.json"
    with open(superseded_path, "w") as f:
        json.dump(decisions, f, indent=2)
        
    audit = {
        "eligible_count": len([s for s in universe["sessions"] if s["is_eligible"]]),
        "development_count": len(dev_dates),
        "holdout_count": len(holdout_dates),
        "previous_decision_count": prev_decision_count,
        "previous_holdout_dates_evaluated": prev_holdout_evaluated,
        "repaired_decision_count": 0, # Will be filled later
        "repaired_holdout_dates_evaluated": [],
        "final_holdout_violation_count": 0
    }
    
    audit_path = reviews_dir / "holdout_candidate_access_audit.json"
    with open(audit_path, "w") as f:
        json.dump(audit, f, indent=2)
        
    print(f"Created {audit_path}")

if __name__ == "__main__":
    main()
