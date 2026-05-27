"""Read-only strategy-family report for EDGE-87.

This module consumes EDGE-86 net cost truth and derives family-level evidence
for keep/watch/kill reporting. It does not mutate strategy state, update runtime
behavior, write to brokers, append paper events, or change dashboards.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

STRATEGY_FAMILY_REPORT_SCHEMA_VERSION = 1
STRATEGY_FAMILY_REPORT_SOURCE = "strategy_family_kill_keep_report_v1"

STRATEGY_FAMILY_REPORT_REDUCED = "STRATEGY_FAMILY_REPORT_REDUCED"
STRATEGY_FAMILY_REPORT_BLOCKED = "STRATEGY_FAMILY_REPORT_BLOCKED"

FAMILY_KEEP = "KEEP"
FAMILY_WATCH = "WATCH"
FAMILY_KILL = "KILL"

INVALID_COST_TRUTH_REPORT_REASON = "invalid_slippage_cost_truth_report"
NO_NET_COST_BUCKETS_REASON = "no_net_cost_buckets"
INSUFFICIENT_FAMILY_SAMPLE_REASON = "insufficient_family_sample"
NEGATIVE_NET_EXPECTANCY_REASON = "negative_net_expectancy"
POSITIVE_NET_EXPECTANCY_REASON = "positive_net_expectancy"
WEAK_NET_WIN_RATE_REASON = "weak_net_win_rate"
MIXED_OR_BORDERLINE_EVIDENCE_REASON = "mixed_or_borderline_evidence"

DEFAULT_MIN_CLOSED_TRADES = 1
DEFAULT_KEEP_MIN_NET_EXPECTANCY = 0.0
DEFAULT_KEEP_MIN_WIN_RATE = 0.5
DEFAULT_KILL_MAX_NET_EXPECTANCY = 0.0
UNKNOWN_FAMILY = "UNKNOWN_FAMILY"
UNKNOWN_REGIME = "UNKNOWN"

_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"
_VERSION_SUFFIX_RE = re.compile(r"([_.-])v\d+$", re.IGNORECASE)


@dataclass(frozen=True)
class StrategyFamilyPolicy:
    """Thresholds used to derive family evidence from net cost truth."""

    min_closed_trades: int = DEFAULT_MIN_CLOSED_TRADES
    keep_min_net_expectancy: float = DEFAULT_KEEP_MIN_NET_EXPECTANCY
    keep_min_win_rate: float = DEFAULT_KEEP_MIN_WIN_RATE
    kill_max_net_expectancy: float = DEFAULT_KILL_MAX_NET_EXPECTANCY

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
            "min_closed_trades": self.min_closed_trades,
            "keep_min_net_expectancy": self.keep_min_net_expectancy,
            "keep_min_win_rate": self.keep_min_win_rate,
            "kill_max_net_expectancy": self.kill_max_net_expectancy,
            "read_only": True,
            "append": False,
        }
        _mark_non_action(payload)
        return payload


@dataclass(frozen=True)
class StrategyFamilyRecommendation:
    """Evidence-only recommendation for one strategy family."""

    strategy_family: str
    recommendation: str
    reason_code: str
    reasons: tuple[str, ...]
    strategy_ids: tuple[str, ...]
    regimes: tuple[str, ...]
    closed_count: int
    net_win_count: int
    net_loss_count: int
    net_flat_count: int
    total_gross_pnl: float
    total_cost: float
    total_net_pnl: float
    average_net_pnl: float
    net_win_rate: float
    net_loss_rate: float
    net_expectancy_per_trade: float
    cost_drag_per_trade: float
    sample_ok: bool
    buckets: tuple[dict[str, Any], ...] = ()
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
            "recommendation": self.recommendation,
            "reason_code": self.reason_code,
            "reasons": list(self.reasons),
            "strategy_ids": list(self.strategy_ids),
            "regimes": list(self.regimes),
            "closed_count": self.closed_count,
            "net_win_count": self.net_win_count,
            "net_loss_count": self.net_loss_count,
            "net_flat_count": self.net_flat_count,
            "total_gross_pnl": self.total_gross_pnl,
            "total_cost": self.total_cost,
            "total_net_pnl": self.total_net_pnl,
            "average_net_pnl": self.average_net_pnl,
            "net_win_rate": self.net_win_rate,
            "net_loss_rate": self.net_loss_rate,
            "net_expectancy_per_trade": self.net_expectancy_per_trade,
            "cost_drag_per_trade": self.cost_drag_per_trade,
            "sample_ok": self.sample_ok,
            "buckets": [dict(bucket) for bucket in self.buckets],
            "metadata": dict(self.metadata),
            "read_only": True,
            "append": False,
        }
        _mark_non_action(payload)
        return payload


@dataclass(frozen=True)
class StrategyFamilyReport:
    """Read-only family report derived from EDGE-86 net cost truth."""

    schema_version: int
    source: str
    status: str
    reason_code: str
    reasons: tuple[str, ...]
    cost_truth_report_valid: bool
    family_count: int
    keep_count: int
    watch_count: int
    kill_count: int
    policy: StrategyFamilyPolicy
    recommendations: tuple[StrategyFamilyRecommendation, ...]
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
            "cost_truth_report_valid": self.cost_truth_report_valid,
            "family_count": self.family_count,
            "keep_count": self.keep_count,
            "watch_count": self.watch_count,
            "kill_count": self.kill_count,
            "policy": self.policy.to_payload(),
            "recommendations": [item.to_payload() for item in self.recommendations],
            "read_only": self.read_only,
            "append": self.append,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def build_strategy_family_report(
    cost_truth_report: Mapping[str, Any] | Any,
    *,
    min_closed_trades: Any = DEFAULT_MIN_CLOSED_TRADES,
    keep_min_net_expectancy: Any = DEFAULT_KEEP_MIN_NET_EXPECTANCY,
    keep_min_win_rate: Any = DEFAULT_KEEP_MIN_WIN_RATE,
    kill_max_net_expectancy: Any = DEFAULT_KILL_MAX_NET_EXPECTANCY,
) -> StrategyFamilyReport:
    """Build a read-only strategy-family report from EDGE-86 net cost truth."""

    policy = _policy(
        min_closed_trades=min_closed_trades,
        keep_min_net_expectancy=keep_min_net_expectancy,
        keep_min_win_rate=keep_min_win_rate,
        kill_max_net_expectancy=kill_max_net_expectancy,
    )
    payload = _payload(cost_truth_report)
    if not _cost_truth_report_valid(payload):
        return _blocked_report(
            reason_code=INVALID_COST_TRUTH_REPORT_REASON,
            reasons=(INVALID_COST_TRUTH_REPORT_REASON,),
            policy=policy,
        )

    buckets = [_payload(bucket) for bucket in payload.get("buckets") or [] if isinstance(_payload(bucket), Mapping)]
    if not buckets:
        return _blocked_report(
            reason_code=NO_NET_COST_BUCKETS_REASON,
            reasons=(NO_NET_COST_BUCKETS_REASON,),
            cost_truth_report_valid=True,
            policy=policy,
            metadata={"derived_from": str(payload.get("source") or "paper_slippage_cost_truth")},
        )

    recommendations = tuple(_recommendation_from_group(family, items, policy) for family, items in _group_buckets(buckets))
    report_reasons = _dedupe(reason for item in recommendations for reason in item.reasons)
    return StrategyFamilyReport(
        schema_version=STRATEGY_FAMILY_REPORT_SCHEMA_VERSION,
        source=STRATEGY_FAMILY_REPORT_SOURCE,
        status=STRATEGY_FAMILY_REPORT_REDUCED,
        reason_code="ok",
        reasons=report_reasons,
        cost_truth_report_valid=True,
        family_count=len(recommendations),
        keep_count=sum(1 for item in recommendations if item.recommendation == FAMILY_KEEP),
        watch_count=sum(1 for item in recommendations if item.recommendation == FAMILY_WATCH),
        kill_count=sum(1 for item in recommendations if item.recommendation == FAMILY_KILL),
        policy=policy,
        recommendations=recommendations,
        metadata={
            "derived_from": str(payload.get("source") or "paper_slippage_cost_truth"),
            "evidence_only": True,
            "does_not_change_strategy_state": True,
            "does_not_promote_or_suspend": True,
        },
    )


def _recommendation_from_group(
    family: str,
    buckets: tuple[dict[str, Any], ...],
    policy: StrategyFamilyPolicy,
) -> StrategyFamilyRecommendation:
    closed_count = sum(_int(bucket.get("closed_count")) for bucket in buckets)
    net_win_count = sum(_int(bucket.get("net_win_count")) for bucket in buckets)
    net_loss_count = sum(_int(bucket.get("net_loss_count")) for bucket in buckets)
    net_flat_count = sum(_int(bucket.get("net_flat_count")) for bucket in buckets)
    total_gross = _round(sum(_float(bucket.get("total_gross_pnl")) for bucket in buckets))
    total_cost = _round(sum(_float(bucket.get("total_cost")) for bucket in buckets))
    total_net = _round(sum(_float(bucket.get("total_net_pnl")) for bucket in buckets))
    average_net = _round(total_net / closed_count) if closed_count else 0.0
    net_win_rate = _round(net_win_count / closed_count) if closed_count else 0.0
    net_loss_rate = _round(net_loss_count / closed_count) if closed_count else 0.0
    cost_drag = _round(total_cost / closed_count) if closed_count else 0.0
    sample_ok = closed_count >= policy.min_closed_trades
    recommendation, reasons = _classify_family(
        sample_ok=sample_ok,
        total_net_pnl=total_net,
        average_net_pnl=average_net,
        net_win_rate=net_win_rate,
        policy=policy,
    )
    strategy_ids = _dedupe(bucket.get("strategy_id") for bucket in buckets)
    regimes = _dedupe(_text(bucket.get("regime")) or UNKNOWN_REGIME for bucket in buckets)
    return StrategyFamilyRecommendation(
        strategy_family=family,
        recommendation=recommendation,
        reason_code=reasons[0],
        reasons=reasons,
        strategy_ids=strategy_ids,
        regimes=regimes,
        closed_count=closed_count,
        net_win_count=net_win_count,
        net_loss_count=net_loss_count,
        net_flat_count=net_flat_count,
        total_gross_pnl=total_gross,
        total_cost=total_cost,
        total_net_pnl=total_net,
        average_net_pnl=average_net,
        net_win_rate=net_win_rate,
        net_loss_rate=net_loss_rate,
        net_expectancy_per_trade=average_net,
        cost_drag_per_trade=cost_drag,
        sample_ok=sample_ok,
        buckets=tuple(_bucket_snapshot(bucket) for bucket in buckets),
        metadata={"evidence_only": True, "policy_applied": True},
    )


def _classify_family(
    *,
    sample_ok: bool,
    total_net_pnl: float,
    average_net_pnl: float,
    net_win_rate: float,
    policy: StrategyFamilyPolicy,
) -> tuple[str, tuple[str, ...]]:
    if not sample_ok:
        return FAMILY_WATCH, (INSUFFICIENT_FAMILY_SAMPLE_REASON,)
    if average_net_pnl <= policy.kill_max_net_expectancy or total_net_pnl < 0.0:
        return FAMILY_KILL, (NEGATIVE_NET_EXPECTANCY_REASON,)
    if average_net_pnl >= policy.keep_min_net_expectancy and net_win_rate >= policy.keep_min_win_rate:
        return FAMILY_KEEP, (POSITIVE_NET_EXPECTANCY_REASON,)
    if net_win_rate < policy.keep_min_win_rate:
        return FAMILY_WATCH, (WEAK_NET_WIN_RATE_REASON,)
    return FAMILY_WATCH, (MIXED_OR_BORDERLINE_EVIDENCE_REASON,)


def _group_buckets(buckets: list[dict[str, Any]]) -> tuple[tuple[str, tuple[dict[str, Any], ...]], ...]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for bucket in buckets:
        family = _family_from_bucket(bucket)
        grouped.setdefault(family, []).append(bucket)
    return tuple((family, tuple(items)) for family, items in sorted(grouped.items(), key=lambda item: item[0]))


def _family_from_bucket(bucket: Mapping[str, Any]) -> str:
    metadata = bucket.get("metadata") if isinstance(bucket.get("metadata"), Mapping) else {}
    for key in ("strategy_family", "family", "family_id"):
        value = _text(metadata.get(key) if isinstance(metadata, Mapping) else None) or _text(bucket.get(key))
        if value:
            return value
    strategy_id = _text(bucket.get("strategy_id"))
    if not strategy_id:
        return UNKNOWN_FAMILY
    stripped = _VERSION_SUFFIX_RE.sub("", strategy_id)
    return stripped or strategy_id


def _bucket_snapshot(bucket: Mapping[str, Any]) -> dict[str, Any]:
    out = {
        "strategy_id": _text(bucket.get("strategy_id")),
        "regime": _text(bucket.get("regime")) or UNKNOWN_REGIME,
        "closed_count": _int(bucket.get("closed_count")),
        "total_gross_pnl": _float(bucket.get("total_gross_pnl")),
        "total_cost": _float(bucket.get("total_cost")),
        "total_net_pnl": _float(bucket.get("total_net_pnl")),
        "net_expectancy_per_trade": _float(bucket.get("net_expectancy_per_trade")),
    }
    _mark_non_action(out)
    return out


def _cost_truth_report_valid(payload: Mapping[str, Any]) -> bool:
    if not isinstance(payload, Mapping):
        return False
    if payload.get("read_only") is not True:
        return False
    if payload.get("append") is not False:
        return False
    if not isinstance(payload.get("buckets"), list):
        return False
    if str(payload.get("status") or "").strip() != "PAPER_SLIPPAGE_COST_REDUCED":
        return False
    return True


def _policy(
    *,
    min_closed_trades: Any,
    keep_min_net_expectancy: Any,
    keep_min_win_rate: Any,
    kill_max_net_expectancy: Any,
) -> StrategyFamilyPolicy:
    return StrategyFamilyPolicy(
        min_closed_trades=max(1, _int(min_closed_trades, default=DEFAULT_MIN_CLOSED_TRADES)),
        keep_min_net_expectancy=_float(keep_min_net_expectancy, default=DEFAULT_KEEP_MIN_NET_EXPECTANCY),
        keep_min_win_rate=max(0.0, min(1.0, _float(keep_min_win_rate, default=DEFAULT_KEEP_MIN_WIN_RATE))),
        kill_max_net_expectancy=_float(kill_max_net_expectancy, default=DEFAULT_KILL_MAX_NET_EXPECTANCY),
    )


def _blocked_report(
    *,
    reason_code: str,
    reasons: tuple[str, ...],
    policy: StrategyFamilyPolicy,
    cost_truth_report_valid: bool = False,
    metadata: dict[str, Any] | None = None,
) -> StrategyFamilyReport:
    return StrategyFamilyReport(
        schema_version=STRATEGY_FAMILY_REPORT_SCHEMA_VERSION,
        source=STRATEGY_FAMILY_REPORT_SOURCE,
        status=STRATEGY_FAMILY_REPORT_BLOCKED,
        reason_code=reason_code,
        reasons=_dedupe(reasons),
        cost_truth_report_valid=cost_truth_report_valid,
        family_count=0,
        keep_count=0,
        watch_count=0,
        kill_count=0,
        policy=policy,
        recommendations=(),
        metadata=dict(metadata or {}),
    )


def _payload(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_payload"):
        value = value.to_payload()
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return default


def _round(value: float) -> float:
    return round(float(value), 10)


def _dedupe(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in values if str(value or "").strip()}))


def _mark_non_action(payload: dict[str, Any]) -> None:
    payload[_ACTION_KEY] = False
    payload[_BROKER_KEY] = False
    payload["live_order_action"] = False
    payload["broker_order_action"] = False


__all__ = [
    "DEFAULT_KEEP_MIN_NET_EXPECTANCY",
    "DEFAULT_KEEP_MIN_WIN_RATE",
    "DEFAULT_KILL_MAX_NET_EXPECTANCY",
    "DEFAULT_MIN_CLOSED_TRADES",
    "FAMILY_KEEP",
    "FAMILY_KILL",
    "FAMILY_WATCH",
    "INSUFFICIENT_FAMILY_SAMPLE_REASON",
    "INVALID_COST_TRUTH_REPORT_REASON",
    "NEGATIVE_NET_EXPECTANCY_REASON",
    "NO_NET_COST_BUCKETS_REASON",
    "POSITIVE_NET_EXPECTANCY_REASON",
    "STRATEGY_FAMILY_REPORT_BLOCKED",
    "STRATEGY_FAMILY_REPORT_REDUCED",
    "STRATEGY_FAMILY_REPORT_SCHEMA_VERSION",
    "STRATEGY_FAMILY_REPORT_SOURCE",
    "StrategyFamilyPolicy",
    "StrategyFamilyRecommendation",
    "StrategyFamilyReport",
    "WEAK_NET_WIN_RATE_REASON",
    "build_strategy_family_report",
]
