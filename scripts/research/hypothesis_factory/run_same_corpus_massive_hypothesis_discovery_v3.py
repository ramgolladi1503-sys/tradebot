#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

from same_corpus_hypothesis_grammar_v3 import generate_candidate_specs
from same_corpus_candidate_evaluator_v3 import evaluate_candidates_development
from same_corpus_selection_pressure_v3 import calculate_selection_pressure

RUNNER_ID = "SAME_CORPUS_MASSIVE_HYPOTHESIS_DISCOVERY_V3"

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

    print(f"Generating candidate specs (max_candidates={args.max_candidates}, max_family_groups={args.max_family_groups})...")
    candidates = generate_candidate_specs(max_candidates=args.max_candidates, max_family_groups=args.max_family_groups)
    print(f"Generated {len(candidates)} candidate specifications across family groups.")

    # 1. Save grammar and candidate registry
    grammar_payload = {
        "schema_version": 1,
        "runner_id": RUNNER_ID,
        "total_generated": len(candidates),
        "max_candidates_limit": args.max_candidates,
        "max_family_groups_limit": args.max_family_groups,
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
            "total_candidates": len(candidates),
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
        "status": "DEVELOPMENT_STRUCTURE_SUPPORTED" if survivors else "NO_DEVELOPMENT_SUPPORTED_CANDIDATE_IN_V3_BATCH",
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

    # 4. Negative Controls Plan
    neg_plan = {
        "schema_version": 1,
        "mandatory_controls": [
            "WRONG_TIME_WINDOW_CONTROL",
            "WRONG_STATE_CONTROL",
            "DIRECTION_INVERSION_CONTROL",
            "SESSION_PERMUTATION_CONTROL",
            "GENERIC_STATE_BASELINE_CONTROL"
        ],
        "status": "PLANNED_IF_SURVIVORS_ADVANCE"
    }
    with (v3_dir / "negative_controls_plan.json").open("w") as f:
        json.dump(neg_plan, f, indent=2)

    # 5. Failure Registry
    failed_candidates = [s for s in summaries if s.get("verdict") != "DEVELOPMENT_STRUCTURE_SUPPORTED"]
    with (v3_dir / "failure_registry.md").open("w") as f:
        f.write("# Campaign V3 Discovery Batch Failure Registry\n\n")
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
        campaign_endpoint = "DEVELOPMENT_STRUCTURE_SUPPORTED_REQUIRES_NARROWING_AND_VALIDATION"
    else:
        campaign_endpoint = "NO_STRUCTURAL_EDGE_FOUND_IN_V3_BATCH"

    manifest = {
        "schema_version": 1,
        "runner_id": RUNNER_ID,
        "campaign_version": "v3",
        "campaign_endpoint": campaign_endpoint,
        "candidate_specs_generated": len(candidates),
        "candidate_specs_evaluated": len(summaries),
        "family_groups_generated": family_groups_count,
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

    print(f"\nCAMPAIGN V3 COMPLETE. Endpoint: {campaign_endpoint}")

if __name__ == "__main__":
    main()
