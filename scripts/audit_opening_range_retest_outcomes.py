#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research.strategy_outcomes.adapters.opening_range_retest import canonical_outcome_records_hash  # noqa: E402
from research.strategy_outcomes.contract import HORIZONS_MINUTES, canonical_json_hash  # noqa: E402

EXPECTED_CANDIDATE_COUNT = 2215
EXPECTED_CANDIDATE_HASH = "53c8cf67f33d1e958bc2ffa1730c00c86d222e67ae76d2e865da6962892e1d24"
EXPECTED_SOURCE_COUNT = 1512
EXPECTED_SOURCE_HASH = "cf4cc9cacb2db3a2f9cdc006465ebd5f8af6e6146e6a6a59048e1af38f2393bc"
ALLOWED_STATUSES = {"MEASURED", "NO_LEGAL_ENTRY"}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit ORB outcome artifacts.")
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--compare-artifact-dir", type=Path)
    args = parser.parse_args()

    contract = _load(args.artifact_dir / "opening_range_retest_outcome_contract_v1.json")
    summary = _load(args.artifact_dir / "opening_range_retest_outcome_summary_v1.json")
    records_payload = _load(args.artifact_dir / "opening_range_retest_outcome_records_v1.json")
    records = list(records_payload.get("records") or [])
    failures: list[str] = []

    required_contract_fields = {
        "schema_version",
        "strategy_id",
        "entry_policy",
        "horizons_minutes",
        "same_bar_stop_target_policy",
        "claim_boundary",
    }
    absent = sorted(required_contract_fields - set(contract))
    if absent:
        failures.append(f"absent_contract_fields:{','.join(absent)}")
    if contract.get("entry_policy") != "first_bar_after_proposal_ready_at":
        failures.append("entry_policy_mismatch")
    if summary.get("decision") != "ORB_OUTCOMES_MEASURED":
        failures.append("summary_decision_not_measured")
    if summary.get("candidate_count") != EXPECTED_CANDIDATE_COUNT or len(records) != EXPECTED_CANDIDATE_COUNT:
        failures.append("candidate_count_mismatch")
    if summary.get("candidate_semantic_hash") != EXPECTED_CANDIDATE_HASH:
        failures.append("candidate_semantic_hash_mismatch")
    if summary.get("source_count") != EXPECTED_SOURCE_COUNT:
        failures.append("source_count_mismatch")
    if summary.get("source_universe_hash") != EXPECTED_SOURCE_HASH:
        failures.append("source_hash_mismatch")
    status_counts = dict(summary.get("status_counts") or {})
    if sum(int(value) for value in status_counts.values()) != EXPECTED_CANDIDATE_COUNT:
        failures.append("candidate_status_count_mismatch")
    unexpected_statuses = sorted(set(status_counts) - ALLOWED_STATUSES)
    if unexpected_statuses:
        failures.append(f"unexpected_candidate_status:{','.join(unexpected_statuses)}")
    for field, expected in {
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }.items():
        if summary.get(field) is not expected or contract.get(field) is not expected:
            failures.append(f"safety_field_mismatch:{field}")
    record_hash = canonical_outcome_records_hash(records)
    if summary.get("outcome_semantic_hash") != record_hash:
        failures.append("outcome_semantic_hash_mismatch")
    expected_horizons = {str(horizon) for horizon in HORIZONS_MINUTES}
    for record in records:
        if record.get("status") == "MEASURED" and str(record.get("entry_timestamp") or "") <= str(record.get("proposal_ready_at") or ""):
            failures.append(f"illegal_entry:{record.get('candidate_id')}")
            break
        if set(dict(record.get("forward_returns") or {})) != expected_horizons:
            failures.append(f"horizon_mismatch:{record.get('candidate_id')}")
            break
    compare_hash = None
    if args.compare_artifact_dir:
        other_summary = _load(args.compare_artifact_dir / "opening_range_retest_outcome_summary_v1.json")
        compare_hash = other_summary.get("outcome_semantic_hash")
        if compare_hash != summary.get("outcome_semantic_hash"):
            failures.append("comparison_outcome_hash_mismatch")

    verdict = "ORB_OUTCOME_AUDIT_READY" if not failures else "AUDIT_INVALID"
    print(
        json.dumps(
            {
                "verdict": verdict,
                "candidate_count": len(records),
                "outcome_semantic_hash": summary.get("outcome_semantic_hash"),
                "summary_hash": canonical_json_hash(summary),
                "compare_outcome_semantic_hash": compare_hash,
                "failures": failures,
            },
            sort_keys=True,
        )
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
