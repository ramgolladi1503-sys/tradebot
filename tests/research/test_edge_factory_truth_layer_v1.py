from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "research" / "governance" / "edge_factory_truth_layer_v1.json"
EXPECTED_V1_SHA256 = "96688b8d2c0d9235bc8dfde1bd7d4fbdb434dd83d446436961d8b84c1dba5771"

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

REQUIRED_GATES = {
    "TIMESTAMP_SEMANTICS",
    "CAUSAL_FEATURES",
    "CHRONOLOGICAL_PARTITION",
    "PROTECTED_CONFIRMATION",
    "BASELINE_VS_CANDIDATE_SAME_METRIC",
    "MULTIPLICITY",
    "EFFECT_SIZE",
    "CHRONOLOGICAL_STABILITY",
    "SESSION_AND_FOLD_CONCENTRATION",
    "ACTUAL_5M_DELAY",
    "NEGATIVE_CONTROLS",
    "CODE_AND_DATA_PROVENANCE",
    "GLOBAL_TRIAL_LEDGER",
}

FORBIDDEN_HARNESS_BEHAVIORS = {
    "HARDCODED_NEGATIVE_CONTROL_PASS",
    "HARDCODED_DELAY_RATIO",
    "HARDCODED_CONCENTRATION_METRIC",
    "WRONG_PVALUE_FOR_MULTIPLICITY",
    "INCOMPARABLE_INCREMENTAL_LIFT_METRICS",
    "HOLDOUT_READ_BEFORE_FREEZE",
    "OUTCOME_COLUMNS_IN_FEATURES",
    "BASE_SHA_MASQUERADING_AS_EXECUTED_CODE_SHA",
}


def _raw() -> bytes:
    return CONTRACT_PATH.read_bytes()


def _contract() -> dict:
    return json.loads(_raw())


def test_truth_layer_v1_is_hash_pinned() -> None:
    """Any in-place edit to V1 must fail until a dedicated governance change updates the lock."""
    assert hashlib.sha256(_raw()).hexdigest() == EXPECTED_V1_SHA256


def test_truth_layer_identity_and_family_catalog_are_frozen() -> None:
    c = _contract()
    assert c["contract_id"] == "TRADEBOT_RESEARCH_TRUTH_LAYER_V1"
    assert c["schema_version"] == 1
    assert c["family_catalog"] == EXPECTED_FAMILIES
    assert len(c["family_catalog"]) == 8
    assert not any(name.startswith("F9_") for name in c["family_catalog"])


def test_campaign_budget_cannot_turn_survivor_target_into_a_mandate() -> None:
    b = _contract()["campaign_budget"]
    assert b["target_independent_survivors"] == 3
    assert b["target_is_not_a_mandate"] is True
    assert b["max_primary_families"] == 8
    assert b["max_primary_tests_per_family"] == 8
    assert b["max_primary_cells_total"] == 64
    assert b["family_9_allowed"] is False
    assert b["new_family_after_outcomes_allowed"] is False
    assert b["gate_weakening_after_outcomes_allowed"] is False
    assert b["post_failure_filter_addition_allowed"] is False
    assert b["failed_signal_inversion_as_new_strategy_allowed"] is False


def test_truth_layer_requires_common_kernel_and_all_core_gates() -> None:
    t = _contract()["truth_layer"]
    assert t["common_kernel_required"] is True
    assert set(t["required_gates"]) == REQUIRED_GATES
    assert set(t["forbidden_harness_behaviors"]) == FORBIDDEN_HARNESS_BEHAVIORS


def test_historical_authority_fails_closed_without_microstructure() -> None:
    d = _contract()["historical_data_authority"]
    assert d["default_mode"] == "OHLCV_ONLY"
    assert d["historical_bid_ask_authority"] is False
    assert d["historical_depth_authority"] is False
    assert d["historical_execution_grade"] is False
    assert d["synthetic_bid_ask_allowed"] is False
    assert d["synthetic_depth_allowed"] is False
    assert d["historical_option_candles_label"] == "HISTORICAL_OPTION_CANDLE_RESEARCH_ONLY"


def test_safety_contract_never_creates_execution_authority() -> None:
    s = _contract()["safety"]
    assert s["read_only_market_research"] is True
    assert s["is_order_action"] is False
    assert s["broker_api_called"] is False
    assert s["broker_write_authority"] is False
    assert s["order_authority"] is False
    assert s["orders_placed"] == 0
    assert s["orders_modified"] == 0
    assert s["orders_cancelled"] == 0
    assert s["paper_orders"] == 0
    assert s["allowed_for_live_execution"] is False
    assert s["manual_approval_required"] is True
    assert s["buy_only"] is True
    assert s["max_hold_minutes"] == 30


def test_stop_rules_force_success_exhaustion_or_real_global_blocker() -> None:
    r = _contract()["stop_rules"]
    assert r["success"] == "THREE_INDEPENDENT_CONFIRMED_MECHANISM_CLUSTERS"
    assert r["exhaustion"] == "ALL_EIGHT_FAMILIES_EXECUTED_BLOCKED_RETIRED_OR_CONFIRMED"
    assert r["continue_after_single_family_failure"] is True
    assert r["stop_after_catalog_exhaustion_even_if_target_not_reached"] is True
    assert set(r["global_blocker"]) == {
        "COMMON_KERNEL_CANNOT_BE_CERTIFIED",
        "AUTHORITATIVE_SHARED_DATA_CORRUPTED_OR_UNUSABLE",
        "PROTECTED_EVIDENCE_IRREPARABLY_CONTAMINATED",
        "CONTINUATION_REQUIRES_FABRICATION_OR_UNSAFE_MUTATION_OR_ORDER_AUTHORITY",
    }


def test_prior_family_custody_cannot_be_silently_rewritten() -> None:
    p = _contract()["prior_family_custody"]
    assert p["CONSTITUENT_BREADTH_DIFFUSION"] == "CLOSED_NO_ROBUST_EDGE"
    assert p["OPTION_IMPLIED_VS_REALIZED"] == "CLOSED_NO_DEFENDABLE_PHENOMENON"
    assert p["FUTURES_SPOT_OHLCV_PROPAGATION_V1"] == "QUARANTINED_HARNESS_DEFECT_SINGLE_CLEAN_REEVAL_ALLOWED"
    assert p["NIFTY_TUESDAY_0DTE_OHLCV_STRUCTURE_V1"] == "QUARANTINED_HARNESS_DEFECT_REEVAL_DEFERRED"


def test_change_control_requires_new_version_and_governance_pr() -> None:
    c = _contract()["change_control"]
    assert c["in_place_semantic_mutation_allowed"] is False
    assert c["requires_version_bump_for_semantic_change"] is True
    assert c["requires_dedicated_governance_pr"] is True
    assert c["strategy_pr_may_modify_truth_layer"] is False
    assert c["requires_adversarial_review"] is True
    assert c["requires_contract_hash_update"] is True
    assert c["requires_explicit_rationale"] is True
