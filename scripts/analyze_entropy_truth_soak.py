import json
import sys
from pathlib import Path
from collections import Counter

def analyze():
    runtime_dir = Path("runtime")
    files = {
        "candidate": runtime_dir / "candidate_decisions.jsonl",
        "ranking": runtime_dir / "ranking_snapshots.jsonl",
        "option": runtime_dir / "option_price_trace.jsonl",
        "feed": runtime_dir / "feed_runtime_latest.json",
        "gate": runtime_dir / "gate_status_latest.json",
    }
    
    total_cycles = 0
    entropy_fields_seen = 0
    total_candidates = 0
    dq_fields_seen = 0
    
    dq_counts = Counter()
    bucket_counts = Counter()
    
    bad_in_top = 0
    bad_execution_ok = 0
    stale_eligible = 0
    invalid_prob_not_uncertain = 0
    missing_entropy = 0
    missing_dq = 0

    if files["candidate"].exists():
        for line in files["candidate"].read_text().splitlines():
            if not line.strip(): continue
            try:
                data = json.loads(line)
            except:
                continue
            
            total_candidates += 1
            
            dq_state = data.get("data_quality_state")
            if dq_state is None:
                missing_dq += 1
            else:
                dq_fields_seen += 1
                dq_counts[dq_state] += 1
            
            entropy = data.get("regime_entropy")
            if entropy is None:
                missing_entropy += 1
            else:
                entropy_fields_seen += 1
                # check prob vector
                probs = data.get("regime_probabilities", {})
                uncertain = data.get("is_uncertain", False)
                if probs:
                    prob_sum = sum(probs.values())
                    if not (0.99 <= prob_sum <= 1.01) and not uncertain:
                        invalid_prob_not_uncertain += 1
                        
            bucket = data.get("display_bucket")
            if bucket:
                bucket_counts[bucket] += 1
                if bucket == "Top Opportunities" and dq_state in ("TRUTH_VIOLATION", "ENTROPY_TOO_HIGH", "STALE_DATA"):
                    bad_in_top += 1
                    
            if data.get("execution_ok", False) and dq_state in ("TRUTH_VIOLATION", "ENTROPY_TOO_HIGH", "STALE_DATA"):
                bad_execution_ok += 1
                
            quote_age = data.get("quote_age_seconds", 0)
            eligible = data.get("score_eligible", False)
            if quote_age > 2 and eligible:
                stale_eligible += 1
                
    if files["feed"].exists():
        try:
            feed_data = json.loads(files["feed"].read_text())
            total_cycles = feed_data.get("cycles", total_cycles)
        except:
            pass
            
    print("=== Entropy Truth Soak Analysis ===")
    print(f"Total Cycles: {total_cycles}")
    print(f"Total Candidates: {total_candidates}")
    print(f"Entropy Field Coverage: {entropy_fields_seen}/{total_candidates}")
    print(f"Data Quality State Coverage: {dq_fields_seen}/{total_candidates}")
    print("\nData Quality Counts:")
    for k, v in dq_counts.items():
        print(f"  {k}: {v}")
    
    print("\nDisplay Bucket Counts:")
    for k, v in bucket_counts.items():
        print(f"  {k}: {v}")
        
    print(f"  Top Opportunities: {bucket_counts.get('Top Opportunities', 0)}")
    print(f"  Watchlist: {bucket_counts.get('Watchlist', 0)}")
    print(f"  Advisory/Debug: {bucket_counts.get('Advisory', 0) + bucket_counts.get('Debug', 0)}")
    print(f"  Suppressed: {bucket_counts.get('Suppressed', 0)}")
    
    print("\nViolations:")
    print(f"  Bad candidates in Top Opportunities: {bad_in_top}")
    print(f"  Bad candidates with execution_ok=true: {bad_execution_ok}")
    print(f"  Stale quote >2s with score_eligible=true: {stale_eligible}")
    print(f"  Invalid probability vector with uncertain=false: {invalid_prob_not_uncertain}")
    print(f"  Missing entropy fields: {missing_entropy}")
    print(f"  Missing data-quality fields: {missing_dq}")
    
    violations = bad_in_top + bad_execution_ok + stale_eligible + invalid_prob_not_uncertain
    if violations > 0:
        print("\nCRITICAL VIOLATIONS FOUND.")
        sys.exit(1)
    else:
        print("\nNo critical violations.")
        sys.exit(0)

if __name__ == "__main__":
    analyze()
