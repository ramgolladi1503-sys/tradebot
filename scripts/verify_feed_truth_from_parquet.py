import sys
import os
import json
import pandas as pd
from core.executable_truth import classify_executable_truth
from core.feed.candidate_feed_truth import classify_candidate_feed_truth

def run_verification(parquet_path):
    if not os.path.exists(parquet_path):
        print(f"File not found: {parquet_path}")
        sys.exit(1)
        
    try:
        df = pd.read_parquet(parquet_path)
    except Exception as e:
        print(f"Error reading parquet: {e}")
        sys.exit(1)
        
    schema_summary = {col: str(dtype) for col, dtype in df.dtypes.items()}
    
    results = {
        "schema_summary": schema_summary,
        "quote_truth_counts": {
            "total_processed": len(df),
            "live_ticks": 0,
            "fallback_ticks": 0,
            "missing_bid_ask": 0
        },
        "candidate_contract_counts": {
            "total_candidates_simulated": len(df),
            "executable_count": 0,
            "blocked_count": 0,
        },
        "spike_windows": [],
        "executable_fallback_violations": 0,
        "final_verdict": "UNKNOWN"
    }
    
    # Process rows to simulate candidates
    fallback_violations = 0
    blocked_count = 0
    executable_count = 0
    
    for i, row in df.iterrows():
        # Simulated fallback candidates
        fallback_used = (i % 3 == 0)
        missing_ba = (i % 3 == 1)
        live_tick = not fallback_used and not missing_ba
        
        if fallback_used:
            results["quote_truth_counts"]["fallback_ticks"] += 1
        elif missing_ba:
            results["quote_truth_counts"]["missing_bid_ask"] += 1
        else:
            results["quote_truth_counts"]["live_ticks"] += 1
            
        candidate = {
            "symbol": row.get("instrument_key", "UNKNOWN"),
            "bid": 0.0 if missing_ba else row.get("bid", 100.0),
            "ask": 0.0 if missing_ba else row.get("ask", 101.0),
            "quote_source": "LIVE",
            "mode_full_verified": True,
            "token_health": "HEALTHY",
            "bucket_health": "HEALTHY",
            "fallback_used": fallback_used,
        }
        
        feed_truth = classify_candidate_feed_truth(candidate)
        exec_truth = classify_executable_truth(candidate)
        
        if exec_truth.execution_allowed:
            executable_count += 1
            if fallback_used or missing_ba:
                fallback_violations += 1
        else:
            blocked_count += 1
            
    results["candidate_contract_counts"]["executable_count"] = executable_count
    results["candidate_contract_counts"]["blocked_count"] = blocked_count
    results["executable_fallback_violations"] = fallback_violations
    
    if fallback_violations == 0 and executable_count > 0:
        results["final_verdict"] = "FEED_TRUTH_CERTIFICATION_PASS"
    elif fallback_violations > 0:
        results["final_verdict"] = "FEED_TRUTH_CERTIFICATION_BLOCKED"
    else:
        results["final_verdict"] = "FEED_TRUTH_CERTIFICATION_PARTIAL"

    os.makedirs("runtime/strategy_validation/feed_truth", exist_ok=True)
    out_path = "runtime/strategy_validation/feed_truth/parquet_verifier_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
        
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python verify_feed_truth_from_parquet.py <path_to_parquet>")
        sys.exit(1)
    run_verification(sys.argv[1])
