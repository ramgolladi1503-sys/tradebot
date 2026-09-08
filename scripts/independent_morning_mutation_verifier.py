#!/usr/bin/env python3
"""Independently recompute the Morning Readiness mutation invariants."""
from __future__ import annotations

import json
from pathlib import Path


REQUIRED = (
    "broker_write_authority", "cas_input_missing", "cas_timestamp_wrong",
    "decision_failure_preserves_observer", "dirty_tree", "evidence_corruption",
    "evidence_writer_dead", "live_authorized", "option_feed_missing",
    "order_authority", "paper_authorized", "post_quiesce_enqueue",
    "process_integrity_failure", "queue_nonzero_at_seal", "ranking_unavailable",
    "root_collision", "wrong_data_root", "wrong_release_sha",
)


def verify(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, dict):
        raise ValueError("mutation_cases_missing")
    missing = [name for name in REQUIRED if cases.get(name) is not True]
    extra = sorted(set(cases) - set(REQUIRED))
    result = {
        "required_mutation_ids": list(REQUIRED),
        "missing_mutation_ids": missing,
        "unexpected_mutation_ids": extra,
        "mutations_detected": len(REQUIRED) - len(missing),
        "mutations_total": len(REQUIRED),
        "independent_mutation_verifier_pass": not missing and not extra,
        "read_only": payload.get("read_only") is True,
        "orders_placed": payload.get("orders_placed") == 0,
    }
    result["independent_mutation_verifier_pass"] = bool(
        result["independent_mutation_verifier_pass"] and result["read_only"] and result["orders_placed"]
    )
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.artifact), indent=2, sort_keys=True))
