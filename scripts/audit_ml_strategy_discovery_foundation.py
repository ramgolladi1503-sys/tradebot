#!/usr/bin/env python3
"""Emit a deterministic, offline foundation audit.

This is a contract/self-audit only. It does not train a model, access market or
broker data, backtest, calculate profitability, or make an edge claim.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.ml_strategy_discovery.contracts import (
    SafetyEnvelope,
    semantic_hash,
)


def build_report() -> dict[str, object]:
    safety = SafetyEnvelope()
    safety.validate()
    capabilities = {
        "causal_feature_contract": True,
        "future_only_triple_barrier_labels": True,
        "chronological_partitions": True,
        "purged_anchored_walk_forward": True,
        "deterministic_negative_controls": True,
        "shallow_tree_training": True,
        "xgboost_training_adapter": True,
        "interpretable_rule_extraction": True,
        "candidate_registry_without_live_status": True,
        "independent_contract_audit": True,
        "market_dataset_adapter": False,
        "trained_model": False,
        "backtest_results": False,
        "profit_factor_analysis": False,
        "structural_edge_claim": False,
    }
    report: dict[str, object] = {
        "verdict": "FOUNDATION_IMPLEMENTED_DATA_INTEGRATION_PENDING",
        "claim_boundary": "NO_EDGE_OR_PROFITABILITY_CLAIM",
        "capabilities": capabilities,
        "safety": {
            "read_only": safety.read_only,
            "is_order_action": safety.is_order_action,
            "broker_api_called": safety.broker_api_called,
            "allowed_for_live_execution": (
                safety.allowed_for_live_execution
            ),
            "append": safety.append,
        },
    }
    report["semantic_hash"] = semantic_hash(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        help="replace this JSON path; never append",
    )
    args = parser.parse_args()
    report = build_report()
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
