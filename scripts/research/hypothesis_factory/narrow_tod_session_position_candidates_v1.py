#!/usr/bin/env python3
import json
import sys
from pathlib import Path

HIGH_INFO_STATES = {
    "UPSIDE_ESCAPE",
    "DOWNSIDE_ESCAPE",
    "FAILED_UPSIDE_ESCAPE",
    "FAILED_DOWNSIDE_ESCAPE",
    "EXPANSION"
}

GENERIC_STATES = {
    "COMPRESSION",
    "RANGE_BALANCE",
    "LOWER_REJECTION",
    "UPPER_REJECTION",
    "DIRECTIONAL_UP",
    "DIRECTIONAL_DOWN",
    "DIRECTIONAL_ACCELERATION",
    "DIRECTIONAL_DECELERATION"
}

def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows

def write_jsonl(path: Path, rows: list[dict]):
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

def main():
    root = Path(__file__).resolve().parent.parent.parent.parent
    bde2_dir = root / "research" / "evidence" / "behavior_discovery_engine_v2"
    
    input_path = bde2_dir / "NIFTY_tod_session_position_candidates_v1.jsonl"
    if not input_path.exists():
        print(f"BLOCKED: Missing {input_path}")
        sys.exit(1)
        
    candidates = load_jsonl(input_path)
    narrowed = []
    rejections = []
    
    for cand in candidates:
        state = cand.get("required_state", "")
        if state in HIGH_INFO_STATES:
            narrowed.append(cand)
        else:
            rejections.append({
                "candidate_id": cand.get("candidate_id"),
                "required_state": state,
                "reason": "PRE_OUTCOME_GENERIC_STATE_REJECTION"
            })
            
    out_narrowed_path = bde2_dir / "NIFTY_tod_session_position_candidates_v1_narrowed.jsonl"
    out_summary_path = bde2_dir / "NIFTY_tod_session_position_candidates_v1_narrowed_summary.json"
    out_rejections_path = bde2_dir / "NIFTY_tod_session_position_candidates_v1_narrowed_rejections.jsonl"
    
    write_jsonl(out_narrowed_path, narrowed)
    write_jsonl(out_rejections_path, rejections)
    
    with out_summary_path.open("w") as f:
        json.dump({
            "total_narrowed_candidates": len(narrowed),
            "total_rejected_candidates": len(rejections),
            "edge_claimed": False,
            "forward_outcomes_used": False,
            "locked_outcomes_accessed": False
        }, f, indent=2)
        
    print(f"Narrowed to {len(narrowed)} candidates. Rejected {len(rejections)} generic candidates.")

if __name__ == "__main__":
    main()
