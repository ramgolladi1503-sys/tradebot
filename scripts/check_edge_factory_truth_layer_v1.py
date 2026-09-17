#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "research" / "governance" / "edge_factory_truth_layer_v1.json"
EXPECTED_SHA256 = "55b9cde7cd5327ee3f5b60fe1a60cb6a093eac4071b5ead1d126c828a013d18a"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"EDGE_FACTORY_TRUTH_LAYER_V1_BLOCKED: {message}")


def main() -> int:
    raw = CONTRACT.read_bytes()
    digest_actual = hashlib.sha256(raw).hexdigest()
    require(digest_actual == EXPECTED_SHA256, f"contract hash drift: {digest_actual}")

    c = json.loads(raw)
    require(c["contract_id"] == "TRADEBOT_RESEARCH_TRUTH_LAYER_V1", "contract identity drift")
    require(c["schema_version"] == 1, "schema version drift")
    require("family_catalog" not in c, "truth layer must not freeze a strategy catalog")

    dsc = c["discovery_protocol"]
    require(dsc["mechanism_discovery_allowed"] is True, "autonomous mechanism discovery disabled")
    require(dsc["outcome_blind_discovery_required"] is True, "outcome-blind discovery removed")
    require(dsc["catalog_freeze_before_outcome_access_required"] is True, "catalog pre-registration removed")
    require(dsc["catalog_sha256_required"] is True, "catalog hash requirement removed")
    require(dsc["catalog_order_frozen_after_freeze"] is True, "post-freeze catalog reorder enabled")
    forbidden_inputs = set(dsc["discovery_inputs_forbidden"])
    for item in {
        "FORWARD_RETURN_RESULTS",
        "VALIDATION_RESULTS",
        "LOCKED_CONFIRMATION_RESULTS",
        "STRATEGY_PNL",
        "SHARPE_OR_WIN_RATE_RESULTS",
        "BEST_THRESHOLD_OR_BEST_HORIZON_RESULTS",
        "FAILED_FAMILY_NEAR_MISS_RESULTS_USED_TO_CREATE_REPLACEMENT_FAMILY",
    }:
        require(item in forbidden_inputs, f"discovery outcome firewall weakened: {item}")

    b = c["campaign_budget"]
    require(b["portfolio_size_is_discovered_not_predeclared"] is True, "fixed portfolio-size target reintroduced")
    require(b["strategy_frequency_is_descriptive_not_a_selection_target"] is True, "strategy frequency became a selection target")
    require(b["daily_trade_generation_is_not_a_success_requirement"] is True, "daily trade requirement introduced")
    require(b["default_max_mechanism_families"] == 12, "mechanism-family budget drift")
    require(b["default_max_primary_hypotheses_per_family"] == 4, "per-family hypothesis budget drift")
    require(b["default_max_primary_horizons_per_hypothesis"] == 2, "horizon budget drift")
    require(b["default_max_primary_cells_total"] == 96, "global primary-cell budget drift")
    require(b["catalog_expansion_after_outcome_access_allowed"] is False, "post-outcome catalog expansion enabled")
    require(b["re_discovery_during_evaluation_allowed"] is False, "mid-evaluation discovery enabled")
    require(b["gate_weakening_after_outcomes_allowed"] is False, "post-outcome gate weakening enabled")
    require(b["post_failure_filter_addition_allowed"] is False, "post-failure filters enabled")
    require(b["failed_signal_inversion_as_new_strategy_allowed"] is False, "failed-signal inversion enabled")

    po = c["portfolio_objective"]
    require(po["portfolio_size_is_discovered_from_survivors"] is True, "portfolio size fixed in advance")
    require(po["fixed_target_strategy_count"] is None, "fixed strategy-count quota introduced")
    require(po["fixed_minimum_sessions_per_year"] is None, "fixed annual-frequency floor introduced")
    require(po["daily_trade_requirement"] is False, "daily-trade mandate introduced")
    require(po["no_trade_is_valid_runtime_outcome"] is True, "NO TRADE outcome removed")
    require(po["coverage_pressure_may_not_create_new_strategies"] is True, "coverage pressure may invent strategies")
    require(po["unique_session_coverage_required"] is True, "unique-session coverage removed")
    require(po["signal_overlap_matrix_required"] is True, "signal-overlap analysis removed")
    require(po["mechanism_overlap_screen_required"] is True, "mechanism-overlap screen removed")
    require(po["live_certified_strategy_eligibility_evaluation"] is True, "live eligibility architecture removed")
    require(po["portfolio_risk_arbitration_required"] is True, "portfolio arbitration removed")
    require(po["manual_approval_required"] is True, "manual approval removed from portfolio objective")

    g = c["global_search_accounting"]
    require(g["append_only_global_experiment_ledger_required"] is True, "global ledger removed")
    require(g["trial_count_persists_across_campaign_versions"] is True, "trial count reset enabled")
    require(g["campaign_version_reset_does_not_reset_search_pressure"] is True, "campaign reset can erase search pressure")
    require(g["failed_and_blocked_trials_remain_visible"] is True, "failed/blocked trials can disappear")
    require(g["global_fdr_or_equivalent_search_adjustment_required"] is True, "global search adjustment removed")

    d = c["historical_data_authority"]
    require(d["default_mode"] == "OHLCV_ONLY", "historical authority widened")
    require(d["historical_bid_ask_authority"] is False, "historical bid/ask authority invented")
    require(d["historical_depth_authority"] is False, "historical depth authority invented")
    require(d["historical_execution_grade"] is False, "historical execution grade enabled")
    require(d["synthetic_bid_ask_allowed"] is False, "synthetic bid/ask enabled")
    require(d["synthetic_depth_allowed"] is False, "synthetic depth enabled")

    t = c["truth_layer"]
    require(t["common_kernel_required"] is True, "common kernel requirement removed")
    required_gates = set(t["required_gates"])
    for item in {
        "OUTCOME_BLIND_MECHANISM_DISCOVERY",
        "CATALOG_PRE_REGISTRATION_AND_HASH",
        "BASELINE_VS_CANDIDATE_SAME_METRIC",
        "MULTIPLICITY",
        "GLOBAL_SEARCH_ACCOUNTING",
        "CHRONOLOGICAL_STABILITY",
        "ACTUAL_5M_DELAY",
        "NEGATIVE_CONTROLS",
        "CODE_AND_DATA_PROVENANCE",
        "GLOBAL_TRIAL_LEDGER",
        "PORTFOLIO_INDEPENDENCE_AND_OVERLAP",
    }:
        require(item in required_gates, f"required truth gate removed: {item}")

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
        "MECHANISM_DISCOVERY_AFTER_OUTCOME_ACCESS",
        "CATALOG_MUTATION_AFTER_FREEZE",
        "SEARCH_PRESSURE_RESET_BETWEEN_CAMPAIGNS",
        "FREQUENCY_FILTER_USED_AS_ALPHA_JUSTIFICATION",
        "COVERAGE_PRESSURE_USED_TO_INVENT_STRATEGY",
        "FIXED_SHORT_HOLD_ASSUMED_WITHOUT_STRATEGY_RATIONALE",
    }:
        require(item in forbidden, f"forbidden behavior removed: {item}")

    s = c["safety"]
    require(s["read_only_market_research"] is True, "research-only boundary removed")
    require(s["broker_write_authority"] is False, "broker write authority enabled")
    require(s["order_authority"] is False, "order authority enabled")
    require(s["allowed_for_live_execution"] is False, "live execution enabled")
    require(s["manual_approval_required"] is True, "manual approval removed")
    require(s["buy_only"] is True, "BUY-only boundary removed")
    require(s["intraday_only"] is True, "intraday-only boundary removed")
    require(s["fixed_max_hold_minutes"] is None, "universal max-hold constraint introduced")
    require(s["overnight_positions_allowed"] is False, "overnight holding enabled")
    require(s["entry_and_exit_time_may_vary_by_strategy"] is True, "strategy-specific intraday duration removed")
    require(s["exit_logic_must_be_causal_and_pre_registered"] is True, "causal exit governance removed")

    r = c["stop_rules"]
    require(r["continue_after_single_family_failure"] is True, "autonomous family loop disabled")
    require(r["stop_after_catalog_exhaustion"] is True, "catalog-exhaustion stop removed")
    require(r["success"] == "CAMPAIGN_COMPLETED_WITH_HONEST_SURVIVOR_COUNT_AND_PORTFOLIO_INDEPENDENCE_ASSESSMENT", "success rule drift")
    require(r["zero_survivors_is_valid_campaign_result"] is True, "zero-survivor result made invalid")
    require(r["future_campaign_may_continue_under_same_global_search_accounting"] is True, "future blind campaign continuation removed")
    require(r["exhaustion"] == "FROZEN_CAMPAIGN_CATALOG_EXHAUSTED", "catalog-exhaustion rule drift")

    cc = c["change_control"]
    require(cc["in_place_semantic_mutation_allowed"] is False, "in-place V1 mutation enabled")
    require(cc["requires_version_bump_for_semantic_change"] is True, "version-bump law removed")
    require(cc["requires_dedicated_governance_pr"] is True, "dedicated governance PR law removed")
    require(cc["strategy_pr_may_modify_truth_layer"] is False, "strategy PR modification enabled")

    print("EDGE_FACTORY_TRUTH_LAYER_V1_PASS")
    print(f"sha256={digest_actual}")
    print("catalog_policy=OUTCOME_BLIND_DISCOVERY_THEN_HASH_FREEZE")
    print("portfolio_size_policy=DISCOVERED_NOT_PREDECLARED")
    print("strategy_frequency_policy=DESCRIPTIVE_NOT_TARGET")
    print("holding_period_policy=INTRADAY_VARIABLE_BY_STRATEGY")
    print("no_trade_valid=true")
    print("global_search_pressure_persists=true")
    print("historical_mode=OHLCV_ONLY")
    print("live_authority=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
