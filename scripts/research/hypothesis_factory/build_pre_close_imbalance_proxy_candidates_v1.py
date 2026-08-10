#!/usr/bin/env python3
import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

TARGET_FAMILY = "PRE_CLOSE_IMBALANCE_PROXY_FAMILY_V1"

def sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def get_preclose_bucket(timestamp_str: str) -> str | None:
    time_part = timestamp_str.split("T")[1]
    h, m, s = map(int, time_part.split(":"))
    minutes_since_midnight = h * 60 + m
    market_open = 3 * 60 + 45
    minutes_since_open = minutes_since_midnight - market_open
    
    if 375 - 60 <= minutes_since_open < 375 - 30:
        return "PRE_CLOSE_60"
    if 375 - 30 <= minutes_since_open <= 375:
        return "PRE_CLOSE_30"
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
            
    preclose_state_counts = defaultdict(int)
    for ep in episodes:
        pc_bucket = get_preclose_bucket(ep["end_timestamp"])
        if not pc_bucket: continue
        for st in ep.get("state_sequence", []):
            preclose_state_counts[(pc_bucket, st)] += 1
            
    high_info_states = {
        "UPSIDE_ESCAPE",
        "DOWNSIDE_ESCAPE",
        "FAILED_UPSIDE_ESCAPE",
        "FAILED_DOWNSIDE_ESCAPE",
        "EXPANSION"
    }

    candidates = []
    rejections = []

    for (pc_bucket, state), count in preclose_state_counts.items():
        cand_id = f"{TARGET_FAMILY}_{pc_bucket}_{state}_IMBALANCE_PROXY"
        if state in high_info_states and count >= 10:
            cand = {
                "candidate_id": cand_id,
                "search_family_id": TARGET_FAMILY,
                "preclose_bucket": pc_bucket,
                "required_state": state,
                "proxy_type": "IMBALANCE_PROXY_ONLY",
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
                "preclose_bucket": pc_bucket,
                "required_state": state,
                "frequency": count,
                "reason": "GENERIC_OR_LOW_FREQUENCY_IMBALANCE_REJECTION"
            })
            
    freeze_path = bde2_dir / "NIFTY_pre_close_imbalance_proxy_candidates_v1.jsonl"
    summary_path = bde2_dir / "NIFTY_pre_close_imbalance_proxy_candidates_v1_summary.json"
    rejections_path = bde2_dir / "NIFTY_pre_close_imbalance_proxy_candidates_v1_rejections.jsonl"
    
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
        
    print(f"Frozen {len(candidates)} Pre-Close Imbalance Proxy candidates.")

if __name__ == "__main__":
    main()
