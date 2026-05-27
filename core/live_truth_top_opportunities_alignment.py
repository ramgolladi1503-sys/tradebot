"""Read-only top-opportunities executable truth alignment for LIVE-TRUTH-01.

This module compares ranked executable truth with the top-opportunities artifact
truth. It detects cases where upstream ranked evidence says executable
candidates exist but the top-opportunities artifact reports zero executable
items. It does not place orders, force execution, mutate runtime state, or write
artifacts.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

TOP_OPPORTUNITIES_ALIGNMENT_SCHEMA_VERSION = 1
TOP_OPPORTUNITIES_ALIGNMENT_SOURCE = "live_truth_top_opportunities_alignment_v1"

ALIGNMENT_STATUS_ALIGNED = "TOP_OPPORTUNITIES_EXECUTABLE_TRUTH_ALIGNED"
ALIGNMENT_STATUS_BLOCKED = "TOP_OPPORTUNITIES_EXECUTABLE_TRUTH_BLOCKED"
ALIGNMENT_STATUS_MISMATCH = "TOP_OPPORTUNITIES_EXECUTABLE_TRUTH_MISMATCH"

INVALID_RANKED_REPORT_REASON = "invalid_ranked_opportunity_report"
INVALID_TOP_OPPORTUNITIES_REPORT_REASON = "invalid_top_opportunities_report"
EXECUTABLE_COUNT_MISMATCH_REASON = "executable_count_mismatch"
TOP_REPORTABLE_MISMATCH_REASON = "top_reportable_executable_mismatch"
TOP_EXECUTABLE_MISSING_REASON = "top_executable_missing_from_top_opportunities"
NO_MISMATCH_REASON = "ok"

_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class TopOpportunitiesExecutableAlignmentReport:
    """Read-only alignment report for ranked vs top-opportunities truth."""

    schema_version: int
    source: str
    status: str
    reason_code: str
    reasons: tuple[str, ...]
    ranked_report_valid: bool
    top_opportunities_report_valid: bool
    ranked_executable_count: int
    top_opportunities_executable_count: int
    ranked_top_reportable_executable: bool
    top_opportunities_top_reportable_executable: bool
    aligned: bool
    mismatch_detected: bool
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
            "ranked_report_valid": self.ranked_report_valid,
            "top_opportunities_report_valid": self.top_opportunities_report_valid,
            "ranked_executable_count": self.ranked_executable_count,
            "top_opportunities_executable_count": self.top_opportunities_executable_count,
            "ranked_top_reportable_executable": self.ranked_top_reportable_executable,
            "top_opportunities_top_reportable_executable": self.top_opportunities_top_reportable_executable,
            "aligned": self.aligned,
            "mismatch_detected": self.mismatch_detected,
            "read_only": self.read_only,
            "append": self.append,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def build_top_opportunities_executable_alignment(
    ranked_report: Mapping[str, Any] | Any,
    top_opportunities_report: Mapping[str, Any] | Any,
) -> TopOpportunitiesExecutableAlignmentReport:
    """Build read-only executable truth alignment evidence.

    The primary mismatch this PR captures is:

    - ranked executable count is greater than zero
    - ranked top reportable executable is true
    - top-opportunities executable count is zero

    That condition must be visible before later writer/runtime fixes are scoped.
    """

    ranked_payload = _payload(ranked_report)
    top_payload = _payload(top_opportunities_report)
    ranked_valid = _valid_mapping(ranked_payload)
    top_valid = _valid_mapping(top_payload)
    if not ranked_valid or not top_valid:
        reasons = []
        if not ranked_valid:
            reasons.append(INVALID_RANKED_REPORT_REASON)
        if not top_valid:
            reasons.append(INVALID_TOP_OPPORTUNITIES_REPORT_REASON)
        return _report(
            status=ALIGNMENT_STATUS_BLOCKED,
            reason_code=reasons[0],
            reasons=tuple(reasons),
            ranked_valid=ranked_valid,
            top_valid=top_valid,
            metadata={"blocked_before_alignment": True},
        )

    ranked_count = _ranked_executable_count(ranked_payload)
    top_count = _top_opportunities_executable_count(top_payload)
    ranked_top_reportable = _ranked_top_reportable_executable(ranked_payload)
    top_reportable = _top_opportunities_top_reportable_executable(top_payload)

    reasons = _alignment_reasons(
        ranked_executable_count=ranked_count,
        top_opportunities_executable_count=top_count,
        ranked_top_reportable_executable=ranked_top_reportable,
        top_opportunities_top_reportable_executable=top_reportable,
    )
    mismatch = bool(reasons)
    return _report(
        status=ALIGNMENT_STATUS_MISMATCH if mismatch else ALIGNMENT_STATUS_ALIGNED,
        reason_code=reasons[0] if reasons else NO_MISMATCH_REASON,
        reasons=reasons,
        ranked_valid=True,
        top_valid=True,
        ranked_executable_count=ranked_count,
        top_opportunities_executable_count=top_count,
        ranked_top_reportable_executable=ranked_top_reportable,
        top_opportunities_top_reportable_executable=top_reportable,
        aligned=not mismatch,
        mismatch_detected=mismatch,
        metadata={
            "ranked_source": str(ranked_payload.get("source") or ranked_payload.get("stage") or "ranked_report"),
            "top_opportunities_source": str(top_payload.get("source") or "top_opportunities_report"),
            "evidence_only": True,
            "does_not_force_execution": True,
        },
    )


def _alignment_reasons(
    *,
    ranked_executable_count: int,
    top_opportunities_executable_count: int,
    ranked_top_reportable_executable: bool,
    top_opportunities_top_reportable_executable: bool,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if ranked_executable_count != top_opportunities_executable_count:
        reasons.append(EXECUTABLE_COUNT_MISMATCH_REASON)
    if ranked_top_reportable_executable != top_opportunities_top_reportable_executable:
        reasons.append(TOP_REPORTABLE_MISMATCH_REASON)
    if ranked_executable_count > 0 and ranked_top_reportable_executable and top_opportunities_executable_count == 0:
        reasons.append(TOP_EXECUTABLE_MISSING_REASON)
    return _dedupe_preserve_order(reasons)


def _ranked_executable_count(payload: Mapping[str, Any]) -> int:
    for key in (
        "ranked_executable_count",
        "executable_count",
        "reportable_executable_count",
        "top_reportable_executable_count",
    ):
        if key in payload:
            return max(0, _int(payload.get(key)))
    candidates = _candidate_list(payload)
    if candidates:
        return sum(1 for candidate in candidates if _candidate_executable(candidate))
    return 0


def _top_opportunities_executable_count(payload: Mapping[str, Any]) -> int:
    for key in (
        "top_opportunities_executable_count",
        "executable_count",
        "reportable_executable_count",
    ):
        if key in payload:
            return max(0, _int(payload.get(key)))
    opportunities = _top_opportunity_list(payload)
    if opportunities:
        return sum(1 for item in opportunities if _candidate_executable(item))
    return 0


def _ranked_top_reportable_executable(payload: Mapping[str, Any]) -> bool:
    for key in ("top_reportable_executable", "ranked_top_reportable_executable", "top_executable"):
        if key in payload:
            return _bool(payload.get(key))
    candidates = _candidate_list(payload)
    if candidates:
        return _candidate_executable(candidates[0])
    return _ranked_executable_count(payload) > 0


def _top_opportunities_top_reportable_executable(payload: Mapping[str, Any]) -> bool:
    for key in (
        "top_opportunities_top_reportable_executable",
        "top_reportable_executable",
        "top_executable",
    ):
        if key in payload:
            return _bool(payload.get(key))
    opportunities = _top_opportunity_list(payload)
    if opportunities:
        return _candidate_executable(opportunities[0])
    return _top_opportunities_executable_count(payload) > 0


def _candidate_list(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    for key in ("ranked_candidates", "candidates", "opportunities", "items", "rows"):
        value = payload.get(key)
        if isinstance(value, list):
            return [_payload(item) for item in value]
    return []


def _top_opportunity_list(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    for key in ("top_opportunities", "opportunities", "items", "rows", "candidates"):
        value = payload.get(key)
        if isinstance(value, list):
            return [_payload(item) for item in value]
    return []


def _candidate_executable(candidate: Mapping[str, Any]) -> bool:
    for key in (
        "is_executable",
        "executable",
        "reportable_executable",
        "top_reportable_executable",
    ):
        if key in candidate:
            return _bool(candidate.get(key))
    status = str(candidate.get("status") or candidate.get("decision") or "").strip().upper()
    if status in {"EXECUTABLE", "REPORTABLE_EXECUTABLE", "APPROVED"}:
        return True
    if status in {"NO_TRADE", "BLOCKED", "REJECTED"}:
        return False
    blockers = candidate.get("blockers") or candidate.get("reasons") or []
    if isinstance(blockers, list) and blockers:
        return False
    return False


def _report(
    *,
    status: str,
    reason_code: str,
    reasons: Iterable[str],
    ranked_valid: bool,
    top_valid: bool,
    ranked_executable_count: int = 0,
    top_opportunities_executable_count: int = 0,
    ranked_top_reportable_executable: bool = False,
    top_opportunities_top_reportable_executable: bool = False,
    aligned: bool = False,
    mismatch_detected: bool = False,
    metadata: dict[str, Any] | None = None,
) -> TopOpportunitiesExecutableAlignmentReport:
    return TopOpportunitiesExecutableAlignmentReport(
        schema_version=TOP_OPPORTUNITIES_ALIGNMENT_SCHEMA_VERSION,
        source=TOP_OPPORTUNITIES_ALIGNMENT_SOURCE,
        status=status,
        reason_code=reason_code,
        reasons=_dedupe_preserve_order(reasons),
        ranked_report_valid=ranked_valid,
        top_opportunities_report_valid=top_valid,
        ranked_executable_count=ranked_executable_count,
        top_opportunities_executable_count=top_opportunities_executable_count,
        ranked_top_reportable_executable=ranked_top_reportable_executable,
        top_opportunities_top_reportable_executable=top_opportunities_top_reportable_executable,
        aligned=aligned,
        mismatch_detected=mismatch_detected,
        metadata=dict(metadata or {}),
    )


def _payload(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_payload"):
        value = value.to_payload()
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _valid_mapping(payload: Mapping[str, Any]) -> bool:
    return bool(payload)


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "executable"}


def _dedupe_preserve_order(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return tuple(out)


def _mark_non_action(payload: dict[str, Any]) -> None:
    payload[_ACTION_KEY] = False
    payload[_BROKER_KEY] = False
    payload["live_order_action"] = False
    payload["broker_order_action"] = False


__all__ = [
    "ALIGNMENT_STATUS_ALIGNED",
    "ALIGNMENT_STATUS_BLOCKED",
    "ALIGNMENT_STATUS_MISMATCH",
    "EXECUTABLE_COUNT_MISMATCH_REASON",
    "INVALID_RANKED_REPORT_REASON",
    "INVALID_TOP_OPPORTUNITIES_REPORT_REASON",
    "NO_MISMATCH_REASON",
    "TOP_EXECUTABLE_MISSING_REASON",
    "TOP_OPPORTUNITIES_ALIGNMENT_SCHEMA_VERSION",
    "TOP_OPPORTUNITIES_ALIGNMENT_SOURCE",
    "TOP_REPORTABLE_MISMATCH_REASON",
    "TopOpportunitiesExecutableAlignmentReport",
    "build_top_opportunities_executable_alignment",
]
