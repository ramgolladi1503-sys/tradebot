#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

from same_corpus_hypothesis_grammar_v3 import generate_candidate_specs
from same_corpus_candidate_evaluator_v3 import evaluate_candidates_development
from same_corpus_selection_pressure_v3 import calculate_selection_pressure
from validate_same_corpus_hypothesis_discovery_v3 import validate_candidate_specs
from same_corpus_time_window_v3 import classify_session_position_window_v3

RUNNER_ID = "SAME_CORPUS_MASSIVE_HYPOTHESIS_DISCOVERY_V3_WINDOW_FIXED"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-candidates", type=int, default=1000)
    parser.add_argument("--max-family-groups", type=int, default=25)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent.parent.parent
    bde2_dir = root / "research" / "evidence" / "behavior_discovery_engine_v2"
    v3_dir = root / "research" / "evidence" / "same_corpus_massive_hypothesis_discovery_v3"
    v3_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = root / "research" / "hypotheses" / "historical_corpus" / "kite_nifty_cache_v2" / "canonical" / "NIFTY.csv"
    episodes_path = bde2_dir / "NIFTY_behavior_episodes_v1.jsonl"

    if not dataset_path.exists() or not episodes_path.exists():
        print(f"BLOCKED: Missing required inputs dataset/episodes")
        sys.exit(1)

    print(f"Generating repaired candidate specs (max_candidates={args.max_candidates}, max_family_groups={args.max_family_groups})...")
    candidates = generate_candidate_specs(max_candidates=args.max_candidates, max_family_groups=args.max_family_groups)
    
    # Audit specs
    audit_metrics = validate_candidate_specs(candidates)
    print(f"Audit Metrics: Valid Specs={audit_metrics['valid_specs']}, Blocked Specs={audit_metrics['blocked_specs']}, Placeholders={audit_metrics['placeholder_specs']}")

    if audit_metrics["placeholder_specs"] > 0 or audit_metrics["specs_with_unenforced_fields"] > 0 or audit_metrics["valid_specs"] < 500:
        print("BLOCKED_GOVERNANCE_OR_IMPLEMENTATION_DEFECT: Candidate registry quality gates failed!")
        sys.exit(1)

    # Window classifier metrics
    with episodes_path.open() as f:
        episodes = [json.loads(line) for line in f if line.strip()]

    parsed_count = len(episodes)
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

    success_rate = classified_count / parsed_count if parsed_count > 0 else 0.0

    if success_rate <= 0.80:
        print("V3_REPAIRED_WINDOW_FIXED_BLOCKED_IMPLEMENTATION_DEFECT: Classifier failed >80% success rate threshold!")
        sys.exit(1)

    # 1. Save grammar and candidate registry
    grammar_payload = {
        "schema_version": 1,
        "runner_id": RUNNER_ID,
        "audit_metrics": audit_metrics,
        "window_classifier_metrics": {
            "total_episodes": parsed_count,
            "classified_count": classified_count,
            "timestamp_parse_failed_count": parse_failed_count,
            "unclassifiable_window_count": unclassifiable_count,
            "window_classification_success_rate": success_rate
        },
        "forward_outcomes_used": False,
        "locked_outcomes_accessed": False
    }
    with (v3_dir / "hypothesis_grammar.json").open("w") as f:
        json.dump(grammar_payload, f, indent=2)

    with (v3_dir / "candidate_registry.jsonl").open("w") as f:
        for c in candidates:
            f.write(json.dumps(c) + "\n")

    with (v3_dir / "candidate_registry_summary.json").open("w") as f:
        json.dump({
            "schema_version": 1,
            **audit_metrics,
            "edge_claimed": False,
            "forward_outcomes_used": False,
            "locked_outcomes_accessed": False
        }, f, indent=2)

    # 2. Evaluate candidates in development
    print(f"Evaluating {len(candidates)} candidates in development screen (60% split)...")
    summaries = evaluate_candidates_development(dataset_path, episodes_path, candidates, development_fraction=0.60)

    survivors = [s for s in summaries if s.get("verdict") == "DEVELOPMENT_STRUCTURE_SUPPORTED"]
    print(f"Development screen complete. {len(survivors)} / {len(candidates)} candidates supported.")

    dev_payload = {
        "schema_version": 1,
        "runner_id": RUNNER_ID,
        "development_only": True,
        "forward_outcomes_computed": True,
        "forward_outcomes_scope": "development_sessions_only",
        "locked_outcomes_accessed": False,
        "edge_claimed": False,
        "total_evaluated": len(summaries),
        "supported_survivors_count": len(survivors),
        "status": "V3_REPAIRED_WINDOW_FIXED_DEVELOPMENT_SURVIVORS_REQUIRES_PRE_OUTCOME_NARROWING" if survivors else "V3_REPAIRED_WINDOW_FIXED_NO_DEVELOPMENT_SURVIVORS",
        "candidate_summaries": summaries
    }
    with (v3_dir / "development_screen.json").open("w") as f:
        json.dump(dev_payload, f, indent=2)

    with (v3_dir / "development_survivors.jsonl").open("w") as f:
        for s in survivors:
            f.write(json.dumps(s) + "\n")

    # 3. Multiple Testing & Selection Pressure
    family_groups_count = len({c.get("family_group") for c in candidates})
    selection_pressure = calculate_selection_pressure(
        candidates_generated=len(candidates),
        candidates_evaluated=len(summaries),
        family_groups_count=family_groups_count,
        survivors_count=len(survivors)
    )
    with (v3_dir / "selection_pressure.json").open("w") as f:
        json.dump(selection_pressure, f, indent=2)

    # 4. Failure Registry
    failed_candidates = [s for s in summaries if s.get("verdict") != "DEVELOPMENT_STRUCTURE_SUPPORTED"]
    with (v3_dir / "failure_registry.md").open("w") as f:
        f.write("# Window-Fixed Repaired Campaign V3 Discovery Batch Failure Registry\n\n")
        f.write(f"**Total Evaluated**: {len(summaries)}\n")
        f.write(f"**Failed Candidates**: {len(failed_candidates)}\n\n")
        f.write("## Failure Reason Breakdown\n")
        reasons_hist = {}
        for fc in failed_candidates:
            for r in fc.get("reasons", []):
                reasons_hist[r] = reasons_hist.get(r, 0) + 1
        for r, cnt in sorted(reasons_hist.items(), key=lambda x: x[1], reverse=True):
            f.write(f"- `{r}`: {cnt} candidates\n")

    # Campaign Endpoint calculation
    if survivors:
        campaign_endpoint = "V3_REPAIRED_WINDOW_FIXED_DEVELOPMENT_SURVIVORS_REQUIRES_PRE_OUTCOME_NARROWING"
    else:
        campaign_endpoint = "V3_REPAIRED_WINDOW_FIXED_NO_DEVELOPMENT_SURVIVORS"

    manifest = {
        "schema_version": 1,
        "runner_id": RUNNER_ID,
        "campaign_version": "v3_window_fixed",
        "campaign_endpoint": campaign_endpoint,
        "candidate_specs_generated": len(candidates),
        "valid_candidate_specs_evaluated": audit_metrics["valid_specs"],
        "invalid_candidate_specs": audit_metrics["invalid_specs"],
        "blocked_candidate_specs": audit_metrics["blocked_specs"],
        "placeholder_specs": audit_metrics["placeholder_specs"],
        "family_groups_generated": family_groups_count,
        "timestamp_parse_success_rate": 1.0 - (parse_failed_count / parsed_count if parsed_count > 0 else 0.0),
        "window_classification_success_rate": success_rate,
        "timestamp_parse_failed_count": parse_failed_count,
        "unclassifiable_window_count": unclassifiable_count,
        "classifiable_episode_count": classified_count,
        "development_tests_run": len(summaries),
        "development_survivors_count": len(survivors),
        "locked_validation_run": False,
        "locked_survivors_count": 0,
        "historical_candidates_supported_count": 0,
        "structural_edges_certified_count": 0,
        "edge_claimed": False,
        "execution_viable": False,
        "prospective_supported": False,
        "runtime_authority": "NONE",
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False
    }
    with (v3_dir / "campaign_manifest.json").open("w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nWINDOW-FIXED REPAIRED CAMPAIGN V3 COMPLETE. Endpoint: {campaign_endpoint}")

if __name__ == "__main__":
    main()
