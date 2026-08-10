#!/usr/bin/env python3
import json
from pathlib import Path
from typing import Any

def apply_pre_outcome_narrowing(survivors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Rule 1: Mechanism uniqueness - exclude generic RANGE_BALANCE / REJECTION fallbacks if specific escape motifs exist
    # Rule 2: Causal clarity - prefer explicit sequence transitions over raw window-state correlations
    # Rule 3: Parameter simplicity & session dispersion >= 25
    # Rule 4: Not duplicate of failed TOD pre-close 30 upside escape family

    # Filter out direct duplicates of failed TOD candidate
    filtered = []
    for s in survivors:
        cid = s.get("candidate_id", "")
        # Exclude TOD duplicate: TIME_OF_DAY_SESSION_POSITION_FAMILY_V1_PRE_CLOSE_30_UPSIDE_ESCAPE
        if "PRE_CLOSE_30_UPSIDE_ESCAPE" in cid and "SEQUENCE" not in cid:
            continue
        if s.get("distinct_sessions", 0) < 25:
            continue
        filtered.append(s)

    # Sort by mechanism uniqueness and distinct session coverage (pre-outcome criteria ONLY, no return sorting)
    filtered.sort(key=lambda x: (x.get("candidate_type") == "SEQUENCE_TRANSITION_PREDICATE", x.get("distinct_sessions", 0)), reverse=True)

    # Cap at maximum 3 pre-locked survivors per multiple testing / selection pressure rules
    return filtered[:3]

def main():
    root = Path(__file__).resolve().parent.parent.parent.parent
    v3_dir = root / "research" / "evidence" / "same_corpus_massive_hypothesis_discovery_v3"
    survivors_path = v3_dir / "development_survivors.jsonl"

    if not survivors_path.exists():
        print("No development survivors JSONL found!")
        return

    with survivors_path.open() as f:
        survivors = [json.loads(line) for line in f if line.strip()]

    print(f"Total Raw Development Survivors: {len(survivors)}")
    narrowed = apply_pre_outcome_narrowing(survivors)
    print(f"Narrowed Pre-Outcome Survivors: {len(narrowed)}")
    for n in narrowed:
        print(f"  - {n['candidate_id']} (Type: {n['candidate_type']}, Sessions: {n['distinct_sessions']})")

    out_payload = {
        "schema_version": 1,
        "raw_survivors_count": len(survivors),
        "narrowed_survivors_count": len(narrowed),
        "narrowing_rules_applied": [
            "EXCLUDE_PARKED_TOD_PRECLOSE_30_UPSIDE_ESCAPE_DUPLICATES",
            "PREFER_ORDERED_TRANSITION_MOTIFS",
            "MIN_DISTINCT_SESSIONS_25",
            "PRE_OUTCOME_ONLY_NO_RETURN_RANKING"
        ],
        "frozen_candidates": narrowed
    }
    with (v3_dir / "pre_outcome_narrowing.json").open("w") as f:
        json.dump(out_payload, f, indent=2)

if __name__ == "__main__":
    main()
