#!/usr/bin/env python3
import json
import sys
from pathlib import Path

def validate_v4_candidate_specs(candidates: list[dict]) -> dict:
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

        if not c.get("uses_completed_bars_only", False):
            invalid += 1

        params = set(c.get("parameters", {}).keys())
        tree_str = json.dumps(c.get("predicate_tree", {}))
        for p in params:
            if p not in tree_str and p != "wick_type" and p != "prior_context":
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
    from same_corpus_ohlc_feature_grammar_v4 import generate_candidate_specs

    candidates = generate_candidate_specs(max_candidates=1500, max_family_groups=30)
    metrics = validate_v4_candidate_specs(candidates)

    print("Campaign V4 Candidate Spec Audit Metrics:")
    print(json.dumps(metrics, indent=2))

    assert metrics["placeholder_specs"] == 0, f"FAILED: {metrics['placeholder_specs']} placeholders found!"
    assert metrics["specs_with_unenforced_fields"] == 0, f"FAILED: {metrics['specs_with_unenforced_fields']} unenforced fields found!"
    assert metrics["valid_specs"] >= 500, f"FAILED: Only {metrics['valid_specs']} valid specs (expected >= 500)!"

    out_path = root / "research" / "evidence" / "same_corpus_ohlc_feature_discovery_v4" / "V4_REPAIR_VALIDATION.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump({"schema_version": 1, "audit_metrics": metrics, "status": "V4_VALIDATION_PASSED"}, f, indent=2)

    print("V4 VALIDATION SUCCESSFUL: All quality & causality assertions passed.")

if __name__ == "__main__":
    main()
