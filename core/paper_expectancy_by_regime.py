"""Read-only paper expectancy aggregation for EDGE-85.

This module consumes EDGE-84 paper outcomes and derives strategy/regime summary
statistics. It does not mutate paper truth, append events, call adapters, change
runtime behavior, or make strategy lifecycle decisions.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from core.paper_outcome_reducer import OUTCOME_CLOSED, PaperOutcomeReductionReport

PAPER_EXPECTANCY_SCHEMA_VERSION = 1
PAPER_EXPECTANCY_SOURCE = "paper_expectancy_by_regime_v1"

EXPECTANCY_STATUS_REDUCED = "PAPER_EXPECTANCY_REDUCED"
EXPECTANCY_STATUS_BLOCKED = "PAPER_EXPECTANCY_BLOCKED"

MIN_CLOSED_OUTCOMES_DEFAULT = 1
UNKNOWN_REGIME = "UNKNOWN"
UNKNOWN_STRATEGY = "UNKNOWN_STRATEGY"

INVALID_OUTCOME_REPORT_REASON = "invalid_outcome_reduction_report"
NO_CLOSED_OUTCOMES_REASON = "no_closed_paper_outcomes"
INSUFFICIENT_SAMPLE_REASON = "insufficient_closed_sample"

_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class PaperExpectancyBucket:
    """Closed paper outcome expectancy for one strategy/regime bucket."""

    strategy_id: str
    regime: str
    closed_count: int
    win_count: int
    loss_count: int
    flat_count: int
    total_gross_pnl: float
    average_gross_pnl: float
    win_rate: float
    loss_rate: float
    expectancy_per_trade: float
    sample_ok: bool
    blockers: tuple[str, ...] = ()
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
            "strategy_id": self.strategy_id,
            "regime": self.regime,
            "closed_count": self.closed_count,
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "flat_count": self.flat_count,
            "total_gross_pnl": self.total_gross_pnl,
            "average_gross_pnl": self.average_gross_pnl,
            "win_rate": self.win_rate,
            "loss_rate": self.loss_rate,
            "expectancy_per_trade": self.expectancy_per_trade,
            "sample_ok": self.sample_ok,
            "blockers": list(self.blockers),
            "metadata": dict(self.metadata),
            "read_only": True,
            "append": False,
        }
        _mark_non_action(payload)
        return payload


@dataclass(frozen=True)
class PaperExpectancyReport:
    """Read-only expectancy report derived from closed paper outcomes."""

    schema_version: int
    source: str
    status: str
    reason_code: str
    reasons: tuple[str, ...]
    outcome_report_valid: bool
    closed_outcome_count: int
    bucket_count: int
    buckets: tuple[PaperExpectancyBucket, ...]
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
            "outcome_report_valid": self.outcome_report_valid,
            "closed_outcome_count": self.closed_outcome_count,
            "bucket_count": self.bucket_count,
            "buckets": [bucket.to_payload() for bucket in self.buckets],
            "read_only": self.read_only,
            "append": self.append,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def build_expectancy_by_regime(
    outcome_report: PaperOutcomeReductionReport | Mapping[str, Any],
    *,
    min_closed_outcomes: int = MIN_CLOSED_OUTCOMES_DEFAULT,
) -> PaperExpectancyReport:
    """Build strategy/regime expectancy from an EDGE-84 outcome report."""

    min_sample = _positive_int(min_closed_outcomes, default=MIN_CLOSED_OUTCOMES_DEFAULT)
    report_payload = _payload(outcome_report)
    if not _outcome_report_valid(report_payload):
        return _blocked_report(
            reason_code=INVALID_OUTCOME_REPORT_REASON,
            reasons=(INVALID_OUTCOME_REPORT_REASON,),
            metadata={"min_closed_outcomes": min_sample},
        )

    raw_outcomes = report_payload.get("outcomes") or []
    closed = [_payload(item) for item in raw_outcomes if _text(_payload(item).get("status")) == OUTCOME_CLOSED]
    if not closed:
        return _blocked_report(
            reason_code=NO_CLOSED_OUTCOMES_REASON,
            reasons=(NO_CLOSED_OUTCOMES_REASON,),
            outcome_report_valid=True,
            metadata={"min_closed_outcomes": min_sample},
        )

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for outcome in closed:
        strategy_id = _text(outcome.get("strategy_id")) or UNKNOWN_STRATEGY
        regime = _regime_from_outcome(outcome)
        grouped.setdefault((strategy_id, regime), []).append(outcome)

    buckets = tuple(
        _bucket_from_group(strategy_id=strategy_id, regime=regime, outcomes=items, min_sample=min_sample)
        for (strategy_id, regime), items in sorted(grouped.items(), key=lambda item: item[0])
    )
    blocked_reasons = _dedupe(reason for bucket in buckets for reason in bucket.blockers)
    status = EXPECTANCY_STATUS_BLOCKED if blocked_reasons else EXPECTANCY_STATUS_REDUCED
    reason_code = blocked_reasons[0] if blocked_reasons else "ok"
    return PaperExpectancyReport(
        schema_version=PAPER_EXPECTANCY_SCHEMA_VERSION,
        source=PAPER_EXPECTANCY_SOURCE,
        status=status,
        reason_code=reason_code,
        reasons=blocked_reasons,
        outcome_report_valid=True,
        closed_outcome_count=len(closed),
        bucket_count=len(buckets),
        buckets=buckets,
        metadata={
            "min_closed_outcomes": min_sample,
            "derived_from": str(report_payload.get("source") or "paper_outcome_reducer"),
            "read_only_reducer": True,
        },
    )


def _bucket_from_group(
    *,
    strategy_id: str,
    regime: str,
    outcomes: list[dict[str, Any]],
    min_sample: int,
) -> PaperExpectancyBucket:
    pnl_values = [_float(item.get("gross_pnl")) for item in outcomes]
    closed_count = len(pnl_values)
    win_count = sum(1 for value in pnl_values if value > 0.0)
    loss_count = sum(1 for value in pnl_values if value < 0.0)
    flat_count = closed_count - win_count - loss_count
    total = round(sum(pnl_values), 10)
    average = round(total / closed_count, 10) if closed_count else 0.0
    blockers = () if closed_count >= min_sample else (INSUFFICIENT_SAMPLE_REASON,)
    return PaperExpectancyBucket(
        strategy_id=strategy_id,
        regime=regime,
        closed_count=closed_count,
        win_count=win_count,
        loss_count=loss_count,
        flat_count=flat_count,
        total_gross_pnl=total,
        average_gross_pnl=average,
        win_rate=round(win_count / closed_count, 10) if closed_count else 0.0,
        loss_rate=round(loss_count / closed_count, 10) if closed_count else 0.0,
        expectancy_per_trade=average,
        sample_ok=closed_count >= min_sample,
        blockers=blockers,
        metadata={"min_closed_outcomes": min_sample},
    )


def _outcome_report_valid(payload: Mapping[str, Any]) -> bool:
    if not isinstance(payload, Mapping):
        return False
    if payload.get("journal_valid") is not True:
        return False
    if payload.get("read_only") is not True:
        return False
    if payload.get("append") is not False:
        return False
    if not isinstance(payload.get("outcomes"), list):
        return False
    return True


def _blocked_report(
    *,
    reason_code: str,
    reasons: tuple[str, ...],
    outcome_report_valid: bool = False,
    metadata: dict[str, Any] | None = None,
) -> PaperExpectancyReport:
    return PaperExpectancyReport(
        schema_version=PAPER_EXPECTANCY_SCHEMA_VERSION,
        source=PAPER_EXPECTANCY_SOURCE,
        status=EXPECTANCY_STATUS_BLOCKED,
        reason_code=reason_code,
        reasons=_dedupe(reasons),
        outcome_report_valid=outcome_report_valid,
        closed_outcome_count=0,
        bucket_count=0,
        buckets=(),
        metadata=dict(metadata or {}),
    )


def _payload(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_payload"):
        value = value.to_payload()
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _regime_from_outcome(outcome: Mapping[str, Any]) -> str:
    metadata = outcome.get("metadata") if isinstance(outcome.get("metadata"), Mapping) else {}
    for key in ("regime", "market_regime", "regime_id"):
        value = _text(metadata.get(key) if isinstance(metadata, Mapping) else None) or _text(outcome.get(key))
        if value:
            return value
    return UNKNOWN_REGIME


def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        return default
    return max(1, parsed)


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dedupe(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in values if str(value or "").strip()}))


def _mark_non_action(payload: dict[str, Any]) -> None:
    payload[_ACTION_KEY] = False
    payload[_BROKER_KEY] = False
    payload["live_order_action"] = False
    payload["broker_order_action"] = False


__all__ = [
    "EXPECTANCY_STATUS_BLOCKED",
    "EXPECTANCY_STATUS_REDUCED",
    "INSUFFICIENT_SAMPLE_REASON",
    "INVALID_OUTCOME_REPORT_REASON",
    "NO_CLOSED_OUTCOMES_REASON",
    "PAPER_EXPECTANCY_SCHEMA_VERSION",
    "PAPER_EXPECTANCY_SOURCE",
    "PaperExpectancyBucket",
    "PaperExpectancyReport",
    "UNKNOWN_REGIME",
    "UNKNOWN_STRATEGY",
    "build_expectancy_by_regime",
]
