#!/usr/bin/env python3
import json
from pathlib import Path
from typing import Any

def apply_v4_pre_outcome_narrowing(survivors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filtered = []
    for s in survivors:
        cid = s.get("candidate_id", "")
        # Require minimum 30 distinct sessions for robust sample adequacy
        if s.get("distinct_sessions", 0) < 30:
            continue
        filtered.append(s)

    # Sort by mechanism type & distinct session coverage (Pre-outcome criteria only)
    filtered.sort(key=lambda x: (x.get("candidate_type") == "BAR_MORPHOLOGY_PREDICATE", x.get("distinct_sessions", 0)), reverse=True)

    # Cap at max 3 per multiple testing rules
    return filtered[:3]

def main():
    root = Path(__file__).resolve().parent.parent.parent.parent
    v4_dir = root / "research" / "evidence" / "same_corpus_ohlc_feature_discovery_v4"
    survivors_path = v4_dir / "development_survivors.jsonl"

    with survivors_path.open() as f:
        survivors = [json.loads(line) for line in f if line.strip()]

    print(f"Total V4 Raw Development Survivors: {len(survivors)}")
    narrowed = apply_v4_pre_outcome_narrowing(survivors)
    print(f"Narrowed V4 Pre-Outcome Survivors: {len(narrowed)}")
    for n in narrowed:
        print(f"  - {n['candidate_id']} (Type: {n['candidate_type']}, Sessions: {n['distinct_sessions']})")

    with (v4_dir / "pre_outcome_narrowing.json").open("w") as f:
        json.dump({
            "schema_version": 1,
            "raw_survivors_count": len(survivors),
            "narrowed_survivors_count": len(narrowed),
            "narrowing_rules": ["MIN_DISTINCT_SESSIONS_30", "PRE_OUTCOME_FEATURE_SPECIFICITY"],
            "frozen_candidates": narrowed
        }, f, indent=2)

if __name__ == "__main__":
    main()
