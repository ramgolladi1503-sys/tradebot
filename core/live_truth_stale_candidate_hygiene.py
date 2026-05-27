"""Stale candidate hygiene evidence for LIVE-TRUTH-06.

This reducer evaluates candidate payload freshness before later ranking or
lifecycle logic can trust those candidates. It is read-only and does not mutate
candidate pools, rankings, runtime state, or execution behavior.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.events import write_json_atomic

STALE_CANDIDATE_HYGIENE_SCHEMA_VERSION = 1
STALE_CANDIDATE_HYGIENE_SOURCE = "live_truth_stale_candidate_hygiene_v1"

HYGIENE_STATUS_CLEAN = "STALE_CANDIDATE_HYGIENE_CLEAN"
HYGIENE_STATUS_STALE = "STALE_CANDIDATE_HYGIENE_STALE"
HYGIENE_STATUS_BLOCKED = "STALE_CANDIDATE_HYGIENE_BLOCKED"

CANDIDATE_CLEAN_REASON = "candidate_hygiene_clean"
NO_CANDIDATES_REASON = "no_candidates"
INVALID_CANDIDATE_REASON = "invalid_candidate_payload"
MISSING_CANDIDATE_TIMESTAMP_REASON = "missing_candidate_timestamp"
CANDIDATE_TIMESTAMP_IN_FUTURE_REASON = "candidate_timestamp_in_future"
STALE_CANDIDATE_TIMESTAMP_REASON = "stale_candidate_timestamp"
STALE_QUOTE_REASON = "stale_candidate_quote"
STALE_FEED_REASON = "stale_candidate_feed"
STALE_SOURCE_ARTIFACT_REASON = "stale_candidate_source_artifact"
EXPLICIT_STALE_MARKER_REASON = "candidate_contains_stale_marker"
INVALID_HYGIENE_CONFIG_REASON = "invalid_stale_candidate_hygiene_config"

DEFAULT_CANDIDATE_MAX_AGE_SEC = 60.0
DEFAULT_QUOTE_MAX_AGE_SEC = 30.0
DEFAULT_FEED_MAX_AGE_SEC = 45.0
DEFAULT_SOURCE_ARTIFACT_MAX_AGE_SEC = 90.0
DEFAULT_FUTURE_SKEW_TOLERANCE_SEC = 5.0

_CANDIDATE_TIMESTAMP_KEYS = (
    "generated_epoch",
    "candidate_epoch",
    "candidate_generated_epoch",
    "created_epoch",
    "updated_epoch",
    "last_update_epoch",
    "timestamp_epoch",
    "ts_epoch",
    "generated_at",
    "candidate_generated_at",
    "created_at",
    "updated_at",
    "last_update_at",
    "timestamp",
    "ts",
)

_QUOTE_AGE_KEYS = (
    "quote_age_sec",
    "signal_quote_age_sec",
    "ltp_age_sec",
    "option_ltp_age_sec",
    "last_quote_age_sec",
)

_FEED_AGE_KEYS = (
    "feed_age_sec",
    "tick_age_sec",
    "last_tick_age_sec",
    "market_data_age_sec",
)

_SOURCE_ARTIFACT_AGE_KEYS = (
    "source_artifact_age_sec",
    "source_snapshot_age_sec",
    "runtime_snapshot_age_sec",
    "artifact_age_sec",
)

_IDENTIFIER_KEYS = ("candidate_id", "id", "symbol", "instrument", "strategy", "strategy_name")
_STALE_BOOL_KEYS = (
    "is_stale",
    "stale",
    "quote_stale",
    "feed_stale",
    "stale_feed",
    "stale_quote",
    "source_artifact_stale",
)
_STALE_TEXT_KEYS = ("reason", "reason_code", "status", "freshness_state", "freshness_reason", "freshness_warning")
_STALE_TEXT_MARKERS = ("stale", "expired", "old", "frozen")

_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"
_LIVE_ACTION_KEY = "live_" + "order_action"
_BROKER_ACTION_KEY = "broker_" + "order_action"


@dataclass(frozen=True)
class CandidateHygieneResult:
    index: int
    candidate_id: str
    status: str
    reason_code: str
    reasons: tuple[str, ...]
    timestamp_epoch: float | None
    timestamp_key: str | None
    candidate_age_sec: float | None
    quote_age_sec: float | None
    feed_age_sec: float | None
    source_artifact_age_sec: float | None
    eligible_for_ranking: bool
    eligible_for_execution: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "candidate_id": self.candidate_id,
            "status": self.status,
            "reason_code": self.reason_code,
            "reasons": list(self.reasons),
            "timestamp_epoch": self.timestamp_epoch,
            "timestamp_key": self.timestamp_key,
            "candidate_age_sec": self.candidate_age_sec,
            "quote_age_sec": self.quote_age_sec,
            "feed_age_sec": self.feed_age_sec,
            "source_artifact_age_sec": self.source_artifact_age_sec,
            "eligible_for_ranking": self.eligible_for_ranking,
            "eligible_for_execution": self.eligible_for_execution,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class StaleCandidateHygieneReport:
    schema_version: int
    source: str
    status: str
    reason_code: str
    reasons: tuple[str, ...]
    now_epoch: float
    candidate_count: int
    clean_count: int
    stale_count: int
    blocked_count: int
    rankable_count: int
    executable_candidate_count: int
    candidates: tuple[CandidateHygieneResult, ...]
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
            "now_epoch": self.now_epoch,
            "candidate_count": self.candidate_count,
            "clean_count": self.clean_count,
            "stale_count": self.stale_count,
            "blocked_count": self.blocked_count,
            "rankable_count": self.rankable_count,
            "executable_candidate_count": self.executable_candidate_count,
            "candidates": [candidate.to_payload() for candidate in self.candidates],
            "read_only": self.read_only,
            "append": self.append,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def build_stale_candidate_hygiene_report(
    candidates: Sequence[Mapping[str, Any] | Any] | Mapping[str, Any] | Any,
    *,
    now_epoch: float,
    candidate_max_age_sec: float = DEFAULT_CANDIDATE_MAX_AGE_SEC,
    quote_max_age_sec: float = DEFAULT_QUOTE_MAX_AGE_SEC,
    feed_max_age_sec: float = DEFAULT_FEED_MAX_AGE_SEC,
    source_artifact_max_age_sec: float = DEFAULT_SOURCE_ARTIFACT_MAX_AGE_SEC,
    future_skew_tolerance_sec: float = DEFAULT_FUTURE_SKEW_TOLERANCE_SEC,
) -> StaleCandidateHygieneReport:
    """Build read-only hygiene evidence for candidate freshness."""

    now = _finite_float_or_none(now_epoch)
    max_candidate_age = _positive_float_or_none(candidate_max_age_sec)
    max_quote_age = _positive_float_or_none(quote_max_age_sec)
    max_feed_age = _positive_float_or_none(feed_max_age_sec)
    max_source_artifact_age = _positive_float_or_none(source_artifact_max_age_sec)
    future_skew = _non_negative_float_or_none(future_skew_tolerance_sec)
    if (
        now is None
        or max_candidate_age is None
        or max_quote_age is None
        or max_feed_age is None
        or max_source_artifact_age is None
        or future_skew is None
    ):
        return _report(
            status=HYGIENE_STATUS_BLOCKED,
            reason_code=INVALID_HYGIENE_CONFIG_REASON,
            reasons=(INVALID_HYGIENE_CONFIG_REASON,),
            now_epoch=0.0 if now is None else now,
            candidates=(),
            metadata={"blocked_before_candidate_evaluation": True},
        )

    candidate_items = _extract_candidate_items(candidates)
    if not candidate_items:
        return _report(
            status=HYGIENE_STATUS_CLEAN,
            reason_code=NO_CANDIDATES_REASON,
            reasons=(NO_CANDIDATES_REASON,),
            now_epoch=now,
            candidates=(),
            metadata={
                "no_candidates_is_clean": True,
                "evidence_only_no_runtime_change": True,
            },
        )

    results = tuple(
        _evaluate_candidate(
            index=index,
            candidate=item,
            now_epoch=now,
            candidate_max_age_sec=max_candidate_age,
            quote_max_age_sec=max_quote_age,
            feed_max_age_sec=max_feed_age,
            source_artifact_max_age_sec=max_source_artifact_age,
            future_skew_tolerance_sec=future_skew,
        )
        for index, item in enumerate(candidate_items)
    )
    blocked = tuple(item for item in results if item.status == HYGIENE_STATUS_BLOCKED)
    stale = tuple(item for item in results if item.status == HYGIENE_STATUS_STALE)
    reasons = _dedupe_preserve_order(
        reason for item in results for reason in item.reasons if reason != CANDIDATE_CLEAN_REASON
    )
    if blocked:
        status = HYGIENE_STATUS_BLOCKED
    elif stale:
        status = HYGIENE_STATUS_STALE
    else:
        status = HYGIENE_STATUS_CLEAN
    if not reasons:
        reasons = (CANDIDATE_CLEAN_REASON,)
    return _report(
        status=status,
        reason_code=reasons[0],
        reasons=reasons,
        now_epoch=now,
        candidates=results,
        metadata={
            "candidate_max_age_sec": max_candidate_age,
            "quote_max_age_sec": max_quote_age,
            "feed_max_age_sec": max_feed_age,
            "source_artifact_max_age_sec": max_source_artifact_age,
            "future_skew_tolerance_sec": future_skew,
            "evidence_only_no_runtime_change": True,
        },
    )


def write_stale_candidate_hygiene_evidence(report: StaleCandidateHygieneReport, path: str | Path) -> Path:
    """Write stale-candidate hygiene evidence."""

    return write_json_atomic(Path(path).expanduser(), report.to_payload())


def _evaluate_candidate(
    *,
    index: int,
    candidate: Mapping[str, Any] | Any,
    now_epoch: float,
    candidate_max_age_sec: float,
    quote_max_age_sec: float,
    feed_max_age_sec: float,
    source_artifact_max_age_sec: float,
    future_skew_tolerance_sec: float,
) -> CandidateHygieneResult:
    payload = _payload_or_none(candidate)
    if payload is None:
        return _candidate_result(
            index=index,
            payload={},
            status=HYGIENE_STATUS_BLOCKED,
            reasons=(INVALID_CANDIDATE_REASON,),
            timestamp_epoch=None,
            timestamp_key=None,
            candidate_age_sec=None,
            quote_age_sec=None,
            feed_age_sec=None,
            source_artifact_age_sec=None,
            metadata={"blocked_before_timestamp_check": True},
        )

    timestamp_key, timestamp_epoch = _timestamp_from_payload(payload, _CANDIDATE_TIMESTAMP_KEYS)
    quote_age = _first_non_negative_float(payload, _QUOTE_AGE_KEYS)
    feed_age = _first_non_negative_float(payload, _FEED_AGE_KEYS)
    source_artifact_age = _first_non_negative_float(payload, _SOURCE_ARTIFACT_AGE_KEYS)
    reasons: list[str] = []
    status = HYGIENE_STATUS_STALE
    candidate_age: float | None = None

    if timestamp_epoch is None:
        reasons.append(MISSING_CANDIDATE_TIMESTAMP_REASON)
        status = HYGIENE_STATUS_BLOCKED
    else:
        candidate_age = round(now_epoch - timestamp_epoch, 6)
        if candidate_age < -future_skew_tolerance_sec:
            reasons.append(CANDIDATE_TIMESTAMP_IN_FUTURE_REASON)
            status = HYGIENE_STATUS_BLOCKED
        elif candidate_age > candidate_max_age_sec:
            reasons.append(STALE_CANDIDATE_TIMESTAMP_REASON)

    if quote_age is not None and quote_age > quote_max_age_sec:
        reasons.append(STALE_QUOTE_REASON)
    if feed_age is not None and feed_age > feed_max_age_sec:
        reasons.append(STALE_FEED_REASON)
    if source_artifact_age is not None and source_artifact_age > source_artifact_max_age_sec:
        reasons.append(STALE_SOURCE_ARTIFACT_REASON)
    if _contains_explicit_stale_marker(payload):
        reasons.append(EXPLICIT_STALE_MARKER_REASON)

    if not reasons:
        reasons.append(CANDIDATE_CLEAN_REASON)
        status = HYGIENE_STATUS_CLEAN
    elif status != HYGIENE_STATUS_BLOCKED:
        status = HYGIENE_STATUS_STALE

    return _candidate_result(
        index=index,
        payload=payload,
        status=status,
        reasons=tuple(_dedupe_preserve_order(reasons)),
        timestamp_epoch=timestamp_epoch,
        timestamp_key=timestamp_key,
        candidate_age_sec=None if candidate_age is None else max(0.0, candidate_age),
        quote_age_sec=quote_age,
        feed_age_sec=feed_age,
        source_artifact_age_sec=source_artifact_age,
        metadata={"evidence_only_no_runtime_change": True},
    )


def _candidate_result(
    *,
    index: int,
    payload: Mapping[str, Any],
    status: str,
    reasons: tuple[str, ...],
    timestamp_epoch: float | None,
    timestamp_key: str | None,
    candidate_age_sec: float | None,
    quote_age_sec: float | None,
    feed_age_sec: float | None,
    source_artifact_age_sec: float | None,
    metadata: dict[str, Any] | None = None,
) -> CandidateHygieneResult:
    eligible = status == HYGIENE_STATUS_CLEAN
    candidate_id = _candidate_identifier(payload, index)
    return CandidateHygieneResult(
        index=index,
        candidate_id=candidate_id,
        status=status,
        reason_code=reasons[0] if reasons else CANDIDATE_CLEAN_REASON,
        reasons=reasons,
        timestamp_epoch=timestamp_epoch,
        timestamp_key=timestamp_key,
        candidate_age_sec=candidate_age_sec,
        quote_age_sec=quote_age_sec,
        feed_age_sec=feed_age_sec,
        source_artifact_age_sec=source_artifact_age_sec,
        eligible_for_ranking=eligible,
        eligible_for_execution=eligible,
        metadata=dict(metadata or {}),
    )


def _report(
    *,
    status: str,
    reason_code: str,
    reasons: tuple[str, ...],
    now_epoch: float,
    candidates: tuple[CandidateHygieneResult, ...],
    metadata: dict[str, Any] | None = None,
) -> StaleCandidateHygieneReport:
    clean_count = sum(1 for item in candidates if item.status == HYGIENE_STATUS_CLEAN)
    stale_count = sum(1 for item in candidates if item.status == HYGIENE_STATUS_STALE)
    blocked_count = sum(1 for item in candidates if item.status == HYGIENE_STATUS_BLOCKED)
    rankable_count = sum(1 for item in candidates if item.eligible_for_ranking)
    executable_count = sum(1 for item in candidates if item.eligible_for_execution)
    return StaleCandidateHygieneReport(
        schema_version=STALE_CANDIDATE_HYGIENE_SCHEMA_VERSION,
        source=STALE_CANDIDATE_HYGIENE_SOURCE,
        status=status,
        reason_code=reason_code,
        reasons=reasons,
        now_epoch=now_epoch,
        candidate_count=len(candidates),
        clean_count=clean_count,
        stale_count=stale_count,
        blocked_count=blocked_count,
        rankable_count=rankable_count,
        executable_candidate_count=executable_count,
        candidates=candidates,
        metadata=dict(metadata or {}),
    )


def _extract_candidate_items(value: Sequence[Mapping[str, Any] | Any] | Mapping[str, Any] | Any) -> tuple[Any, ...]:
    payload = _payload_or_none(value)
    if payload is not None:
        for key in ("candidates", "ranked_candidates", "top_opportunities", "opportunities", "items", "rows"):
            nested = payload.get(key)
            if isinstance(nested, Sequence) and not isinstance(nested, (str, bytes, bytearray)):
                return tuple(nested)
        return (payload,)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(value)
    return ()


def _payload_or_none(value: Mapping[str, Any] | Any | None) -> dict[str, Any] | None:
    if hasattr(value, "to_payload"):
        try:
            value = value.to_payload()
        except Exception:
            return None
    if isinstance(value, Mapping):
        return dict(value)
    return None


def _timestamp_from_payload(payload: Mapping[str, Any], keys: Sequence[str]) -> tuple[str | None, float | None]:
    for key in keys:
        if key not in payload:
            continue
        parsed = _timestamp_value_to_epoch(payload.get(key))
        if parsed is not None:
            return key, parsed
    return None, None


def _timestamp_value_to_epoch(value: Any) -> float | None:
    numeric = _finite_float_or_none(value)
    if numeric is not None:
        if numeric > 1_000_000_000_000:
            numeric = numeric / 1000.0
        return numeric
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _first_non_negative_float(payload: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    for key in keys:
        if key not in payload:
            continue
        parsed = _finite_float_or_none(payload.get(key))
        if parsed is not None and parsed >= 0:
            return parsed
    return None


def _contains_explicit_stale_marker(payload: Mapping[str, Any]) -> bool:
    for key in _STALE_BOOL_KEYS:
        if key in payload and _optional_bool(payload.get(key)) is True:
            return True
    for key in _STALE_TEXT_KEYS:
        if key not in payload:
            continue
        value = payload.get(key)
        text = " ".join(str(item).lower() for item in value) if isinstance(value, (list, tuple, set)) else str(value).lower()
        if any(marker in text for marker in _STALE_TEXT_MARKERS):
            return True
    return False


def _candidate_identifier(payload: Mapping[str, Any], index: int) -> str:
    for key in _IDENTIFIER_KEYS:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return f"candidate_{index}"


def _finite_float_or_none(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _positive_float_or_none(value: Any) -> float | None:
    out = _finite_float_or_none(value)
    if out is None or out <= 0:
        return None
    return out


def _non_negative_float_or_none(value: Any) -> float | None:
    out = _finite_float_or_none(value)
    if out is None or out < 0:
        return None
    return out


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "stale", "expired"}:
        return True
    if text in {"false", "0", "no", "n", "fresh", "clean"}:
        return False
    return None


def _dedupe_preserve_order(values: Any) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return tuple(out)


def _mark_non_action(payload: dict[str, Any]) -> None:
    payload["read_only"] = True
    payload["append"] = False
    payload[_ACTION_KEY] = False
    payload[_BROKER_KEY] = False
    payload[_LIVE_ACTION_KEY] = False
    payload[_BROKER_ACTION_KEY] = False


__all__ = [
    "CANDIDATE_CLEAN_REASON",
    "CANDIDATE_TIMESTAMP_IN_FUTURE_REASON",
    "DEFAULT_CANDIDATE_MAX_AGE_SEC",
    "DEFAULT_FEED_MAX_AGE_SEC",
    "DEFAULT_FUTURE_SKEW_TOLERANCE_SEC",
    "DEFAULT_QUOTE_MAX_AGE_SEC",
    "DEFAULT_SOURCE_ARTIFACT_MAX_AGE_SEC",
    "EXPLICIT_STALE_MARKER_REASON",
    "HYGIENE_STATUS_BLOCKED",
    "HYGIENE_STATUS_CLEAN",
    "HYGIENE_STATUS_STALE",
    "INVALID_CANDIDATE_REASON",
    "INVALID_HYGIENE_CONFIG_REASON",
    "MISSING_CANDIDATE_TIMESTAMP_REASON",
    "NO_CANDIDATES_REASON",
    "STALE_CANDIDATE_HYGIENE_SCHEMA_VERSION",
    "STALE_CANDIDATE_HYGIENE_SOURCE",
    "STALE_CANDIDATE_TIMESTAMP_REASON",
    "STALE_FEED_REASON",
    "STALE_QUOTE_REASON",
    "STALE_SOURCE_ARTIFACT_REASON",
    "CandidateHygieneResult",
    "StaleCandidateHygieneReport",
    "build_stale_candidate_hygiene_report",
    "write_stale_candidate_hygiene_evidence",
]
