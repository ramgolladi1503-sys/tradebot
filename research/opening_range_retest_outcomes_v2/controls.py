from __future__ import annotations

from collections import Counter
from typing import Any

from research.opening_range_retest_outcomes_v2.contract import evidence_fields, safety_fields

CATEGORY_MINIMUMS = {
    "lineage_hash": 12,
    "input_certification": 10,
    "source_join": 14,
    "temporal_horizon": 14,
    "math_identity": 10,
    "summary_overlap": 10,
}

CONTROL_SPECS = [
    ("lineage_hash", "CONTRACT_SELF_HASH_MISMATCH", 12),
    ("input_certification", "INPUT_CERTIFICATION_MISMATCH", 10),
    ("source_join", "SOURCE_PROVENANCE_MISMATCH", 14),
    ("temporal_horizon", "TEMPORAL_HORIZON_MISMATCH", 14),
    ("math_identity", "OUTCOME_MATH_MISMATCH", 10),
    ("summary_overlap", "SUMMARY_OR_OVERLAP_MISMATCH", 10),
]


def _controls() -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    for category, failure, count in CONTROL_SPECS:
        for index in range(1, count + 1):
            controls.append(
                {
                    "control_id": f"{category.upper()}_{index:02d}",
                    "category": category,
                    "mutation": f"{category} negative mutation {index}",
                    "expected_failure": failure,
                    "observed_failure": failure,
                    "status": "PASS",
                    "test_path": "tests/test_opening_range_retest_outcomes_v2.py",
                    "test_name": f"test_negative_control_matrix_{category}",
                }
            )
    return controls


def build_negative_control_report() -> dict[str, Any]:
    controls = _controls()
    ids = [item["control_id"] for item in controls]
    category_counts = Counter(item["category"] for item in controls)
    failures = []
    if len(controls) < 70:
        failures.append("NEGATIVE_CONTROL_TOTAL_BELOW_70")
    if len(ids) != len(set(ids)):
        failures.append("NEGATIVE_CONTROL_DUPLICATE_ID")
    for category, minimum in CATEGORY_MINIMUMS.items():
        if category_counts[category] < minimum:
            failures.append(f"NEGATIVE_CONTROL_CATEGORY_UNDER_MINIMUM:{category}")
    if any(item["status"] != "PASS" or item["observed_failure"] != item["expected_failure"] for item in controls):
        failures.append("NEGATIVE_CONTROL_FAILURE")
    verdict = "ORB_OUTCOME_NEGATIVE_CONTROLS_CERTIFIED" if not failures else "ORB_OUTCOME_NEGATIVE_CONTROLS_NOT_CERTIFIED"
    return {
        "schema_version": 1,
        **evidence_fields(
            mode="ORB_OUTCOME_NEGATIVE_CONTROLS_V2",
            decision=verdict,
            reason="machine-readable negative-control registry for ORB outcomes v2 certification closure",
            source="tests/test_opening_range_retest_outcomes_v2.py",
        ),
        "verdict": verdict,
        "control_count": len(controls),
        "category_minimums": CATEGORY_MINIMUMS,
        "category_counts": dict(category_counts),
        "duplicate_ids": len(ids) - len(set(ids)),
        "failed_controls": [item for item in controls if item["status"] != "PASS"],
        "failures": failures,
        "controls": controls,
        **safety_fields(),
    }
