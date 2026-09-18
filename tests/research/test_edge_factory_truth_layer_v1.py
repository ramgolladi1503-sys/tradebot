from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "research" / "governance" / "edge_factory_truth_layer_v1.json"
EXPECTED_V1_SHA256 = "55b9cde7cd5327ee3f5b60fe1a60cb6a093eac4071b5ead1d126c828a013d18a"

REQUIRED_GATES = {
    "OUTCOME_BLIND_MECHANISM_DISCOVERY",
    "CATALOG_PRE_REGISTRATION_AND_HASH",
    "TIMESTAMP_SEMANTICS",
    "CAUSAL_FEATURES",
    "CHRONOLOGICAL_PARTITION",
    "PROTECTED_CONFIRMATION",
    "BASELINE_VS_CANDIDATE_SAME_METRIC",
    "MULTIPLICITY",
    "GLOBAL_SEARCH_ACCOUNTING",
    "EFFECT_SIZE",
    "CHRONOLOGICAL_STABILITY",
    "SESSION_AND_FOLD_CONCENTRATION",
    "ACTUAL_5M_DELAY",
    "NEGATIVE_CONTROLS",
    "CODE_AND_DATA_PROVENANCE",
    "GLOBAL_TRIAL_LEDGER",
    "PORTFOLIO_INDEPENDENCE_AND_OVERLAP",
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
    "MECHANISM_DISCOVERY_AFTER_OUTCOME_ACCESS",
    "CATALOG_MUTATION_AFTER_FREEZE",
    "SEARCH_PRESSURE_RESET_BETWEEN_CAMPAIGNS",
    "FREQUENCY_FILTER_USED_AS_ALPHA_JUSTIFICATION",
    "COVERAGE_PRESSURE_USED_TO_INVENT_STRATEGY",
    "FIXED_SHORT_HOLD_ASSUMED_WITHOUT_STRATEGY_RATIONALE",
}


def _raw() -> bytes:
    return CONTRACT_PATH.read_bytes()


def _contract() -> dict:
    return json.loads(_raw())


def test_truth_layer_v1_is_hash_pinned() -> None:
    assert hashlib.sha256(_raw()).hexdigest() == EXPECTED_V1_SHA256


def test_truth_layer_freezes_process_and_portfolio_objective_not_strategy_catalog() -> None:
    c = _contract()
    assert c["contract_id"] == "TRADEBOT_RESEARCH_TRUTH_LAYER_V1"
    assert c["schema_version"] == 1
    assert "family_catalog" not in c
    assert c["purpose"] == "Permanent anti-drift research authority: freeze the scientific process and the portfolio objective, not a fixed strategy catalog."


def test_discovery_is_autonomous_but_outcome_blind_and_preregistered() -> None:
    d = _contract()["discovery_protocol"]
    assert d["mechanism_discovery_allowed"] is True
    assert d["outcome_blind_discovery_required"] is True
    assert d["catalog_freeze_before_outcome_access_required"] is True
    assert d["catalog_sha256_required"] is True
    assert d["catalog_order_frozen_after_freeze"] is True
    assert d["mechanism_rationale_required"] is True
    assert d["duplicate_mechanism_screen_required"] is True
    assert d["prior_closed_family_screen_required"] is True

    forbidden = set(d["discovery_inputs_forbidden"])
    assert {
        "FORWARD_RETURN_RESULTS",
        "VALIDATION_RESULTS",
        "LOCKED_CONFIRMATION_RESULTS",
        "STRATEGY_PNL",
        "SHARPE_OR_WIN_RATE_RESULTS",
        "BEST_THRESHOLD_OR_BEST_HORIZON_RESULTS",
        "FAILED_FAMILY_NEAR_MISS_RESULTS_USED_TO_CREATE_REPLACEMENT_FAMILY",
    } <= forbidden


