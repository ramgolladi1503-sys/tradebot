#!/usr/bin/env python3
import json
import sys
from pathlib import Path

def validate_candidate_specs(candidates: list[dict]) -> dict:
    total = len(candidates)
    valid = 0
    invalid = 0
    blocked = 0
    placeholders = 0
    unenforced_fields = 0
    with_window_policy = 0
    with_predicate_tree = 0
    seen_ids = set()
    duplicates = 0

    for c in candidates:
        cid = c.get("candidate_id", "")
        if cid in seen_ids:
            duplicates += 1
        seen_ids.add(cid)

        if "MASSIVE_GRAMMAR_CATEGORY" in c.get("family_group", "") or "Grammar generated" in c.get("mechanism_label", ""):
            placeholders += 1

        if not c.get("predicate_tree"):
            invalid += 1
            continue

        with_predicate_tree += 1

        if c.get("window_policy"):
            with_window_policy += 1

        params = set(c.get("parameters", {}).keys())
        tree_str = json.dumps(c.get("predicate_tree", {}))
        for p in params:
            if p not in tree_str and p != "first_state" and p != "second_state" and p != "state1" and p != "state2" and p != "states":
                unenforced_fields += 1

        if "BLOCKED_MISSING_REQUIRED_INPUT" in tree_str:
            blocked += 1
        else:
            valid += 1

    return {
        "total_specs_generated": total,
        "valid_specs": valid,
        "invalid_specs": invalid,
        "blocked_specs": blocked,
        "placeholder_specs": placeholders,
        "duplicate_specs": duplicates,
        "specs_with_unenforced_fields": unenforced_fields,
        "specs_with_window_policy": with_window_policy,
        "specs_with_predicate_tree": with_predicate_tree
    }

def main():
    root = Path(__file__).resolve().parent.parent.parent.parent
    sys.path.insert(0, str(root / "scripts" / "research" / "hypothesis_factory"))
    from same_corpus_hypothesis_grammar_v3 import generate_candidate_specs
    from same_corpus_time_window_v3 import classify_session_position_window_v3

    candidates = generate_candidate_specs(max_candidates=1000, max_family_groups=25)
    metrics = validate_candidate_specs(candidates)

    print("Candidate Spec Quality Audit Metrics:")
    print(json.dumps(metrics, indent=2))

    assert metrics["placeholder_specs"] == 0, f"FAILED: {metrics['placeholder_specs']} placeholders found!"
    assert metrics["specs_with_unenforced_fields"] == 0, f"FAILED: {metrics['specs_with_unenforced_fields']} unenforced fields found!"
    assert metrics["valid_specs"] >= 500, f"FAILED: Only {metrics['valid_specs']} valid specs (expected >= 500)!"

    # Validate timestamp window classifier on development episodes
    episodes_path = root / "research" / "evidence" / "behavior_discovery_engine_v2" / "NIFTY_behavior_episodes_v1.jsonl"
    with episodes_path.open() as f:
        episodes = [json.loads(line) for line in f if line.strip()]

    parsed_count = 0
    classified_count = 0
    parse_failed_count = 0
    unclassifiable_count = 0

    for ep in episodes:
        ts = ep.get("end_timestamp", "")
        win, err = classify_session_position_window_v3(ts)
        if err == "TIMESTAMP_PARSE_FAILED":
            parse_failed_count += 1
        elif err == "UNCLASSIFIABLE_WINDOW":
            unclassifiable_count += 1
        else:
            classified_count += 1
        parsed_count += 1

    success_rate = classified_count / parsed_count if parsed_count > 0 else 0.0
    print(f"Window Classifier Metrics: Evaluated={parsed_count}, Classified={classified_count}, Success Rate={success_rate:.2%}")
    print(f"TIMESTAMP_PARSE_FAILED={parse_failed_count}, UNCLASSIFIABLE_WINDOW={unclassifiable_count}")

    assert success_rate > 0.80, f"FAILED: Window classification success rate {success_rate:.2%} is <= 80%!"

    out_path = root / "research" / "evidence" / "same_corpus_massive_hypothesis_discovery_v3" / "V3_REPAIR_VALIDATION_WINDOW_FIXED.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump({
            "schema_version": 1,
            "audit_metrics": metrics,
            "window_classifier_metrics": {
                "total_episodes": parsed_count,
                "classified_count": classified_count,
                "timestamp_parse_failed_count": parse_failed_count,
                "unclassifiable_window_count": unclassifiable_count,
                "window_classification_success_rate": success_rate
            },
            "status": "REPAIR_VALIDATION_WINDOW_FIXED_PASSED"
        }, f, indent=2)

    print("VALIDATION SUCCESSFUL: All quality gates passed cleanly.")

if __name__ == "__main__":
    main()
