from __future__ import annotations

from .common import canonical_hash

MECHANISMS = {
    "CROSS_INDEX_RELATIVE_STRENGTH_DISLOCATION": 6,
    "VOLATILITY_STATE_TRANSITION_CONTINUATION": 6,
    "FAILED_AUCTION_REACCEPTANCE": 6,
    "OPENING_CONTINUATION_WITH_INDEX_CONFIRMATION": 6,
}


def campaign_contract(*, source_manifest_hash: str) -> dict:
    return {
        "schema_version": "1.0",
        "campaign_id": "kite-five-minute-governed-discovery-v1",
        "source_manifest_hash": source_manifest_hash,
        "mechanisms": [
            {
                "family": family,
                "max_variants": count,
                "economic_rationale": "Causal five-minute structural index behavior screen; underlying-only development evidence.",
                "causal_timestamps": "signals use completed bars at or before decision timestamp",
            }
            for family, count in MECHANISMS.items()
        ],
        "max_total_variants": 24,
        "minimum_support": 30,
        "stability_gates": [
            "after_cost_expectancy_positive",
            "profit_factor_above_threshold",
            "bootstrap_lower_bound_positive",
            "chronological_fold_stability",
            "leave_one_month_out_stability",
            "concentration_guard",
            "placebo_shift_control",
            "multiple_testing_accounting",
        ],
        "transaction_cost_assumption_bps": 2.0,
        "selection_rule": "select one candidate only if all frozen gates pass; otherwise no edge found",
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def contract_hash(contract: dict) -> str:
    return canonical_hash(contract)
