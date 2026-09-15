#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "research" / "governance" / "edge_factory_truth_layer_v1.json"
EXPECTED_SHA256 = "96688b8d2c0d9235bc8dfde1bd7d4fbdb434dd83d446436961d8b84c1dba5771"
EXPECTED_FAMILIES = [
    "F1_OPENING_GAP_INVENTORY_RESPONSE",
    "F2_OPENING_PRICE_DISCOVERY_AND_RANGE_TRANSITION",
    "F3_VOLATILITY_STATE_TRANSITION",
    "F4_PATH_EFFICIENCY_TREND_VS_EXHAUSTION",
    "F5_INTRADAY_EXTREME_DISPLACEMENT_RESPONSE",
    "F6_CROSS_INDEX_INFORMATION_PROPAGATION",
    "F7_SCHEDULED_EVENT_RESPONSE",
    "F8_FUTURES_SPOT_PROPAGATION_REEVALUATION",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"EDGE_FACTORY_TRUTH_LAYER_V1_BLOCKED: {message}")


def main() -> int:
    raw = CONTRACT.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    require(digest == EXPECTED_SHA256, f"contract hash drift: {digest}")

    c = json.loads(raw)
    require(c["contract_id"] == "TRADEBOT_RESEARCH_TRUTH_LAYER_V1", "contract identity drift")
    require(c["schema_version"] == 1, "schema version drift")
    require(c["family_catalog"] == EXPECTED_FAMILIES, "family catalog drift")

    b = c["campaign_budget"]
    require(b["target_independent_survivors"] == 3, "survivor target drift")
    require(b["target_is_not_a_mandate"] is True, "survivor target became a mandate")
    require(b["max_primary_families"] == 8, "family budget drift")
    require(b["max_primary_tests_per_family"] == 8, "per-family test budget drift")
    require(b["max_primary_cells_total"] == 64, "global test budget drift")
    require(b["family_9_allowed"] is False, "family 9 enabled")
    require(b["new_family_after_outcomes_allowed"] is False, "post-outcome family creation enabled")
    require(b["gate_weakening_after_outcomes_allowed"] is False, "post-outcome gate weakening enabled")
    require(b["post_failure_filter_addition_allowed"] is False, "post-failure filters enabled")
    require(b["failed_signal_inversion_as_new_strategy_allowed"] is False, "failed-signal inversion enabled")

    d = c["historical_data_authority"]
    require(d["default_mode"] == "OHLCV_ONLY", "historical authority widened")
    require(d["historical_bid_ask_authority"] is False, "historical bid/ask authority invented")
    require(d["historical_depth_authority"] is False, "historical depth authority invented")
    require(d["historical_execution_grade"] is False, "historical execution grade enabled")
    require(d["synthetic_bid_ask_allowed"] is False, "synthetic bid/ask enabled")
    require(d["synthetic_depth_allowed"] is False, "synthetic depth enabled")

    t = c["truth_layer"]
    require(t["common_kernel_required"] is True, "common kernel requirement removed")
    forbidden = set(t["forbidden_harness_behaviors"])
    for item in {
        "HARDCODED_NEGATIVE_CONTROL_PASS",
        "HARDCODED_DELAY_RATIO",
        "HARDCODED_CONCENTRATION_METRIC",
        "WRONG_PVALUE_FOR_MULTIPLICITY",
        "INCOMPARABLE_INCREMENTAL_LIFT_METRICS",
        "HOLDOUT_READ_BEFORE_FREEZE",
        "OUTCOME_COLUMNS_IN_FEATURES",
        "BASE_SHA_MASQUERADING_AS_EXECUTED_CODE_SHA",
    }:
        require(item in forbidden, f"forbidden harness behavior removed: {item}")

    s = c["safety"]
    require(s["read_only_market_research"] is True, "research-only boundary removed")
    require(s["broker_write_authority"] is False, "broker write authority enabled")
    require(s["order_authority"] is False, "order authority enabled")
    require(s["allowed_for_live_execution"] is False, "live execution enabled")
    require(s["manual_approval_required"] is True, "manual approval removed")
    require(s["buy_only"] is True, "BUY-only boundary removed")
    require(s["max_hold_minutes"] == 30, "max hold drift")

    r = c["stop_rules"]
    require(r["continue_after_single_family_failure"] is True, "autonomous family loop disabled")
    require(r["stop_after_catalog_exhaustion_even_if_target_not_reached"] is True, "exhaustion stop removed")
    require(r["success"] == "THREE_INDEPENDENT_CONFIRMED_MECHANISM_CLUSTERS", "success rule drift")

    cc = c["change_control"]
    require(cc["in_place_semantic_mutation_allowed"] is False, "in-place V1 mutation enabled")
    require(cc["requires_version_bump_for_semantic_change"] is True, "version-bump law removed")
    require(cc["requires_dedicated_governance_pr"] is True, "dedicated governance PR law removed")
    require(cc["strategy_pr_may_modify_truth_layer"] is False, "strategy PR modification enabled")

    print("EDGE_FACTORY_TRUTH_LAYER_V1_PASS")
    print(f"sha256={digest}")
    print(f"families={len(EXPECTED_FAMILIES)}")
    print("historical_mode=OHLCV_ONLY")
    print("live_authority=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
