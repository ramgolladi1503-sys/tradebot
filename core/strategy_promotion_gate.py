"""Read-only strategy promotion gate evidence for EDGE-89.

This module evaluates the EDGE-88 lifecycle-state report and emits deterministic
promotion-gate evidence. It never promotes strategies, mutates lifecycle state,
executes trades, routes orders, calls brokers, wires runtime behavior, or changes
UI surfaces.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from core.strategy_lifecycle_states import (
    LIFECYCLE_STATE_ACTIVE_ELIGIBLE,
    STRATEGY_LIFECYCLE_REDUCED,
)

STRATEGY_PROMOTION_GATE_SCHEMA_VERSION = 1
STRATEGY_PROMOTION_GATE_SOURCE = "strategy_promotion_gate_v1"

STRATEGY_PROMOTION_GATE_EVALUATED = "STRATEGY_PROMOTION_GATE_EVALUATED"
STRATEGY_PROMOTION_GATE_BLOCKED = "STRATEGY_PROMOTION_GATE_BLOCKED"

PROMOTION_DECISION_CANDIDATE = "PROMOTION_CANDIDATE"
PROMOTION_DECISION_BLOCKED = "PROMOTION_BLOCKED"
PROMOTION_DECISION_REVIEW = "PROMOTION_REVIEW_REQUIRED"

INVALID_LIFECYCLE_REPORT_REASON = "invalid_strategy_lifecycle_report"
NO_LIFECYCLE_STATES_REASON = "no_strategy_lifecycle_states"
INVALID_PROMOTION_POLICY_REASON = "invalid_strategy_promotion_policy"
ACTIVE_ELIGIBLE_PROMOTION_CANDIDATE_REASON = "active_eligible_promotion_candidate"
LIFECYCLE_NOT_ACTIVE_ELIGIBLE_REASON = "lifecycle_not_active_eligible"
NOT_ELIGIBLE_FOR_PROMOTION_REASON = "not_eligible_for_promotion"
PROMOTION_REVIEW_REQUIRED_REASON = "promotion_review_required"
LOW_PROMOTION_SAMPLE_REASON = "low_promotion_sample"
NON_POSITIVE_EXPECTANCY_REASON = "non_positive_expectancy"
LOW_WIN_RATE_REASON = "low_win_rate"
UNKNOWN_FAMILY = "UNKNOWN_FAMILY"

DEFAULT_PROMOTION_MIN_CLOSED_TRADES = 20
DEFAULT_PROMOTION_MIN_WIN_RATE = 0.5
_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class StrategyPromotionPolicy:
    """Policy thresholds for read-only promotion-gate evidence."""

    promotion_min_closed_trades: int = DEFAULT_PROMOTION_MIN_CLOSED_TRADES
    promotion_min_win_rate: float = DEFAULT_PROMOTION_MIN_WIN_RATE

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "promotion_min_closed_trades": self.promotion_min_closed_trades,
            "promotion_min_win_rate": self.promotion_min_win_rate,
            "read_only": True,
            "append": False,
        }
        _mark_non_action(payload)
        return payload


@dataclass(frozen=True)
class StrategyPromotionGateDecision:
    """Read-only promotion-gate decision for one strategy family."""

    strategy_family: str
    decision: str
    reason_code: str
    reasons: tuple[str, ...]
    lifecycle_state: str
    source_recommendation: str
    strategy_ids: tuple[str, ...]
    regimes: tuple[str, ...]
    closed_count: int
    net_expectancy_per_trade: float
    net_win_rate: float
    sample_ok: bool
    eligible_for_promotion: bool
    requires_review: bool
    promotion_ready: bool = False
    promotion_applied: bool = False
    lifecycle_state_mutated: bool = False
    read_only: bool = True
    append: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "strategy_family": self.strategy_family,
            "decision": self.decision,
            "reason_code": self.reason_code,
            "reasons": list(self.reasons),
            "lifecycle_state": self.lifecycle_state,
            "source_recommendation": self.source_recommendation,
            "strategy_ids": list(self.strategy_ids),
            "regimes": list(self.regimes),
            "closed_count": self.closed_count,
            "net_expectancy_per_trade": self.net_expectancy_per_trade,
            "net_win_rate": self.net_win_rate,
            "sample_ok": self.sample_ok,
            "eligible_for_promotion": self.eligible_for_promotion,
            "requires_review": self.requires_review,
            "promotion_ready": self.promotion_ready,
            "promotion_applied": self.promotion_applied,
            "lifecycle_state_mutated": self.lifecycle_state_mutated,
            "read_only": self.read_only,
            "append": self.append,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload


@dataclass(frozen=True)
class StrategyPromotionGateReport:
    """Read-only promotion-gate report derived from lifecycle-state evidence."""

    schema_version: int
    source: str
    status: str
    reason_code: str
    reasons: tuple[str, ...]
    lifecycle_report_valid: bool
    family_count: int
    promotion_candidate_count: int
    blocked_count: int
    review_required_count: int
    policy: StrategyPromotionPolicy
    decisions: tuple[StrategyPromotionGateDecision, ...]
    read_only: bool = True
    append: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "source": self.source,
            "status": self.status,
            "reason_code": self.reason_code,
            "reasons": list(self.reasons),
            "lifecycle_report_valid": self.lifecycle_report_valid,
            "family_count": self.family_count,
            "promotion_candidate_count": self.promotion_candidate_count,
            "blocked_count": self.blocked_count,
            "review_required_count": self.review_required_count,
            "policy": self.policy.to_payload(),
            "decisions": [decision.to_payload() for decision in self.decisions],
            "read_only": self.read_only,
            "append": self.append,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def build_strategy_promotion_gate_report(
    lifecycle_report: Mapping[str, Any] | Any,
    *,
    promotion_min_closed_trades: Any = DEFAULT_PROMOTION_MIN_CLOSED_TRADES,
    promotion_min_win_rate: Any = DEFAULT_PROMOTION_MIN_WIN_RATE,
) -> StrategyPromotionGateReport:
    """Evaluate read-only promotion readiness from EDGE-88 lifecycle evidence."""

    policy = _policy(
        promotion_min_closed_trades=promotion_min_closed_trades,
        promotion_min_win_rate=promotion_min_win_rate,
    )
    if policy is None:
        return _blocked_report(
            reason_code=INVALID_PROMOTION_POLICY_REASON,
            reasons=(INVALID_PROMOTION_POLICY_REASON,),
            policy=StrategyPromotionPolicy(),
            metadata={"blocked_before_promotion_evaluation": True},
        )

    payload = _payload(lifecycle_report)
    if not _lifecycle_report_valid(payload):
        return _blocked_report(
            reason_code=INVALID_LIFECYCLE_REPORT_REASON,
            reasons=(INVALID_LIFECYCLE_REPORT_REASON,),
            policy=policy,
            metadata={"blocked_before_promotion_evaluation": True},
        )

    states = tuple(dict(item) for item in payload.get("states") or [] if isinstance(item, Mapping))
    if not states:
        return _blocked_report(
            reason_code=NO_LIFECYCLE_STATES_REASON,
            reasons=(NO_LIFECYCLE_STATES_REASON,),
            policy=policy,
            lifecycle_report_valid=True,
            metadata={"derived_from": str(payload.get("source") or "strategy_lifecycle_states")},
        )

    decisions = tuple(_decision_from_state(item, policy) for item in states)
    report_reasons = _dedupe(decision.reason_code for decision in decisions)
    return StrategyPromotionGateReport(
        schema_version=STRATEGY_PROMOTION_GATE_SCHEMA_VERSION,
        source=STRATEGY_PROMOTION_GATE_SOURCE,
        status=STRATEGY_PROMOTION_GATE_EVALUATED,
        reason_code="ok",
        reasons=report_reasons,
        lifecycle_report_valid=True,
        family_count=len(decisions),
        promotion_candidate_count=sum(1 for decision in decisions if decision.decision == PROMOTION_DECISION_CANDIDATE),
        blocked_count=sum(1 for decision in decisions if decision.decision == PROMOTION_DECISION_BLOCKED),
        review_required_count=sum(1 for decision in decisions if decision.decision == PROMOTION_DECISION_REVIEW),
        policy=policy,
        decisions=decisions,
        metadata={
            "derived_from": str(payload.get("source") or "strategy_lifecycle_states"),
            "evidence_only": True,
            "does_not_change_strategy_state": True,
            "does_not_promote_or_suspend_or_retire": True,
        },
    )


def _decision_from_state(
    state: Mapping[str, Any],
    policy: StrategyPromotionPolicy,
) -> StrategyPromotionGateDecision:
    lifecycle_state = _text(state.get("lifecycle_state"))
    closed_count = _int(state.get("closed_count"))
    net_expectancy = _float(state.get("net_expectancy_per_trade"))
    win_rate = _float(state.get("net_win_rate"))
    sample_ok = bool(state.get("sample_ok"))
    eligible_for_promotion = bool(state.get("eligible_for_promotion"))
    requires_review = bool(state.get("requires_review"))

    reasons: list[str] = []
    if lifecycle_state != LIFECYCLE_STATE_ACTIVE_ELIGIBLE:
        reasons.append(LIFECYCLE_NOT_ACTIVE_ELIGIBLE_REASON)
    if not eligible_for_promotion:
        reasons.append(NOT_ELIGIBLE_FOR_PROMOTION_REASON)
    if requires_review:
        reasons.append(PROMOTION_REVIEW_REQUIRED_REASON)
    if not sample_ok or closed_count < policy.promotion_min_closed_trades:
        reasons.append(LOW_PROMOTION_SAMPLE_REASON)
    if net_expectancy <= 0.0:
        reasons.append(NON_POSITIVE_EXPECTANCY_REASON)
    if win_rate < policy.promotion_min_win_rate:
        reasons.append(LOW_WIN_RATE_REASON)

    if not reasons:
        decision = PROMOTION_DECISION_CANDIDATE
        reason_code = ACTIVE_ELIGIBLE_PROMOTION_CANDIDATE_REASON
        promotion_ready = True
    elif PROMOTION_REVIEW_REQUIRED_REASON in reasons:
        decision = PROMOTION_DECISION_REVIEW
        reason_code = PROMOTION_REVIEW_REQUIRED_REASON
        promotion_ready = False
    else:
        decision = PROMOTION_DECISION_BLOCKED
        reason_code = reasons[0]
        promotion_ready = False

    return StrategyPromotionGateDecision(
        strategy_family=_text(state.get("strategy_family")) or UNKNOWN_FAMILY,
        decision=decision,
        reason_code=reason_code,
        reasons=_dedupe((reason_code, *reasons, *_tuple_text(state.get("reasons")))),
        lifecycle_state=lifecycle_state or "UNKNOWN",
        source_recommendation=_text(state.get("source_recommendation")) or "UNKNOWN",
        strategy_ids=_tuple_text(state.get("strategy_ids")),
        regimes=_tuple_text(state.get("regimes")),
        closed_count=closed_count,
        net_expectancy_per_trade=net_expectancy,
        net_win_rate=win_rate,
        sample_ok=sample_ok,
        eligible_for_promotion=eligible_for_promotion,
        requires_review=requires_review,
        promotion_ready=promotion_ready,
        metadata={
            "source_reason_code": _text(state.get("reason_code")),
            "evidence_only": True,
        },
    )


def _lifecycle_report_valid(payload: Mapping[str, Any]) -> bool:
    if payload.get("read_only") is not True:
        return False
    if payload.get("append") is not False:
        return False
    if str(payload.get("status") or "").strip() != STRATEGY_LIFECYCLE_REDUCED:
        return False
    if not isinstance(payload.get("states"), list):
        return False
    return True


def _blocked_report(
    *,
    reason_code: str,
    reasons: tuple[str, ...],
    policy: StrategyPromotionPolicy,
    lifecycle_report_valid: bool = False,
    metadata: dict[str, Any] | None = None,
) -> StrategyPromotionGateReport:
    return StrategyPromotionGateReport(
        schema_version=STRATEGY_PROMOTION_GATE_SCHEMA_VERSION,
        source=STRATEGY_PROMOTION_GATE_SOURCE,
        status=STRATEGY_PROMOTION_GATE_BLOCKED,
        reason_code=reason_code,
        reasons=_dedupe(reasons),
        lifecycle_report_valid=lifecycle_report_valid,
        family_count=0,
        promotion_candidate_count=0,
        blocked_count=0,
        review_required_count=0,
        policy=policy,
        decisions=(),
        metadata=dict(metadata or {}),
    )


def _policy(*, promotion_min_closed_trades: Any, promotion_min_win_rate: Any) -> StrategyPromotionPolicy | None:
    min_closed = _int(promotion_min_closed_trades, default=-1)
    min_win_rate = _float(promotion_min_win_rate, default=-1.0)
    if min_closed <= 0:
        return None
    if min_win_rate < 0.0 or min_win_rate > 1.0:
        return None
    return StrategyPromotionPolicy(
        promotion_min_closed_trades=min_closed,
        promotion_min_win_rate=min_win_rate,
    )


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _tuple_text(value: Any) -> tuple[str, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return _dedupe(value)
    text = _text(value)
    return (text,) if text else ()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: Any, *, default: float = 0.0) -> float:
    try:
        return round(float(value or 0.0), 10)
    except (TypeError, ValueError):
        return default


def _dedupe(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in values if str(value or "").strip()}))


def _mark_non_action(payload: dict[str, Any]) -> None:
    payload[_ACTION_KEY] = False
    payload[_BROKER_KEY] = False
    payload["live_order_action"] = False
    payload["broker_order_action"] = False


__all__ = [
    "ACTIVE_ELIGIBLE_PROMOTION_CANDIDATE_REASON",
    "DEFAULT_PROMOTION_MIN_CLOSED_TRADES",
    "DEFAULT_PROMOTION_MIN_WIN_RATE",
    "INVALID_LIFECYCLE_REPORT_REASON",
    "INVALID_PROMOTION_POLICY_REASON",
    "LIFECYCLE_NOT_ACTIVE_ELIGIBLE_REASON",
    "LOW_PROMOTION_SAMPLE_REASON",
    "LOW_WIN_RATE_REASON",
    "NO_LIFECYCLE_STATES_REASON",
    "NON_POSITIVE_EXPECTANCY_REASON",
    "NOT_ELIGIBLE_FOR_PROMOTION_REASON",
    "PROMOTION_DECISION_BLOCKED",
    "PROMOTION_DECISION_CANDIDATE",
    "PROMOTION_DECISION_REVIEW",
    "PROMOTION_REVIEW_REQUIRED_REASON",
    "STRATEGY_PROMOTION_GATE_BLOCKED",
    "STRATEGY_PROMOTION_GATE_EVALUATED",
    "STRATEGY_PROMOTION_GATE_SCHEMA_VERSION",
    "STRATEGY_PROMOTION_GATE_SOURCE",
    "StrategyPromotionGateDecision",
    "StrategyPromotionGateReport",
    "StrategyPromotionPolicy",
    "build_strategy_promotion_gate_report",
]
