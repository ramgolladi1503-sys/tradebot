"""Regime Architecture Contract V1.

Formalizes downstream regime output roles, semantic boundaries, and safety invariants.
"""
from __future__ import annotations

from typing import Any, Final, Mapping

# Explicit architecture assertions
REGIME_HAS_ORDER_AUTHORITY: Final[bool] = False
RANGE_TO_RV_TRANSITION_CAN_TRIGGER_ENTRY: Final[bool] = False
RANGE_TO_RANGE_VOLATILE_EXECUTION_TRIGGER: Final[bool] = False
TRANSITION_EXECUTION_TRIGGER_ALLOWED: Final[bool] = False
EVENT_STATE_PRODUCTION_VALIDATED: Final[bool] = False
PANIC_STATE_PRODUCTION_VALIDATED: Final[bool] = False
PROBABILITIES_CALIBRATED: Final[bool] = False
RANGE_VOLATILE_ROLE: Final[str] = "STATE_DESCRIPTOR"
TRANSITIONS_ROLE: Final[str] = "DESCRIPTIVE_CONTEXT"

# Governed taxonomy roles
REGIME_OUTPUT_ROLES: Final[dict[str, dict[str, list[str]]]] = {
    "TREND": {
        "allowed": [
            "strategy activation/deactivation",
            "directional-strategy eligibility",
            "trend-risk conditioning",
            "strategy ranking feature",
            "market-state labeling",
            "state-aware parameter selection if pre-existing and separately validated",
        ],
        "prohibited": [
            "direct order placement",
            "guaranteed directional prediction",
            "calibrated probability interpretation",
        ],
    },
    "RANGE": {
        "allowed": [
            "mean-reversion/range-strategy eligibility",
            "trend-strategy suppression",
            "risk conditioning",
            "ranking feature",
            "market-state labeling",
        ],
        "prohibited": [
            "direct entry signal",
            "guaranteed reversal timing",
        ],
    },
    "RANGE_VOLATILE": {
        "allowed": [
            "volatility-risk conditioning",
            "strategy activation/deactivation",
            "risk-limit tightening or strategy suppression where pre-existing policy permits",
            "position-size conditioning if separately governed",
            "spread/slippage caution state",
            "market-state labeling",
            "ranking feature",
            "selection of strategies appropriate for elevated volatility",
        ],
        "prohibited": [
            "treating RANGE -> RANGE_VOLATILE transition as a standalone entry trigger",
            "immediate breakout-entry authorization based solely on the transition",
            "representing the transition timestamp as a certified timing edge",
            "using the transition alone to promote a candidate to execution",
            "using the state as proof of future volatility expansion at a specific horizon",
        ],
    },
    "EVENT": {
        "status": "DATA_BLOCKED / NOT HISTORICALLY VALIDATED",
        "allowed": ["diagnostic/observational only"],
        "prohibited": [
            "production gating as if validated",
            "execution-timing authority",
        ],
    },
    "PANIC": {
        "status": "DATA_BLOCKED / NOT HISTORICALLY VALIDATED",
        "allowed": ["diagnostic/observational only"],
        "prohibited": [
            "production gating as if validated",
            "execution-timing authority",
        ],
    },
}

PROBABILITY_SEMANTICS_ALLOWED_LABELS: Final[tuple[str, ...]] = (
    "heuristic score-derived probability-like vector",
    "normalized heuristic distribution",
    "relative confidence vector",
)

PROBABILITY_SEMANTICS_PROHIBITED_LABELS: Final[tuple[str, ...]] = (
    "calibrated probability",
    "true posterior probability",
    "forecast probability with empirical calibration",
)


def assert_architecture_compliance(
    *,
    is_order_action: bool = False,
    is_entry_trigger: bool = False,
    transition: tuple[str, str] | None = None,
    regime: str | None = None,
    claim_calibrated: bool = False,
    claim_validated_event_panic: bool = False,
) -> bool:
    """Enforce architecture boundaries at runtime or evaluation boundaries."""
    if is_order_action:
        raise PermissionError("VIOLATION V4: Regime outputs have zero direct order authority.")

    if is_entry_trigger and transition == ("RANGE", "RANGE_VOLATILE"):
        raise PermissionError(
            "VIOLATION V1: RANGE -> RANGE_VOLATILE transition cannot trigger entry alone."
        )

    if claim_calibrated:
        raise ValueError(
            "VIOLATION V2: Heuristic softmax scores must not be claimed as calibrated probabilities."
        )

    if claim_validated_event_panic and regime in ("EVENT", "PANIC"):
        raise ValueError(
            f"VIOLATION V3: {regime} is DATA_BLOCKED and not validated for production gating."
        )

    return True
