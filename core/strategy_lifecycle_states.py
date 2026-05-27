"""Read-only strategy lifecycle state model for EDGE-88.

This module derives deterministic lifecycle states from the EDGE-87 strategy-family
keep/watch/kill evidence. It is intentionally evidence-only: it does not promote,
suspend, retire, execute, route orders, call brokers, wire runtime behavior, or
change dashboards.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

STRATEGY_LIFECYCLE_SCHEMA_VERSION = 1
STRATEGY_LIFECYCLE_SOURCE = "strategy_lifecycle_states_v1"

STRATEGY_LIFECYCLE_REDUCED = "STRATEGY_LIFECYCLE_REDUCED"
STRATEGY_LIFECYCLE_BLOCKED = "STRATEGY_LIFECYCLE_BLOCKED"

LIFECYCLE_STATE_CANDIDATE = "CANDIDATE"
LIFECYCLE_STATE_ACTIVE_ELIGIBLE = "ACTIVE_ELIGIBLE"
LIFECYCLE_STATE_WATCHLIST = "WATCHLIST"
LIFECYCLE_STATE_SUSPEND_CANDIDATE = "SUSPEND_CANDIDATE"
LIFECYCLE_STATE_RETIRED_CANDIDATE = "RETIRED_CANDIDATE"

FAMILY_RECOMMENDATION_KEEP = "KEEP"
FAMILY_RECOMMENDATION_WATCH = "WATCH"
FAMILY_RECOMMENDATION_KILL = "KILL"

INVALID_FAMILY_REPORT_REASON = "invalid_strategy_family_report"
NO_FAMILY_RECOMMENDATIONS_REASON = "no_strategy_family_recommendations"
INVALID_LIFECYCLE_POLICY_REASON = "invalid_strategy_lifecycle_policy"
KEEP_FAMILY_ACTIVE_ELIGIBLE_REASON = "keep_family_active_eligible"
WATCH_FAMILY_WATCHLIST_REASON = "watch_family_watchlist"
KILL_FAMILY_SUSPEND_CANDIDATE_REASON = "kill_family_suspend_candidate"
KILL_FAMILY_RETIRED_CANDIDATE_REASON = "kill_family_retired_candidate"
UNKNOWN_RECOMMENDATION_WATCHLIST_REASON = "unknown_family_recommendation_watchlist"
LOW_SAMPLE_CANDIDATE_REASON = "low_sample_lifecycle_candidate"

DEFAULT_RETIRE_MIN_CLOSED_TRADES = 30
UNKNOWN_FAMILY = "UNKNOWN_FAMILY"

_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class StrategyLifecyclePolicy:
    """Policy thresholds for read-only lifecycle state derivation."""

    retire_min_closed_trades: int = DEFAULT_RETIRE_MIN_CLOSED_TRADES

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
            "retire_min_closed_trades": self.retire_min_closed_trades,
            "read_only": True,
            "append": False,
        }
        _mark_non_action(payload)
        return payload


@dataclass(frozen=True)
class StrategyLifecycleState:
    """Read-only lifecycle state for one strategy family."""

    strategy_family: str
    lifecycle_state: str
    reason_code: str
    reasons: tuple[str, ...]
    source_recommendation: str
    strategy_ids: tuple[str, ...]
    regimes: tuple[str, ...]
    closed_count: int
    net_expectancy_per_trade: float
    net_win_rate: float
    sample_ok: bool
    eligible_for_promotion: bool = False
    requires_review: bool = True
    promotion_applied: bool = False
    suspension_applied: bool = False
    retirement_applied: bool = False
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
            "lifecycle_state": self.lifecycle_state,
            "reason_code": self.reason_code,
            "reasons": list(self.reasons),
            "source_recommendation": self.source_recommendation,
            "strategy_ids": list(self.strategy_ids),
            "regimes": list(self.regimes),
            "closed_count": self.closed_count,
            "net_expectancy_per_trade": self.net_expectancy_per_trade,
            "net_win_rate": self.net_win_rate,
            "sample_ok": self.sample_ok,
            "eligible_for_promotion": self.eligible_for_promotion,
            "requires_review": self.requires_review,
            "promotion_applied": self.promotion_applied,
            "suspension_applied": self.suspension_applied,
            "retirement_applied": self.retirement_applied,
            "read_only": self.read_only,
            "append": self.append,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload


@dataclass(frozen=True)
class StrategyLifecycleReport:
    """Read-only lifecycle-state report derived from strategy-family evidence."""

    schema_version: int
    source: str
    status: str
    reason_code: str
    reasons: tuple[str, ...]
    family_report_valid: bool
    family_count: int
    active_eligible_count: int
    watchlist_count: int
    suspend_candidate_count: int
    retired_candidate_count: int
    candidate_count: int
    policy: StrategyLifecyclePolicy
    states: tuple[StrategyLifecycleState, ...]
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
            "family_report_valid": self.family_report_valid,
            "family_count": self.family_count,
            "active_eligible_count": self.active_eligible_count,
            "watchlist_count": self.watchlist_count,
            "suspend_candidate_count": self.suspend_candidate_count,
            "retired_candidate_count": self.retired_candidate_count,
            "candidate_count": self.candidate_count,
            "policy": self.policy.to_payload(),
            "states": [state.to_payload() for state in self.states],
            "read_only": self.read_only,
            "append": self.append,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def build_strategy_lifecycle_report(
    family_report: Mapping[str, Any] | Any,
    *,
    retire_min_closed_trades: Any = DEFAULT_RETIRE_MIN_CLOSED_TRADES,
) -> StrategyLifecycleReport:
    """Derive read-only lifecycle states from EDGE-87 family recommendations."""

    policy = _policy(retire_min_closed_trades=retire_min_closed_trades)
    if policy is None:
        return _blocked_report(
            reason_code=INVALID_LIFECYCLE_POLICY_REASON,
            reasons=(INVALID_LIFECYCLE_POLICY_REASON,),
            policy=StrategyLifecyclePolicy(),
            metadata={"blocked_before_lifecycle_evaluation": True},
        )

    payload = _payload(family_report)
    if not _family_report_valid(payload):
        return _blocked_report(
            reason_code=INVALID_FAMILY_REPORT_REASON,
            reasons=(INVALID_FAMILY_REPORT_REASON,),
            policy=policy,
            metadata={"blocked_before_lifecycle_evaluation": True},
        )

    recommendations = tuple(
        dict(item)
        for item in payload.get("recommendations") or []
        if isinstance(item, Mapping)
    )
    if not recommendations:
        return _blocked_report(
            reason_code=NO_FAMILY_RECOMMENDATIONS_REASON,
            reasons=(NO_FAMILY_RECOMMENDATIONS_REASON,),
            policy=policy,
            family_report_valid=True,
            metadata={"derived_from": str(payload.get("source") or "strategy_family_report")},
        )

    states = tuple(_state_from_recommendation(item, policy) for item in recommendations)
    report_reasons = _dedupe(state.reason_code for state in states)
    return StrategyLifecycleReport(
        schema_version=STRATEGY_LIFECYCLE_SCHEMA_VERSION,
        source=STRATEGY_LIFECYCLE_SOURCE,
        status=STRATEGY_LIFECYCLE_REDUCED,
        reason_code="ok",
        reasons=report_reasons,
        family_report_valid=True,
        family_count=len(states),
        active_eligible_count=sum(1 for state in states if state.lifecycle_state == LIFECYCLE_STATE_ACTIVE_ELIGIBLE),
        watchlist_count=sum(1 for state in states if state.lifecycle_state == LIFECYCLE_STATE_WATCHLIST),
        suspend_candidate_count=sum(1 for state in states if state.lifecycle_state == LIFECYCLE_STATE_SUSPEND_CANDIDATE),
        retired_candidate_count=sum(1 for state in states if state.lifecycle_state == LIFECYCLE_STATE_RETIRED_CANDIDATE),
        candidate_count=sum(1 for state in states if state.lifecycle_state == LIFECYCLE_STATE_CANDIDATE),
        policy=policy,
        states=states,
        metadata={
            "derived_from": str(payload.get("source") or "strategy_family_report"),
            "evidence_only": True,
            "does_not_change_strategy_state": True,
            "does_not_promote_or_suspend_or_retire": True,
        },
    )


def _state_from_recommendation(
    recommendation: Mapping[str, Any],
    policy: StrategyLifecyclePolicy,
) -> StrategyLifecycleState:
    strategy_family = _text(recommendation.get("strategy_family")) or UNKNOWN_FAMILY
    source_recommendation = _text(recommendation.get("recommendation")).upper()
    closed_count = _int(recommendation.get("closed_count"))
    sample_ok = bool(recommendation.get("sample_ok"))
    source_reasons = _tuple_text(recommendation.get("reasons"))

    if not sample_ok:
        lifecycle_state = LIFECYCLE_STATE_CANDIDATE
        reason_code = LOW_SAMPLE_CANDIDATE_REASON
        requires_review = True
        eligible_for_promotion = False
    elif source_recommendation == FAMILY_RECOMMENDATION_KEEP:
        lifecycle_state = LIFECYCLE_STATE_ACTIVE_ELIGIBLE
        reason_code = KEEP_FAMILY_ACTIVE_ELIGIBLE_REASON
        requires_review = False
        eligible_for_promotion = True
    elif source_recommendation == FAMILY_RECOMMENDATION_WATCH:
        lifecycle_state = LIFECYCLE_STATE_WATCHLIST
        reason_code = WATCH_FAMILY_WATCHLIST_REASON
        requires_review = True
        eligible_for_promotion = False
    elif source_recommendation == FAMILY_RECOMMENDATION_KILL:
        if closed_count >= policy.retire_min_closed_trades:
            lifecycle_state = LIFECYCLE_STATE_RETIRED_CANDIDATE
            reason_code = KILL_FAMILY_RETIRED_CANDIDATE_REASON
        else:
            lifecycle_state = LIFECYCLE_STATE_SUSPEND_CANDIDATE
            reason_code = KILL_FAMILY_SUSPEND_CANDIDATE_REASON
        requires_review = True
        eligible_for_promotion = False
    else:
        lifecycle_state = LIFECYCLE_STATE_WATCHLIST
        reason_code = UNKNOWN_RECOMMENDATION_WATCHLIST_REASON
        requires_review = True
        eligible_for_promotion = False

    return StrategyLifecycleState(
        strategy_family=strategy_family,
        lifecycle_state=lifecycle_state,
        reason_code=reason_code,
        reasons=_dedupe((reason_code, *source_reasons)),
        source_recommendation=source_recommendation or "UNKNOWN",
        strategy_ids=_tuple_text(recommendation.get("strategy_ids")),
        regimes=_tuple_text(recommendation.get("regimes")),
        closed_count=closed_count,
        net_expectancy_per_trade=_float(recommendation.get("net_expectancy_per_trade")),
        net_win_rate=_float(recommendation.get("net_win_rate")),
        sample_ok=sample_ok,
        eligible_for_promotion=eligible_for_promotion,
        requires_review=requires_review,
        metadata={
            "source_reason_code": _text(recommendation.get("reason_code")),
            "evidence_only": True,
        },
    )


def _family_report_valid(payload: Mapping[str, Any]) -> bool:
    if payload.get("read_only") is not True:
        return False
    if payload.get("append") is not False:
        return False
    if str(payload.get("status") or "").strip() != "STRATEGY_FAMILY_REPORT_REDUCED":
        return False
    if not isinstance(payload.get("recommendations"), list):
        return False
    return True


def _blocked_report(
    *,
    reason_code: str,
    reasons: tuple[str, ...],
    policy: StrategyLifecyclePolicy,
    family_report_valid: bool = False,
    metadata: dict[str, Any] | None = None,
) -> StrategyLifecycleReport:
    return StrategyLifecycleReport(
        schema_version=STRATEGY_LIFECYCLE_SCHEMA_VERSION,
        source=STRATEGY_LIFECYCLE_SOURCE,
        status=STRATEGY_LIFECYCLE_BLOCKED,
        reason_code=reason_code,
        reasons=_dedupe(reasons),
        family_report_valid=family_report_valid,
        family_count=0,
        active_eligible_count=0,
        watchlist_count=0,
        suspend_candidate_count=0,
        retired_candidate_count=0,
        candidate_count=0,
        policy=policy,
        states=(),
        metadata=dict(metadata or {}),
    )


def _policy(*, retire_min_closed_trades: Any) -> StrategyLifecyclePolicy | None:
    retire_min = _int(retire_min_closed_trades, default=-1)
    if retire_min <= 0:
        return None
    return StrategyLifecyclePolicy(retire_min_closed_trades=retire_min)


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
    "DEFAULT_RETIRE_MIN_CLOSED_TRADES",
    "INVALID_FAMILY_REPORT_REASON",
    "INVALID_LIFECYCLE_POLICY_REASON",
    "KEEP_FAMILY_ACTIVE_ELIGIBLE_REASON",
    "KILL_FAMILY_RETIRED_CANDIDATE_REASON",
    "KILL_FAMILY_SUSPEND_CANDIDATE_REASON",
    "LIFECYCLE_STATE_ACTIVE_ELIGIBLE",
    "LIFECYCLE_STATE_CANDIDATE",
    "LIFECYCLE_STATE_RETIRED_CANDIDATE",
    "LIFECYCLE_STATE_SUSPEND_CANDIDATE",
    "LIFECYCLE_STATE_WATCHLIST",
    "LOW_SAMPLE_CANDIDATE_REASON",
    "NO_FAMILY_RECOMMENDATIONS_REASON",
    "STRATEGY_LIFECYCLE_BLOCKED",
    "STRATEGY_LIFECYCLE_REDUCED",
    "STRATEGY_LIFECYCLE_SCHEMA_VERSION",
    "STRATEGY_LIFECYCLE_SOURCE",
    "StrategyLifecyclePolicy",
    "StrategyLifecycleReport",
    "StrategyLifecycleState",
    "UNKNOWN_RECOMMENDATION_WATCHLIST_REASON",
    "WATCH_FAMILY_WATCHLIST_REASON",
    "build_strategy_lifecycle_report",
]
