from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


BROKER_ACTION_FIELDS = (
    "is_order_action",
    "broker_api_called",
    "live_order_action",
    "broker_order_action",
)


@dataclass(frozen=True)
class TraceDimensionResult:
    name: str
    complete: bool
    missing_fields: tuple[str, ...] = ()
    hard_fail: bool = False


@dataclass(frozen=True)
class CandidateTraceScore:
    score: int
    trace_complete: bool
    hard_failed: bool
    dimensions: tuple[TraceDimensionResult, ...]
    missing_fields: tuple[str, ...] = field(default_factory=tuple)
    hard_fail_fields: tuple[str, ...] = field(default_factory=tuple)

    @property
    def incomplete_dimensions(self) -> tuple[TraceDimensionResult, ...]:
        return tuple(dimension for dimension in self.dimensions if not dimension.complete)


def score_candidate_trace(record: dict[str, Any]) -> CandidateTraceScore:
    """Score whether one candidate evidence record is decision-auditable.

    This module is intentionally static/evidence-only. It does not import runtime
    Tradebot code, call brokers, or alter ranking/strategy behavior.
    """

    dimensions = (
        _dimension("candidate_identity", record, ("candidate_id",), hard_fail=True),
        _dimension("source", record, ("source", "strategy")),
        _dimension("mode", record, ("mode",)),
        _dimension("timestamp", record, ("timestamp", "created_at", "event_time")),
        _dimension("input_data_quality", record, ("input_data_quality", "data_quality", "feed_quality")),
        _dimension("score_or_rank", record, ("score", "rank", "confidence", "confidence_raw")),
        _dimension("decision_reason", record, ("reason", "decision_reason", "rejection_reason", "acceptance_reason")),
        _dimension("risk_result", record, ("risk_result", "risk", "risk_decision")),
        _broker_action_dimension(record),
        _dimension("final_decision", record, ("decision", "final_decision")),
    )
    complete_count = sum(1 for dimension in dimensions if dimension.complete)
    score = int(round((complete_count / len(dimensions)) * 100))
    missing_fields = tuple(field for dimension in dimensions for field in dimension.missing_fields)
    hard_fail_fields = tuple(field for dimension in dimensions if dimension.hard_fail and not dimension.complete for field in dimension.missing_fields)
    hard_failed = bool(hard_fail_fields)
    trace_complete = score == 100 and not hard_failed
    return CandidateTraceScore(
        score=score,
        trace_complete=trace_complete,
        hard_failed=hard_failed,
        dimensions=dimensions,
        missing_fields=missing_fields,
        hard_fail_fields=hard_fail_fields,
    )


def _dimension(name: str, record: dict[str, Any], fields: tuple[str, ...], hard_fail: bool = False) -> TraceDimensionResult:
    if any(_has_value(record, field) for field in fields):
        return TraceDimensionResult(name=name, complete=True, hard_fail=hard_fail)
    return TraceDimensionResult(name=name, complete=False, missing_fields=fields, hard_fail=hard_fail)


def _broker_action_dimension(record: dict[str, Any]) -> TraceDimensionResult:
    missing = tuple(field for field in BROKER_ACTION_FIELDS if field not in record)
    unsafe = tuple(field for field in BROKER_ACTION_FIELDS if field in record and record[field] is not False)
    if not missing and not unsafe:
        return TraceDimensionResult(name="broker_action_flags", complete=True)
    return TraceDimensionResult(name="broker_action_flags", complete=False, missing_fields=missing + unsafe)


def _has_value(record: dict[str, Any], field: str) -> bool:
    value = record.get(field)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True
