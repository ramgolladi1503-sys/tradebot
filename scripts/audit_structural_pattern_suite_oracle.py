#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.structural_pattern_suite.io import write_json_with_sidecar


REQUIRED_MUTATIONS = {
    "future_bar_inserted_into_feature_input",
    "entry_changed_to_same_decision_bar",
    "peer_leader_changed",
    "previous_high_low_changed",
    "candidate_side_flipped",
    "modified_outcome",
    "accepted_source_row_changed",
    "canonical_candidate_ordering_changed",
    "candidate_deleted",
    "candidate_duplicated",
    "source_manifest_hash_changed",
}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit structural pattern suite v2 oracle results.")
    parser.add_argument("--run-dir", type=Path, default=Path("/Users/madhuram/tradebot-ml-evidence/structural-pattern-suite-v3/run-a"))
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    mutation_path = args.run_dir / "audit/mutation_test_results.json"
    oracle_path = args.run_dir / "audit/independent_oracle.json"
    if not mutation_path.is_file() or not oracle_path.is_file():
        print(json.dumps({"status": "FAIL", "error": "missing v2 oracle artifacts"}, indent=2, sort_keys=True), file=sys.stderr)
        return 2
    mutations = json.loads(mutation_path.read_text(encoding="utf-8"))
    oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
    observed = set(mutations)
    missing = sorted(REQUIRED_MUTATIONS - observed)
    not_detected = sorted(name for name in REQUIRED_MUTATIONS & observed if not mutations.get(name, {}).get("detected"))
    status = "PASS" if not missing and not not_detected and oracle.get("status") == "PASS" and oracle.get("bundle_hash_verified") is True else "FAIL"
    payload = {
        "schema_version": "2.0",
        "status": status,
        "run_dir": str(args.run_dir),
        "primary_strategy_evaluators_imported": False,
        "missing_mutations": missing,
        "mutations_not_detected": not_detected,
        "mutation_tests": {name: mutations.get(name) for name in sorted(REQUIRED_MUTATIONS)},
        "candidate_count": oracle.get("candidate_count"),
        "bundle_hash_verified": oracle.get("bundle_hash_verified"),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    output = args.output or (args.run_dir / "audit/independent_oracle_audit.json")
    write_json_with_sidecar(output, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
