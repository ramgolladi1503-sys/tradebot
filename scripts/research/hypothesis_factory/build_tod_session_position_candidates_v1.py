#!/usr/bin/env python3
import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

TARGET_FAMILY = "TIME_OF_DAY_SESSION_POSITION_FAMILY_V1"

def sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def get_tod_bucket(timestamp_str: str) -> str:
    time_part = timestamp_str.split("T")[1]
    h, m, s = map(int, time_part.split(":"))
    minutes_since_midnight = h * 60 + m
    market_open = 3 * 60 + 45
    minutes_since_open = minutes_since_midnight - market_open
    
    if minutes_since_open < 0 or minutes_since_open > 375:
        return "OUT_OF_SESSION"
    
    if minutes_since_open <= 30:
        return "OPEN_0_30"
    if minutes_since_open <= 60:
        return "OPEN_30_60"
    if minutes_since_open >= 375 - 30:
        return "PRE_CLOSE_30"
    if minutes_since_open >= 375 - 60:
        return "PRE_CLOSE_60"
    
    return "MID_SESSION"

def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    
    root = Path(__file__).resolve().parent.parent.parent.parent
    
    episodes_path = root / "research" / "evidence" / "behavior_discovery_engine_v2" / "NIFTY_behavior_episodes_v1.jsonl"
    if not episodes_path.exists():
        print(f"BLOCKED: Missing {episodes_path}")
        sys.exit(1)
        
    episodes = []
    with episodes_path.open() as f:
        for line in f:
            if not line.strip(): continue
            episodes.append(json.loads(line))
            
    tod_state_counts = defaultdict(int)
    for ep in episodes:
        tod = get_tod_bucket(ep["end_timestamp"])
        if tod == "OUT_OF_SESSION": continue
        for st in ep.get("state_sequence", []):
            tod_state_counts[(tod, st)] += 1
            
    candidates = []
    for (tod, state), count in tod_state_counts.items():
        # Keep it broad pre-outcome, the development outcome screen will filter
        if count >= 20: 
            cand = {
                "candidate_id": f"{TARGET_FAMILY}_{tod}_{state}",
                "search_family_id": TARGET_FAMILY,
                "tod_bucket": tod,
                "required_state": state,
                "edge_claimed": False,
                "forward_outcomes_used": False,
                "locked_outcomes_accessed": False,
                "pre_outcome_frequency": count
            }
            cand["hash"] = sha256_str(json.dumps(cand, sort_keys=True))
            candidates.append(cand)
            
    freeze_path = root / "research" / "evidence" / "behavior_discovery_engine_v2" / "NIFTY_tod_session_position_candidates_v1.jsonl"
    summary_path = root / "research" / "evidence" / "behavior_discovery_engine_v2" / "NIFTY_tod_session_position_candidates_v1_summary.json"
    rejections_path = root / "research" / "evidence" / "behavior_discovery_engine_v2" / "NIFTY_tod_session_position_candidates_v1_rejections.jsonl"
    
    with freeze_path.open("w") as f:
        for c in candidates:
            f.write(json.dumps(c) + "\n")
            
    with summary_path.open("w") as f:
        json.dump({
            "total_candidates": len(candidates),
            "edge_claimed": False,
            "forward_outcomes_used": False,
            "locked_outcomes_accessed": False
        }, f, indent=2)
        
    # No rejections during pre-outcome phase built this way, write empty or specific rejections if needed
    with rejections_path.open("w") as f:
        pass
            
    print(f"Frozen {len(candidates)} TOD candidates.")

if __name__ == "__main__":
    main()