def test_campaign_budget_is_finite_without_fixing_portfolio_size_or_frequency() -> None:
    b = _contract()["campaign_budget"]
    assert b["default_max_mechanism_families"] == 12
    assert b["default_max_primary_hypotheses_per_family"] == 4
    assert b["default_max_primary_horizons_per_hypothesis"] == 2
    assert b["default_max_primary_cells_total"] == 96
    assert b["portfolio_size_is_discovered_not_predeclared"] is True
    assert b["strategy_frequency_is_descriptive_not_a_selection_target"] is True
    assert b["daily_trade_generation_is_not_a_success_requirement"] is True
    assert b["catalog_expansion_after_outcome_access_allowed"] is False
    assert b["re_discovery_during_evaluation_allowed"] is False
    assert b["gate_weakening_after_outcomes_allowed"] is False
    assert b["post_failure_filter_addition_allowed"] is False
    assert b["failed_signal_inversion_as_new_strategy_allowed"] is False


def test_portfolio_objective_matches_canonical_user_goal() -> None:
    p = _contract()["portfolio_objective"]
    assert p["strategy_frequency_policy"] == "FREQUENT_MODERATE_OR_RARE_ALL_ALLOWED"
    assert p["rare_strategy_allowed_if_evidence_sufficient"] is True
    assert p["frequent_strategy_allowed_if_evidence_sufficient"] is True
    assert p["fixed_minimum_sessions_per_year"] is None
    assert p["fixed_target_strategy_count"] is None
    assert p["portfolio_size_is_discovered_from_survivors"] is True
    assert p["daily_trade_requirement"] is False
    assert p["no_trade_is_valid_runtime_outcome"] is True
    assert p["unique_session_coverage_required"] is True
    assert p["signal_overlap_matrix_required"] is True
    assert p["mechanism_overlap_screen_required"] is True
    assert p["coverage_pressure_may_not_create_new_strategies"] is True
    assert p["live_certified_strategy_eligibility_evaluation"] is True
    assert p["multiple_simultaneous_candidates_allowed"] is True
    assert p["portfolio_risk_arbitration_required"] is True
    assert p["manual_approval_required"] is True


def test_search_pressure_never_resets_between_campaigns() -> None:
    g = _contract()["global_search_accounting"]
    assert g["append_only_global_experiment_ledger_required"] is True
    assert g["trial_count_persists_across_campaign_versions"] is True
    assert g["campaign_version_reset_does_not_reset_search_pressure"] is True
    assert g["failed_and_blocked_trials_remain_visible"] is True
    assert g["global_fdr_or_equivalent_search_adjustment_required"] is True
    assert g["pbo_dsr_or_search_adjusted_inference_required_when_applicable"] is True


def test_truth_layer_requires_common_kernel_and_core_gates() -> None:
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


def test_safety_contract_is_intraday_only_without_universal_short_hold() -> None:
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
    assert s["intraday_only"] is True
    assert s["fixed_max_hold_minutes"] is None
    assert s["overnight_positions_allowed"] is False
    assert s["entry_and_exit_time_may_vary_by_strategy"] is True
    assert s["exit_logic_must_be_causal_and_pre_registered"] is True


def test_stop_rules_are_catalog_exhaustion_and_honest_survivor_accounting() -> None:
    r = _contract()["stop_rules"]
    assert r["success"] == "CAMPAIGN_COMPLETED_WITH_HONEST_SURVIVOR_COUNT_AND_PORTFOLIO_INDEPENDENCE_ASSESSMENT"
    assert r["exhaustion"] == "FROZEN_CAMPAIGN_CATALOG_EXHAUSTED"
    assert r["continue_after_single_family_failure"] is True
    assert r["stop_after_catalog_exhaustion"] is True
    assert r["zero_survivors_is_valid_campaign_result"] is True
    assert r["future_campaign_may_continue_under_same_global_search_accounting"] is True
    assert "OUTCOME_BLIND_DISCOVERY_BOUNDARY_CANNOT_BE_PROVEN" in r["global_blocker"]


def test_prior_family_custody_cannot_be_silently_rewritten() -> None:
    p = _contract()["prior_family_custody"]
    assert p["CONSTITUENT_BREADTH_DIFFUSION"] == "CLOSED_NO_ROBUST_EDGE"
    assert p["OPTION_IMPLIED_VS_REALIZED"] == "CLOSED_NO_DEFENDABLE_PHENOMENON"
    assert p["FUTURES_SPOT_OHLCV_PROPAGATION_V1"] == "QUARANTINED_HARNESS_DEFECT_REEVAL_ONLY_IF_PRE_REGISTERED_IN_FUTURE_CAMPAIGN"
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
