#!/usr/bin/env python3
"""Independent Verifier for Trade Truth Level A and Level B under Current Production Lineage.

Loads primitive evidence artifacts:
- TRADE_TRUTH_LEVEL_A_CURRENT_LINEAGE_PRIMITIVE_EVIDENCE.json
- TRADE_TRUTH_LEVEL_B_CURRENT_LINEAGE_PRIMITIVE_EVIDENCE.json

Derives:
- TRADE_TRUTH_LEVEL_A_CURRENT_LINEAGE_EVIDENCE.json
- TRADE_TRUTH_LEVEL_B_CURRENT_LINEAGE_EVIDENCE.json

Performs mandatory mutation-sensitivity testing (flips 1 mandatory test -> verifier MUST fail).
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

REQUIRED_LEVEL_A_PROPERTIES = [
    "record_immutability",
    "deterministic_serialization",
    "record_hash_deterministic",
    "decision_hash_exists",
    "append_only_store",
    "hash_chain_continuity",
    "restart_continuity",
    "trace_retrieval",
    "deletion_detection",
    "reorder_detection",
    "truncation_detection",
    "corruption_detection",
    "unknown_semantics",
    "provenance_immutability",
    "outcome_append_only_amendments",
]

REQUIRED_LEVEL_B_CASES = [
    "compatible_approved_candidate",
    "family_mismatch",
    "family_missing",
    "unapproved_strategy",
    "duplicate_candidate",
    "ranking_winner",
    "risk_rejection",
    "governance_execution_rejection",
    "no_trade",
]


def evaluate_level_a(data: dict) -> tuple[bool, str, list[str]]:
    props = data.get("properties", {})
    failures = []
    for prop in REQUIRED_LEVEL_A_PROPERTIES:
        if prop not in props:
            failures.append(f"MISSING_PROP:{prop}")
        elif not props[prop].get("pass"):
            failures.append(f"FAILED_PROP:{prop}")
    
    if failures:
        return False, "LEVEL_A_VERIFICATION_FAILED", failures
    return True, "CURRENT_LEVEL_A_REVALIDATED", []


def evaluate_level_b(data: dict) -> tuple[bool, str, list[str]]:
    cases = data.get("cases", {})
    failures = []
    for case_key in REQUIRED_LEVEL_B_CASES:
        if case_key not in cases:
            failures.append(f"MISSING_CASE:{case_key}")
        elif not cases[case_key].get("pass"):
            failures.append(f"FAILED_CASE:{case_key}")
    
    if failures:
        return False, "LEVEL_B_VERIFICATION_FAILED", failures
    return True, "CURRENT_LEVEL_B_REVALIDATED", []


def run_mutation_sensitivity_test(a_data: dict, b_data: dict) -> bool:
    """Must fail when an arbitrary mandatory property or case is corrupted."""
    # Corrupt A
    corrupt_a = copy.deepcopy(a_data)
    corrupt_a["properties"]["hash_chain_continuity"]["pass"] = False
    ok_a, _, _ = evaluate_level_a(corrupt_a)
    if ok_a:
        return False

    # Corrupt B
    corrupt_b = copy.deepcopy(b_data)
    corrupt_b["cases"]["risk_rejection"]["pass"] = False
    ok_b, _, _ = evaluate_level_b(corrupt_b)
    if ok_b:
        return False

    return True


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    a_prim_path = repo_root / "TRADE_TRUTH_LEVEL_A_CURRENT_LINEAGE_PRIMITIVE_EVIDENCE.json"
    b_prim_path = repo_root / "TRADE_TRUTH_LEVEL_B_CURRENT_LINEAGE_PRIMITIVE_EVIDENCE.json"

    if not a_prim_path.exists() or not b_prim_path.exists():
        print("ERROR: Missing primitive evidence artifacts.")
        return 1

    with open(a_prim_path, "r") as f:
        a_data = json.load(f)

    with open(b_prim_path, "r") as f:
        b_data = json.load(f)

    # 1. Evaluate Level A
    a_ok, a_status, a_fails = evaluate_level_a(a_data)
    level_a_evidence = {
        "status": a_status,
        "verified_by": "scripts/verify_trade_truth_level_ab_current_lineage.py",
        "failures": a_fails,
        "total_properties_checked": len(REQUIRED_LEVEL_A_PROPERTIES),
        "passed_properties_count": len(REQUIRED_LEVEL_A_PROPERTIES) - len(a_fails),
        "properties": a_data.get("properties"),
    }
    with open(repo_root / "TRADE_TRUTH_LEVEL_A_CURRENT_LINEAGE_EVIDENCE.json", "w") as f:
        json.dump(level_a_evidence, f, indent=2)

    # 2. Evaluate Level B
    b_ok, b_status, b_fails = evaluate_level_b(b_data)
    level_b_evidence = {
        "status": b_status,
        "verified_by": "scripts/verify_trade_truth_level_ab_current_lineage.py",
        "failures": b_fails,
        "total_cases_checked": len(REQUIRED_LEVEL_B_CASES),
        "passed_cases_count": len(REQUIRED_LEVEL_B_CASES) - len(b_fails),
        "cases": b_data.get("cases"),
    }
    with open(repo_root / "TRADE_TRUTH_LEVEL_B_CURRENT_LINEAGE_EVIDENCE.json", "w") as f:
        json.dump(level_b_evidence, f, indent=2)

    # 3. Test Mutation Sensitivity
    mut_ok = run_mutation_sensitivity_test(a_data, b_data)
    print(f"LEVEL_A_STATUS={a_status}")
    print(f"LEVEL_B_STATUS={b_status}")
    print(f"LEVEL_AB_VERIFIER_MUTATION_SENSITIVITY={'PASS' if mut_ok else 'FAIL'}")

    if a_ok and b_ok and mut_ok:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
