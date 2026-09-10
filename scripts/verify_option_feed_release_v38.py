#!/usr/bin/env python3
"""Independent option-feed release verifier and mutation campaign.

The verifier accepts only primitive evidence fields.  It deliberately does
not trust a precomputed readiness boolean or the failed-session summary.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED = (
    "storage_path_authority",
    "repository_local_live_writers",
    "all_persistence_queues_zero",
    "post_quiesce_enqueue_count",
    "row_reconciliation_pass",
    "persistence_restart_readthrough_pass",
    "memory_restart_readthrough_pass",
    "evidence_writer_regression_pass",
    "composition_test_pass",
    "arbitrary_ungoverned_tmp_root_rejected",
    "option_universe_size",
    "option_subscription_request_build_pass",
    "subscription_truth_class",
    "option_ticks_verified",
    "session_binding_failure_class",
    "option_token_domain_consistent",
    "runtime_mirror_reachable",
    "freshness_sla_logic_valid",
    "read_only_safety_pass",
    "broker_write_authority",
    "order_authority",
    "paper_authorized",
    "live_authorized",
)


def verify(evidence: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    missing = [key for key in REQUIRED if key not in evidence]
    errors.extend(f"missing:{key}" for key in missing)
    if missing:
        return {"pass": False, "errors": errors, "checked_fields": 0}

    exact_true = (
        "storage_path_authority",
        "all_persistence_queues_zero",
        "row_reconciliation_pass",
        "persistence_restart_readthrough_pass",
        "memory_restart_readthrough_pass",
        "evidence_writer_regression_pass",
        "composition_test_pass",
        "arbitrary_ungoverned_tmp_root_rejected",
        "option_subscription_request_build_pass",
        "option_ticks_verified",
        "option_token_domain_consistent",
        "runtime_mirror_reachable",
        "freshness_sla_logic_valid",
        "read_only_safety_pass",
    )
    for key in exact_true:
        if evidence.get(key) is not True:
            errors.append(f"not_true:{key}")
    if evidence.get("repository_local_live_writers") != 0:
        errors.append("repository_local_live_writers_nonzero")
    if evidence.get("post_quiesce_enqueue_count") != 0:
        errors.append("post_quiesce_enqueue_count_nonzero")
    if evidence.get("option_universe_size") != 120:
        errors.append("option_universe_size_not_120")
    if evidence.get("subscription_truth_class") not in {
        "ONE_CANONICAL_SUBSCRIPTION_TRUTH",
        "MULTIPLE_RECONCILED_TRUTHS",
    }:
        errors.append("subscription_truth_not_reconciled")
    if evidence.get("session_binding_failure_class") not in {"NONE", ""}:
        errors.append("session_binding_failure")
    if any(evidence.get(key) is not False for key in (
        "broker_write_authority", "order_authority", "paper_authorized", "live_authorized"
    )):
        errors.append("unsafe_authority_flag")
    if evidence.get("broker_write_calls", 0) != 0 or evidence.get("order_calls", 0) != 0:
        errors.append("broker_or_order_calls_nonzero")
    return {
        "pass": not errors,
        "errors": errors,
        "checked_fields": len(REQUIRED),
    }


MUTATIONS = {
    "persistence_import_before_data_root": ("storage_path_authority", False),
    "checkout_local_default_sqlite": ("storage_path_authority", False),
    "stale_prior_session_data_root": ("session_binding_failure_class", "PRIOR_SESSION"),
    "dead_depth_writer": ("evidence_writer_regression_pass", False),
    "hidden_queue_full_rejection": ("all_persistence_queues_zero", False),
    "omitted_task_done": ("row_reconciliation_pass", False),
    "queue_nonzero_at_seal": ("all_persistence_queues_zero", False),
    "post_quiesce_enqueue": ("post_quiesce_enqueue_count", 1),
    "skipped_sqlite_commit": ("persistence_restart_readthrough_pass", False),
    "skipped_checkpoint_close": ("persistence_restart_readthrough_pass", False),
    "deleted_persisted_depth_row": ("row_reconciliation_pass", False),
    "corrupted_evidence_hash": ("evidence_writer_regression_pass", False),
    "truncated_evidence_jsonl": ("evidence_writer_regression_pass", False),
    "empty_option_universe": ("option_universe_size", 0),
    "broken_option_runtime_mirror": ("runtime_mirror_reachable", False),
    "stale_option_freshness": ("freshness_sla_logic_valid", False),
    "broker_write_authority_true": ("broker_write_authority", True),
    "order_authority_true": ("order_authority", True),
}


def mutation_campaign(baseline: dict[str, Any]) -> dict[str, Any]:
    detected: list[str] = []
    undetected: list[str] = []
    for name, (field, value) in MUTATIONS.items():
        mutated = copy.deepcopy(baseline)
        mutated[field] = value
        if not verify(mutated)["pass"]:
            detected.append(name)
        else:
            undetected.append(name)
    return {
        "total": len(MUTATIONS),
        "detected": len(detected),
        "detected_ids": detected,
        "undetected_ids": undetected,
        "pass": not undetected,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        raise SystemExit(f"usage: {argv[0]} EVIDENCE.json")
    evidence = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    result = {
        "independent_verifier": verify(evidence),
        "mutation_campaign": mutation_campaign(evidence),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["independent_verifier"]["pass"] and result["mutation_campaign"]["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
