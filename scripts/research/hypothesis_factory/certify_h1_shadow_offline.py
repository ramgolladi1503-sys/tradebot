#!/usr/bin/env python3
"""Offline certification gate for H1 shadow adapter and trade-intent emission.

This gate is intentionally offline and read-only. It does not touch Kite,
Upstox, broker APIs, paper orders, live orders, or any existing strategy's
qualification status. Its purpose is to block merging unless H1 can be linked
as a shadow-only trade-intent strategy with the frozen predicate preserved.
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from strategies.strategy_registry import load_strategy_registry
from strategies.shadow.h1_trapped_push_snapback import (
    CANDIDATE_ID,
    FROZEN_PREDICATE,
    FROZEN_PREDICATE_VERSION,
    SHADOW_EMISSION_MODE,
    STRATEGY_ID,
    generate_h1_shadow_trade_intents,
)

EXPECTED_FROZEN_PREDICATE = "(range_bps[t-1] > 12.0) & (upper_wick_bps[t-1] > 4.0) & (body_bps[t] < -2.0)"
FORBIDDEN_EXECUTION_FIELDS = {
    "broker_order_id",
    "exchange_order_id",
    "order_type",
    "product_type",
    "quantity",
    "tradingsymbol",
    "instrument_token",
}


def _fixture_bars() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ["2026-08-10 09:15:00", 24581.25, 24607.95, 24557.95, 24602.70],
            ["2026-08-10 09:20:00", 24602.85, 24620.95, 24590.00, 24590.35],
            ["2026-08-10 09:25:00", 24589.95, 24592.40, 24553.55, 24553.55],
            ["2026-08-10 09:30:00", 24557.90, 24560.90, 24533.05, 24533.05],
            ["2026-08-10 09:35:00", 24534.25, 24536.15, 24511.10, 24528.05],
            ["2026-08-10 09:40:00", 24528.85, 24530.35, 24512.95, 24521.15],
            ["2026-08-10 09:45:00", 24521.75, 24538.80, 24518.45, 24527.60],
            ["2026-08-10 09:50:00", 24529.30, 24542.80, 24524.55, 24527.90],
            ["2026-08-10 09:55:00", 24528.25, 24538.20, 24525.05, 24534.25],
        ],
        columns=["datetime", "open", "high", "low", "close"],
    )


def _check_registry() -> dict[str, Any]:
    registry = load_strategy_registry()
    entry = registry.get(STRATEGY_ID)
    if entry is None:
        raise AssertionError(f"{STRATEGY_ID} missing from strategy registry")
    if entry.strategy_kind != "shadow_trade_intent_strategy":
        raise AssertionError(f"Unexpected H1 strategy_kind={entry.strategy_kind}")
    if entry.certification_track != "offline_shadow_certification_only":
        raise AssertionError(f"Unexpected H1 certification_track={entry.certification_track}")
    if "no broker" not in entry.blocked_reason.lower() and "no broker writes" not in entry.blocked_reason.lower():
        raise AssertionError("H1 registry blocked_reason must explicitly preserve no-broker boundary")
    imported = importlib.import_module(entry.module_path.replace("/", ".").removesuffix(".py"))
    if not hasattr(imported, entry.callable_name):
        raise AssertionError(f"Registry callable {entry.callable_name} missing from {entry.module_path}")
    return {
        "strategy_id": entry.strategy_id,
        "strategy_kind": entry.strategy_kind,
        "instrument_family": entry.instrument_family,
        "callable_name": entry.callable_name,
        "certification_supported": entry.certification_supported,
        "certification_track": entry.certification_track,
        "blocked_reason": entry.blocked_reason,
    }


def _check_shadow_intents() -> dict[str, Any]:
    if CANDIDATE_ID != "H1_TRAPPED_PUSH_SNAPBACK":
        raise AssertionError("Candidate id drifted")
    if FROZEN_PREDICATE_VERSION != "H1_V14_FROZEN":
        raise AssertionError("Frozen predicate version drifted")
    if FROZEN_PREDICATE != EXPECTED_FROZEN_PREDICATE:
        raise AssertionError("Frozen predicate text changed")

    intents = generate_h1_shadow_trade_intents(
        _fixture_bars(),
        run_id="OFFLINE_CERTIFICATION_FIXTURE",
        source_file_or_feed="offline_fixture",
    )
    if len(intents) != 1:
        raise AssertionError(f"Expected exactly one H1 shadow intent, got {len(intents)}")
    intent = intents[0]
    if intent["strategy_id"] != STRATEGY_ID:
        raise AssertionError("Intent strategy id mismatch")
    if intent["shadow_trade_action"] != "BUY_PUT_SHADOW":
        raise AssertionError("H1 down pattern must emit BUY_PUT_SHADOW intent")
    if intent["emission_mode"] != SHADOW_EMISSION_MODE:
        raise AssertionError("Intent emission mode mismatch")
    if intent["routeable_order"] is not False:
        raise AssertionError("H1 shadow intent must not be routeable")
    if intent["orders_created"] != 0 or intent["broker_writes_created"] != 0:
        raise AssertionError("H1 shadow intent created order/broker write counts")
    for flag in ("paper_authorized", "live_authorized", "order_authority", "broker_write_authority"):
        if intent[flag] is not False:
            raise AssertionError(f"Authority flag {flag} is not false")
    forbidden_present = sorted(FORBIDDEN_EXECUTION_FIELDS.intersection(intent.keys()))
    if forbidden_present:
        raise AssertionError(f"Shadow intent contains routeable execution fields: {forbidden_present}")
    if intent["outcome_status"] != "OUTCOME_AVAILABLE":
        raise AssertionError("Certification fixture should have available 6-bar outcome")

    return {
        "intents_emitted": len(intents),
        "first_intent": intent,
    }


def run_certification(output_path: Path) -> dict[str, Any]:
    registry_report = _check_registry()
    intent_report = _check_shadow_intents()
    result = {
        "schema_version": "H1_SHADOW_OFFLINE_CERTIFICATION_V1",
        "controlled_verdict": "H1_SHADOW_OFFLINE_CERTIFICATION_PASS",
        "strategy_id": STRATEGY_ID,
        "candidate_id": CANDIDATE_ID,
        "frozen_predicate_version": FROZEN_PREDICATE_VERSION,
        "frozen_predicate_unchanged": True,
        "registry_report": registry_report,
        "intent_report": intent_report,
        "other_strategies_superseded": False,
        "other_strategies_requalified": False,
        "orders_created": 0,
        "broker_writes_created": 0,
        "paper_authorized": False,
        "live_authorized": False,
        "order_authority": False,
        "broker_write_authority": False,
        "prospective_supported": False,
        "execution_viable": False,
        "structural_edge_certified": False,
        "edge_claimed": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline certify H1 shadow trade-intent adapter")
    parser.add_argument(
        "--output",
        default="research/evidence/h1_shadow_offline_certification_v1/OFFLINE_CERTIFICATION_RESULT.json",
    )
    args = parser.parse_args()
    result = run_certification(REPO_ROOT / args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
