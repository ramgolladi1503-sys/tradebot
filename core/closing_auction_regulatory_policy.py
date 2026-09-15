"""Fail-closed regulatory overlay for the NSE closing-auction regime.

This module is intentionally non-executable: it exposes market-structure metadata for
research, feature labelling and governance. A consultation paper must never become
runtime trading authority until an effective exchange/regulatory circular is separately
verified and promoted.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from typing import Any

from core.time_utils import IST_TZ, now_ist

NORMAL_LATE_SESSION = "NORMAL_LATE_SESSION"
CAS_REFERENCE_TRANSITION = "CAS_REFERENCE_TRANSITION"
CAS_ORDER_DISCOVERY = "CAS_ORDER_DISCOVERY"
CAS_MATCHING = "CAS_MATCHING"
DERIVATIVE_CONVERGENCE = "DERIVATIVE_CONVERGENCE"
OUTSIDE_CAS_STUDY = "OUTSIDE_CAS_STUDY"

SEBI_CONSULTATION_DATE = date(2026, 9, 12)
SEBI_CONSULTATION_STATUS = "CONSULTATION_ONLY_NOT_EFFECTIVE_RULE"
SEBI_CONSULTATION_SOURCE = (
    "SEBI consultation paper dated 2026-09-12: Review of certain aspects of the "
    "Closing Auction Session, Market Timings and Settlement Methodologies for "
    "Derivative Contracts"
)


@dataclass(frozen=True)
class ClosingAuctionWindow:
    normal_start: time = time(14, 45)
    normal_end: time = time(15, 15)
    reference_end: time = time(15, 20)
    order_discovery_end: time = time(15, 30)
    matching_end: time = time(15, 35)
    derivative_end: time = time(15, 40)


@dataclass(frozen=True)
class RegulatoryOverlay:
    as_of: str
    status: str
    source: str
    execution_changes_active: bool
    runtime_override_allowed: bool
    settlement_method_override_active: bool
    post_auction_window_override_active: bool
    cancellation_rule_override_active: bool
    indicative_index_rule_override_active: bool
    proposals: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def regulatory_overlay(*, as_of: date | None = None) -> RegulatoryOverlay:
    """Return the known 2026-09-12 consultation as non-authoritative metadata.

    The function deliberately keeps every proposed execution change disabled. A later
    effective circular must be represented by a new, separately reviewed policy version.
    """

    observed = as_of or now_ist().date()
    proposals: tuple[str, ...] = ()
    if observed >= SEBI_CONSULTATION_DATE:
        proposals = (
            "expiry_settlement_blended_vwap_last_30m_plus_closing_auction",
            "temporary_expiry_settlement_last_30m_continuous_only",
            "post_auction_derivatives_window_reduction_to_5m",
            "order_cancellation_restriction_outside_1pct_reference_band",
            "suppress_estimated_index_close_during_auction",
        )
    return RegulatoryOverlay(
        as_of=observed.isoformat(),
        status=SEBI_CONSULTATION_STATUS,
        source=SEBI_CONSULTATION_SOURCE,
        execution_changes_active=False,
        runtime_override_allowed=False,
        settlement_method_override_active=False,
        post_auction_window_override_active=False,
        cancellation_rule_override_active=False,
        indicative_index_rule_override_active=False,
        proposals=proposals,
    )


def classify_closing_auction_phase(
    observed: datetime,
    *,
    window: ClosingAuctionWindow | None = None,
) -> str:
    """Classify a timestamp using TradeBot's frozen closing-auction study contract."""

    contract = window or ClosingAuctionWindow()
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=IST_TZ)
    else:
        observed = observed.astimezone(IST_TZ)
    current = observed.time().replace(tzinfo=None)

    if contract.normal_start <= current < contract.normal_end:
        return NORMAL_LATE_SESSION
    if contract.normal_end <= current < contract.reference_end:
        return CAS_REFERENCE_TRANSITION
    if contract.reference_end <= current < contract.order_discovery_end:
        return CAS_ORDER_DISCOVERY
    if contract.order_discovery_end <= current < contract.matching_end:
        return CAS_MATCHING
    if contract.matching_end <= current <= contract.derivative_end:
        return DERIVATIVE_CONVERGENCE
    return OUTSIDE_CAS_STUDY


def ordinary_continuous_training_eligible(phase: str) -> bool:
    """Only normal continuous-market observations may train ordinary directional models."""

    return phase == NORMAL_LATE_SESSION


def closing_auction_observation_requires_quarantine(phase: str) -> bool:
    """Return True when an observation must not be treated as ordinary market movement."""

    return phase in {
        CAS_REFERENCE_TRANSITION,
        CAS_ORDER_DISCOVERY,
        CAS_MATCHING,
        DERIVATIVE_CONVERGENCE,
    }


def assert_no_consultation_runtime_override(overlay: RegulatoryOverlay) -> None:
    """Fail closed if consultation-only metadata is ever promoted into runtime authority."""

    forbidden = (
        overlay.execution_changes_active,
        overlay.runtime_override_allowed,
        overlay.settlement_method_override_active,
        overlay.post_auction_window_override_active,
        overlay.cancellation_rule_override_active,
        overlay.indicative_index_rule_override_active,
    )
    if any(forbidden):
        raise RuntimeError("consultation_only_policy_cannot_override_runtime")
