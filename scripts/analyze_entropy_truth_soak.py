import json
import sys
from pathlib import Path
from collections import Counter

def get_first(data, keys, default=None):
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return default

def parse_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    if isinstance(value, int):
        return value != 0
    return False

def normalize_display_bucket(value):
    if not isinstance(value, str):
        return "UNKNOWN"
    val = value.strip().upper()
    if val in ("TOP_OPPORTUNITY", "TOP OPPORTUNITIES", "TOP_OPPORTUNITIES"):
        return "TOP_OPPORTUNITY"
    return val

def normalize_data_quality_state(value):
    if not isinstance(value, str):
        return "UNKNOWN"
    return value.strip().upper()

def is_bad_feed_state(data):
    bad_tokens = {
        "fallback", "recovered_fallback", "fallback_data", "fallback_quote_data",
        "rest_fallback", "stale_feed", "stale_option_ltp", "synthetic",
        "missing_depth", "missing_spread", "quote_age_unknown", "planning_only",
        "advisory_only", "untrusted_quote_source"
    }
    
    dq_state = normalize_data_quality_state(data.get("data_quality_state", ""))
    
    # check tokens in multiple fields
    fields_to_check = [
        data.get("data_quality_state", ""),
        data.get("quote_truth_source", ""),
        data.get("source_flags", ""),
        data.get("suppression_reason", ""),
        data.get("execution_block_reason", ""),
        data.get("reasons", ""),
        data.get("tags", ""),
        data.get("display_bucket", ""),
        data.get("candidate_status", "")
    ]
    
    for field in fields_to_check:
        if isinstance(field, str):
            field_tokens = set(field.lower().split(","))
            for t in field_tokens:
                t = t.strip()
                if t in bad_tokens or any(bt in t for bt in bad_tokens):
                    return True
        elif isinstance(field, list):
            for t in field:
                if isinstance(t, str):
                    t = t.lower().strip()
                    if t in bad_tokens or any(bt in t for bt in bad_tokens):
                        return True
                        
    return False

def is_top_opportunity(data):
    bucket = get_first(data, ["display_bucket", "bucket", "ranking_bucket", "ui_bucket"])
    if not bucket:
        return False
    return normalize_display_bucket(bucket) == "TOP_OPPORTUNITY"

def analyze_candidate(data):
    violations = []
    
    # Check fields
    raw_entropy = get_first(data, ["market_entropy_raw", "regime_entropy", "entropy", "raw_entropy"])
    norm_entropy = get_first(data, ["market_entropy_normalized", "regime_entropy_normalized", "normalized_entropy"])
    is_uncertain = get_first(data, ["market_regime_uncertain", "is_uncertain", "entropy_too_high"], False)
    is_uncertain = parse_bool(is_uncertain)
    
    quote_age = get_first(data, ["quote_age_sec", "quote_age_seconds", "option_ltp_age_sec", "option_ltp_age_seconds", "tick_age_sec"], 0)
    try:
        quote_age = float(quote_age)
    except:
        quote_age = 0.0
        
    score_eligible = parse_bool(data.get("score_eligible", False))
    execution_ok = parse_bool(data.get("execution_ok", False))
    dq_state = normalize_data_quality_state(data.get("data_quality_state", ""))
    
    is_bad = is_bad_feed_state(data)
    is_top = is_top_opportunity(data)
    
    is_active = score_eligible or execution_ok or is_top
    
    # Check rules
    if is_bad and is_top:
        violations.append("bad_feed_in_top_opportunities")
    
    if is_bad and execution_ok:
        violations.append("bad_feed_execution_ok")
        
    if quote_age > 2.0 and score_eligible:
        violations.append("stale_quote_eligible")
        
    # Check probability vector
    probs = get_first(data, ["regime_probabilities", "probabilities"])
    if probs and isinstance(probs, dict):
        try:
            prob_sum = sum(float(v) for v in probs.values())
            if not (0.99 <= prob_sum <= 1.01) and not is_uncertain:
                violations.append("invalid_prob_uncertain_false")
        except:
            pass
            
    if is_active:
        if raw_entropy is None and norm_entropy is None:
            violations.append("missing_both_entropy")
        if not dq_state and not is_bad: # If it's not known bad and has no state
            violations.append("missing_dq_state_and_inference")
            
    return {
        "is_bad": is_bad,
        "is_top": is_top,
        "is_active": is_active,
        "raw_entropy": raw_entropy,
        "norm_entropy": norm_entropy,
        "is_uncertain": is_uncertain,
        "execution_ok": execution_ok,
        "quote_age": quote_age,
        "score_eligible": score_eligible,
        "dq_state": dq_state,
        "violations": violations
    }

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
    total_candidates = 0
    
    dq_counts = Counter()
    bucket_counts = Counter()
    
    all_violations = []

    if files["candidate"].exists():
        for line in files["candidate"].read_text().splitlines():
            if not line.strip(): continue
            try:
                data = json.loads(line)
            except:
                continue
            
            total_candidates += 1
            res = analyze_candidate(data)
            
            if res["dq_state"]:
                dq_counts[res["dq_state"]] += 1
            else:
                if res["is_bad"]:
                    dq_counts["INFERRED_BAD"] += 1
                else:
                    dq_counts["UNKNOWN"] += 1
                    
            bucket = normalize_display_bucket(get_first(data, ["display_bucket", "bucket", "ranking_bucket", "ui_bucket"]))
            if bucket:
                bucket_counts[bucket] += 1
                
            for v in res["violations"]:
                all_violations.append(v)
                
    if files["feed"].exists():
        try:
            feed_data = json.loads(files["feed"].read_text())
            total_cycles = feed_data.get("cycles", total_cycles)
        except:
            pass
            
    print("=== Entropy Truth Soak Analysis ===")
    print(f"Total Cycles: {total_cycles}")
    print(f"Total Candidates: {total_candidates}")
    
    print("\nData Quality Counts:")
    for k, v in dq_counts.items():
        print(f"  {k}: {v}")
    
    print("\nDisplay Bucket Counts:")
    for k, v in bucket_counts.items():
        print(f"  {k}: {v}")
        
    print("\nViolations:")
    violation_counts = Counter(all_violations)
    if not violation_counts:
        print("  None")
    for k, v in violation_counts.items():
        print(f"  {k}: {v}")
    
    if total_candidates == 0:
        print("\nNo candidates processed. (Market likely closed or OFFHOURS).")
        print("Final Verdict: OFFHOURS_READY_ONLY / INCONCLUSIVE_FEED_NOT_STABLE")
        sys.exit(0)
        
    if all_violations:
        print("\nCRITICAL VIOLATIONS FOUND.")
        sys.exit(1)
    else:
        print("\nNo critical violations.")
        sys.exit(0)

if __name__ == "__main__":
    analyze()
