"""Read-only strategy suspension and retirement rule evidence for EDGE-90.

This module consumes EDGE-88 lifecycle-state evidence and emits deterministic
suspension/retirement rule decisions. It never mutates lifecycle state, suspends,
retires, promotes, executes trades, routes orders, calls brokers, wires runtime
behavior, or changes UI surfaces.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from core.strategy_lifecycle_states import (
    LIFECYCLE_STATE_RETIRED_CANDIDATE,
    LIFECYCLE_STATE_SUSPEND_CANDIDATE,
    STRATEGY_LIFECYCLE_REDUCED,
)

STRATEGY_SUSPENSION_RETIREMENT_SCHEMA_VERSION = 1
STRATEGY_SUSPENSION_RETIREMENT_SOURCE = "strategy_suspension_retirement_rules_v1"

STRATEGY_SUSPENSION_RETIREMENT_EVALUATED = "STRATEGY_SUSPENSION_RETIREMENT_EVALUATED"
STRATEGY_SUSPENSION_RETIREMENT_BLOCKED = "STRATEGY_SUSPENSION_RETIREMENT_BLOCKED"

RULE_DECISION_SUSPENSION_CANDIDATE = "SUSPENSION_CANDIDATE"
RULE_DECISION_RETIREMENT_CANDIDATE = "RETIREMENT_CANDIDATE"
RULE_DECISION_NO_ACTION = "NO_ACTION"
RULE_DECISION_REVIEW_REQUIRED = "REVIEW_REQUIRED"

INVALID_LIFECYCLE_REPORT_REASON = "invalid_strategy_lifecycle_report"
NO_LIFECYCLE_STATES_REASON = "no_strategy_lifecycle_states"
INVALID_RULE_POLICY_REASON = "invalid_suspension_retirement_policy"
SUSPEND_CANDIDATE_RULE_READY_REASON = "suspend_candidate_rule_ready"
RETIRE_CANDIDATE_RULE_READY_REASON = "retire_candidate_rule_ready"
LIFECYCLE_NOT_SUSPEND_OR_RETIRE_CANDIDATE_REASON = "lifecycle_not_suspend_or_retire_candidate"
LOW_SUSPENSION_SAMPLE_REASON = "low_suspension_sample"
LOW_RETIREMENT_SAMPLE_REASON = "low_retirement_sample"
NON_NEGATIVE_EXPECTANCY_REVIEW_REASON = "non_negative_expectancy_requires_review"
REVIEW_REQUIRED_REASON = "suspension_retirement_review_required"
UNKNOWN_FAMILY = "UNKNOWN_FAMILY"

DEFAULT_SUSPENSION_MIN_CLOSED_TRADES = 10
DEFAULT_RETIREMENT_MIN_CLOSED_TRADES = 30
_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class StrategySuspensionRetirementPolicy:
    """Policy thresholds for read-only suspension/retirement rule evidence."""

    suspension_min_closed_trades: int = DEFAULT_SUSPENSION_MIN_CLOSED_TRADES
    retirement_min_closed_trades: int = DEFAULT_RETIREMENT_MIN_CLOSED_TRADES

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
            "suspension_min_closed_trades": self.suspension_min_closed_trades,
            "retirement_min_closed_trades": self.retirement_min_closed_trades,
            "read_only": True,
            "append": False,
        }
        _mark_non_action(payload)
        return payload


@dataclass(frozen=True)
class StrategySuspensionRetirementDecision:
    """Read-only suspension/retirement decision for one strategy family."""

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
    requires_review: bool
    suspension_ready: bool = False
    retirement_ready: bool = False
    suspension_applied: bool = False
    retirement_applied: bool = False
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
            "requires_review": self.requires_review,
            "suspension_ready": self.suspension_ready,
            "retirement_ready": self.retirement_ready,
            "suspension_applied": self.suspension_applied,
            "retirement_applied": self.retirement_applied,
            "lifecycle_state_mutated": self.lifecycle_state_mutated,
            "read_only": self.read_only,
            "append": self.append,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload


@dataclass(frozen=True)
class StrategySuspensionRetirementReport:
    """Read-only suspension/retirement rule report from lifecycle evidence."""

    schema_version: int
    source: str
    status: str
    reason_code: str
    reasons: tuple[str, ...]
    lifecycle_report_valid: bool
    family_count: int
    suspension_candidate_count: int
    retirement_candidate_count: int
    no_action_count: int
    review_required_count: int
    policy: StrategySuspensionRetirementPolicy
    decisions: tuple[StrategySuspensionRetirementDecision, ...]
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
            "suspension_candidate_count": self.suspension_candidate_count,
            "retirement_candidate_count": self.retirement_candidate_count,
            "no_action_count": self.no_action_count,
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


def build_strategy_suspension_retirement_report(
    lifecycle_report: Mapping[str, Any] | Any,
    *,
    suspension_min_closed_trades: Any = DEFAULT_SUSPENSION_MIN_CLOSED_TRADES,
    retirement_min_closed_trades: Any = DEFAULT_RETIREMENT_MIN_CLOSED_TRADES,
) -> StrategySuspensionRetirementReport:
    """Evaluate read-only suspension/retirement rule readiness."""

    policy = _policy(
        suspension_min_closed_trades=suspension_min_closed_trades,
        retirement_min_closed_trades=retirement_min_closed_trades,
    )
    if policy is None:
        return _blocked_report(
            reason_code=INVALID_RULE_POLICY_REASON,
            reasons=(INVALID_RULE_POLICY_REASON,),
            policy=StrategySuspensionRetirementPolicy(),
            metadata={"blocked_before_rule_evaluation": True},
        )

    payload = _payload(lifecycle_report)
    if not _lifecycle_report_valid(payload):
        return _blocked_report(
            reason_code=INVALID_LIFECYCLE_REPORT_REASON,
            reasons=(INVALID_LIFECYCLE_REPORT_REASON,),
            policy=policy,
            metadata={"blocked_before_rule_evaluation": True},
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
    return StrategySuspensionRetirementReport(
        schema_version=STRATEGY_SUSPENSION_RETIREMENT_SCHEMA_VERSION,
        source=STRATEGY_SUSPENSION_RETIREMENT_SOURCE,
        status=STRATEGY_SUSPENSION_RETIREMENT_EVALUATED,
        reason_code="ok",
        reasons=report_reasons,
        lifecycle_report_valid=True,
        family_count=len(decisions),
        suspension_candidate_count=sum(1 for item in decisions if item.decision == RULE_DECISION_SUSPENSION_CANDIDATE),
        retirement_candidate_count=sum(1 for item in decisions if item.decision == RULE_DECISION_RETIREMENT_CANDIDATE),
        no_action_count=sum(1 for item in decisions if item.decision == RULE_DECISION_NO_ACTION),
        review_required_count=sum(1 for item in decisions if item.decision == RULE_DECISION_REVIEW_REQUIRED),
        policy=policy,
        decisions=decisions,
        metadata={
            "derived_from": str(payload.get("source") or "strategy_lifecycle_states"),
            "evidence_only": True,
            "does_not_change_strategy_state": True,
            "does_not_apply_suspension_or_retirement": True,
        },
    )


def _decision_from_state(
    state: Mapping[str, Any],
    policy: StrategySuspensionRetirementPolicy,
) -> StrategySuspensionRetirementDecision:
    lifecycle_state = _text(state.get("lifecycle_state"))
    closed_count = _int(state.get("closed_count"))
    net_expectancy = _float(state.get("net_expectancy_per_trade"))
    win_rate = _float(state.get("net_win_rate"))
    sample_ok = bool(state.get("sample_ok"))
    source_requires_review = bool(state.get("requires_review"))

    reasons: list[str] = []
    if lifecycle_state == LIFECYCLE_STATE_SUSPEND_CANDIDATE:
        if not sample_ok or closed_count < policy.suspension_min_closed_trades:
            reasons.append(LOW_SUSPENSION_SAMPLE_REASON)
        if net_expectancy >= 0.0:
            reasons.append(NON_NEGATIVE_EXPECTANCY_REVIEW_REASON)
        if reasons:
            decision = RULE_DECISION_REVIEW_REQUIRED
            reason_code = reasons[0]
            suspension_ready = False
            retirement_ready = False
            requires_review = True
        else:
            decision = RULE_DECISION_SUSPENSION_CANDIDATE
            reason_code = SUSPEND_CANDIDATE_RULE_READY_REASON
            suspension_ready = True
            retirement_ready = False
            requires_review = source_requires_review
    elif lifecycle_state == LIFECYCLE_STATE_RETIRED_CANDIDATE:
        if not sample_ok or closed_count < policy.retirement_min_closed_trades:
            reasons.append(LOW_RETIREMENT_SAMPLE_REASON)
        if net_expectancy >= 0.0:
            reasons.append(NON_NEGATIVE_EXPECTANCY_REVIEW_REASON)
        if reasons:
            decision = RULE_DECISION_REVIEW_REQUIRED
            reason_code = reasons[0]
            suspension_ready = False
            retirement_ready = False
            requires_review = True
        else:
            decision = RULE_DECISION_RETIREMENT_CANDIDATE
            reason_code = RETIRE_CANDIDATE_RULE_READY_REASON
            suspension_ready = False
            retirement_ready = True
            requires_review = source_requires_review
    else:
        decision = RULE_DECISION_NO_ACTION
        reason_code = LIFECYCLE_NOT_SUSPEND_OR_RETIRE_CANDIDATE_REASON
        reasons.append(reason_code)
        suspension_ready = False
        retirement_ready = False
        requires_review = False

    return StrategySuspensionRetirementDecision(
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
        requires_review=requires_review,
        suspension_ready=suspension_ready,
        retirement_ready=retirement_ready,
        metadata={
            "source_reason_code": _text(state.get("reason_code")),
            "source_requires_review": source_requires_review,
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
    policy: StrategySuspensionRetirementPolicy,
    lifecycle_report_valid: bool = False,
    metadata: dict[str, Any] | None = None,
) -> StrategySuspensionRetirementReport:
    return StrategySuspensionRetirementReport(
        schema_version=STRATEGY_SUSPENSION_RETIREMENT_SCHEMA_VERSION,
        source=STRATEGY_SUSPENSION_RETIREMENT_SOURCE,
        status=STRATEGY_SUSPENSION_RETIREMENT_BLOCKED,
        reason_code=reason_code,
        reasons=_dedupe(reasons),
        lifecycle_report_valid=lifecycle_report_valid,
        family_count=0,
        suspension_candidate_count=0,
        retirement_candidate_count=0,
        no_action_count=0,
        review_required_count=0,
        policy=policy,
        decisions=(),
        metadata=dict(metadata or {}),
    )


def _policy(
    *,
    suspension_min_closed_trades: Any,
    retirement_min_closed_trades: Any,
) -> StrategySuspensionRetirementPolicy | None:
    suspension_min = _int(suspension_min_closed_trades, default=-1)
    retirement_min = _int(retirement_min_closed_trades, default=-1)
    if suspension_min <= 0 or retirement_min <= 0:
        return None
    if retirement_min < suspension_min:
        return None
    return StrategySuspensionRetirementPolicy(
        suspension_min_closed_trades=suspension_min,
        retirement_min_closed_trades=retirement_min,
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
    "DEFAULT_RETIREMENT_MIN_CLOSED_TRADES",
    "DEFAULT_SUSPENSION_MIN_CLOSED_TRADES",
    "INVALID_LIFECYCLE_REPORT_REASON",
    "INVALID_RULE_POLICY_REASON",
    "LIFECYCLE_NOT_SUSPEND_OR_RETIRE_CANDIDATE_REASON",
    "LOW_RETIREMENT_SAMPLE_REASON",
    "LOW_SUSPENSION_SAMPLE_REASON",
    "NO_LIFECYCLE_STATES_REASON",
    "NON_NEGATIVE_EXPECTANCY_REVIEW_REASON",
    "RETIRE_CANDIDATE_RULE_READY_REASON",
    "RULE_DECISION_NO_ACTION",
    "RULE_DECISION_RETIREMENT_CANDIDATE",
    "RULE_DECISION_REVIEW_REQUIRED",
    "RULE_DECISION_SUSPENSION_CANDIDATE",
    "STRATEGY_SUSPENSION_RETIREMENT_BLOCKED",
    "STRATEGY_SUSPENSION_RETIREMENT_EVALUATED",
    "STRATEGY_SUSPENSION_RETIREMENT_SCHEMA_VERSION",
    "STRATEGY_SUSPENSION_RETIREMENT_SOURCE",
    "SUSPEND_CANDIDATE_RULE_READY_REASON",
    "StrategySuspensionRetirementDecision",
    "StrategySuspensionRetirementPolicy",
    "StrategySuspensionRetirementReport",
    "build_strategy_suspension_retirement_report",
]
