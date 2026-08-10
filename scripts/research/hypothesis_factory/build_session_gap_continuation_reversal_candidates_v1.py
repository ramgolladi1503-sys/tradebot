#!/usr/bin/env python3
import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

TARGET_FAMILY = "SESSION_GAP_CONTINUATION_REVERSAL_FAMILY_V1"

def sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

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
            
    gap_state_counts = defaultdict(int)
    for ep in episodes:
        for st in ep.get("state_sequence", []):
            if st in ("UPSIDE_ESCAPE", "DOWNSIDE_ESCAPE", "FAILED_UPSIDE_ESCAPE", "FAILED_DOWNSIDE_ESCAPE"):
                gap_state_counts[st] += 1
            
    candidates = []
    rejections = []

    for state, count in gap_state_counts.items():
        cand_id = f"{TARGET_FAMILY}_{state}_GAP_PROXIMAL"
        if count >= 10:
            cand = {
                "candidate_id": cand_id,
                "search_family_id": TARGET_FAMILY,
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
                "required_state": state,
                "frequency": count,
                "reason": "LOW_FREQUENCY_GAP_PROXIMAL_REJECTION"
            })
            
    freeze_path = bde2_dir / "NIFTY_session_gap_continuation_reversal_candidates_v1.jsonl"
    summary_path = bde2_dir / "NIFTY_session_gap_continuation_reversal_candidates_v1_summary.json"
    rejections_path = bde2_dir / "NIFTY_session_gap_continuation_reversal_candidates_v1_rejections.jsonl"
    
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
        
    print(f"Frozen {len(candidates)} Session Gap Continuation Reversal candidates.")

if __name__ == "__main__":
    main()
