from __future__ import annotations

from .common import canonical_hash

MECHANISMS = {
    "CROSS_INDEX_RELATIVE_STRENGTH_DISLOCATION": 6,
    "VOLATILITY_STATE_TRANSITION_CONTINUATION": 6,
    "FAILED_AUCTION_REACCEPTANCE": 6,
    "OPENING_CONTINUATION_WITH_INDEX_CONFIRMATION": 6,
}
GATES = {
    "minimum_trade_support": {"threshold": 30},
    "net_expectancy_positive": {"threshold_bps": 0.0},
    "profit_factor": {"threshold": 1.20},
    "bootstrap_lower_bound_positive": {
        "threshold_bps": 0.0,
        "method": "deterministic bootstrap seed 1729",
    },
    "chronological_fold_stability": {
        "positive_fold_fraction_threshold": 0.75,
        "fold_count": 4,
    },
    "leave_one_month_out_stability": {"required": True},
    "leave_one_regime_out_stability": {"required_when_enough_observations": True},
    "largest_session_contribution": {"maximum_share": 0.25},
    "largest_month_contribution": {"maximum_share": 0.35},
    "parameter_neighbour_stability": {"required": True},
    "placebo_control": {"required_result": "FAILS_TO_PASS"},
    "shifted_signal_control": {"required_result": "FAILS_TO_PASS"},
    "multiple_testing_correction": {
        "method": "Bonferroni over 24 frozen variants",
        "alpha": 0.05,
    },
}


def frozen_variants() -> list[dict]:
    variants = []
    for family, count in MECHANISMS.items():
        for index in range(count):
            variants.append(
                {
                    "mechanism_id": family,
                    "variant_id": f"{family}_V{index + 1:02d}",
                    "parameters": {
                        "threshold_bps": float((index + 1) * 2),
                        "decision_bar_offset": 3,
                        "entry_timestamp": "09:30 Asia/Kolkata completed-bar decision",
                        "exit_timestamp": "15:25 Asia/Kolkata completed-bar close",
                        "direction_semantics": (
                            "positive dislocation screens long relative NIFTY; "
                            "negative dislocation screens short relative NIFTY"
                        ),
                    },
                }
            )
    return variants


def campaign_contract(*, source_manifest_hash: str) -> dict:
    return {
        "schema_version": "1.0",
        "campaign_id": "kite-five-minute-governed-discovery-v1",
        "source_manifest_hash": source_manifest_hash,
        "frozen_variants": frozen_variants(),
        "gates": GATES,
        "deterministic_random_seeds": {
            "bootstrap": 1729,
            "permutation": 2718,
        },
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
        "minimum_support": GATES["minimum_trade_support"]["threshold"],
        "stability_gates": list(GATES),
        "transaction_cost_assumption_bps": 2.0,
        "selection_rule": "select one candidate only if all frozen gates pass; otherwise no edge found",
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def contract_hash(contract: dict) -> str:
    return canonical_hash(contract)
