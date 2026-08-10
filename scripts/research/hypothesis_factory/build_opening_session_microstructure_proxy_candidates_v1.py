#!/usr/bin/env python3
import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

TARGET_FAMILY = "OPENING_SESSION_MICROSTRUCTURE_PROXY_FAMILY_V1"

def sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def get_opening_bucket(timestamp_str: str) -> str | None:
    time_part = timestamp_str.split("T")[1]
    h, m, s = map(int, time_part.split(":"))
    minutes_since_midnight = h * 60 + m
    market_open = 3 * 60 + 45
    minutes_since_open = minutes_since_midnight - market_open
    
    if 0 <= minutes_since_open <= 30:
        return "OPENING_0_30"
    if 30 < minutes_since_open <= 60:
        return "OPENING_30_60"
    return None

def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    
    root = Path(__file__).resolve().parent.parent.parent.parent
    bde2_dir = root / "research" / "evidence" / "behavior_discovery_engine_v2"
    episodes_path = bde2_dir / "NIFTY_behavior_episodes_v1.jsonl"
    
    if not episodes_path.exists():
        print(f"BLOCKED: Missing {episodes_path}")
        sys.exit(1)
        
    episodes = []
    with episodes_path.open() as f:
        for line in f:
            if not line.strip(): continue
            episodes.append(json.loads(line))
            
    opening_state_counts = defaultdict(int)
    for ep in episodes:
        op_bucket = get_opening_bucket(ep["end_timestamp"])
        if not op_bucket: continue
        for st in ep.get("state_sequence", []):
            opening_state_counts[(op_bucket, st)] += 1
            
    # Causal opening microstructure proxy candidates
    # Restrict candidate pool strictly to high-information opening states
    opening_high_info_states = {
        "UPSIDE_ESCAPE",
        "DOWNSIDE_ESCAPE",
        "FAILED_UPSIDE_ESCAPE",
        "FAILED_DOWNSIDE_ESCAPE",
        "EXPANSION"
    }

    candidates = []
    rejections = []

    for (op_bucket, state), count in opening_state_counts.items():
        cand_id = f"{TARGET_FAMILY}_{op_bucket}_{state}"
        if state in opening_high_info_states and count >= 15:
            cand = {
                "candidate_id": cand_id,
                "search_family_id": TARGET_FAMILY,
                "opening_bucket": op_bucket,
                "required_state": state,
                "pre_outcome_frequency": count,
                "edge_claimed": False,
                "forward_outcomes_used": False,
                "locked_outcomes_accessed": False
            }
            cand["hash"] = sha256_str(json.dumps(cand, sort_keys=True))
            candidates.append(cand)
        else:
            rejections.append({
                "candidate_id": cand_id,
                "opening_bucket": op_bucket,
                "required_state": state,
                "frequency": count,
                "reason": "GENERIC_OR_LOW_FREQUENCY_OPENING_REJECTION"
            })
            
    freeze_path = bde2_dir / "NIFTY_opening_session_microstructure_proxy_candidates_v1.jsonl"
    summary_path = bde2_dir / "NIFTY_opening_session_microstructure_proxy_candidates_v1_summary.json"
    rejections_path = bde2_dir / "NIFTY_opening_session_microstructure_proxy_candidates_v1_rejections.jsonl"
    
    with freeze_path.open("w") as f:
        for c in candidates:
            f.write(json.dumps(c) + "\n")
            
    with rejections_path.open("w") as f:
        for r in rejections:
            f.write(json.dumps(r) + "\n")

    with summary_path.open("w") as f:
        json.dump({
            "search_family_id": TARGET_FAMILY,
            "total_candidates": len(candidates),
            "total_rejections": len(rejections),
            "edge_claimed": False,
            "forward_outcomes_used": False,
            "locked_outcomes_accessed": False
        }, f, indent=2)
        
    print(f"Frozen {len(candidates)} Opening Session Microstructure candidates.")

if __name__ == "__main__":
    main()
