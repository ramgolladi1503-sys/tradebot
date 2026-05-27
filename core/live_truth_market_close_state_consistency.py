"""Market-close state consistency evidence for LIVE-TRUTH-05.

This reducer checks whether close-state runtime artifacts agree that the market
is closed/off-hours and whether expensive loops/candidate counts are quiet. It
is read-only and does not mutate runtime state or wire scheduler behavior.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.events import write_json_atomic

MARKET_CLOSE_STATE_SCHEMA_VERSION = 1
MARKET_CLOSE_STATE_SOURCE = "live_truth_market_close_state_consistency_v1"

MARKET_CLOSE_STATUS_CONSISTENT = "MARKET_CLOSE_STATE_CONSISTENT"
MARKET_CLOSE_STATUS_INCONSISTENT = "MARKET_CLOSE_STATE_INCONSISTENT"
MARKET_CLOSE_STATUS_BLOCKED = "MARKET_CLOSE_STATE_BLOCKED"
MARKET_CLOSE_STATUS_NOT_APPLICABLE = "MARKET_CLOSE_STATE_NOT_APPLICABLE"

CLOSE_STATE_OK_REASON = "market_close_state_consistent"
INVALID_MARKET_SNAPSHOT_REASON = "invalid_market_snapshot"
MISSING_MARKET_OPEN_REASON = "missing_market_open"
MARKET_OPEN_TRUE_REASON = "market_open_true"
FEED_MARKET_OPEN_CONFLICT_REASON = "feed_runtime_market_open_conflict_without_freshness_warning"
TOP_MARKET_STATE_MISSING_REASON = "top_opportunities_market_state_missing"
TOP_MARKET_STATE_NOT_CLOSED_REASON = "top_opportunities_market_state_not_closed_or_offhours"
SOURCE_CANDIDATES_NOT_QUIET_REASON = "source_candidate_count_not_quiet_after_close"
EXECUTABLES_NOT_ZERO_REASON = "executable_count_not_zero_after_close"
RUNTIME_HEALTH_NOT_QUIET_REASON = "runtime_health_not_quiet_or_offhours"
HIGH_FREQUENCY_LOOP_ACTIVE_REASON = "high_frequency_loop_active_after_close"

DEFAULT_MAX_OFFHOURS_LOOP_FREQUENCY_HZ = 0.2

_MARKET_CLOSED_TOKENS = ("market_closed", "offhours", "off_hours", "offhours_blocked", "closed")
_QUIET_TOKENS = ("market_closed", "offhours", "off_hours", "quiet", "idle", "paused")
_MARKET_OPEN_KEYS = ("market_open", "is_market_open", "open")
_MARKET_STATE_KEYS = ("market_state", "runtime_state", "state", "status", "reason_code")
_SOURCE_COUNT_KEYS = (
    "source_candidate_count",
    "top_opportunities_source_candidate_count",
    "candidate_count",
    "candidates_count",
    "ranked_total_count",
)
_EXECUTABLE_COUNT_KEYS = (
    "executable_count",
    "ranked_executable_count",
    "reportable_executable_count",
    "top_executable_count",
    "top_opportunities_executable_count",
)
_OFFHOURS_ALLOWED_KEYS = (
    "offhours_planning_enabled",
    "offhours_analysis_enabled",
    "replay_mode",
    "replay_enabled",
    "planning_mode",
)
_QUIET_BOOL_KEYS = ("quiet_mode", "offhours_mode", "off_hours_mode", "market_closed_mode")
_LOOP_ACTIVE_KEYS = (
    "slo_loop_active",
    "high_frequency_slo_loop_active",
    "candidate_scan_active",
    "scanner_active",
    "ranking_loop_active",
)
_LOOP_FREQUENCY_KEYS = ("loop_frequency_hz", "slo_loop_frequency_hz", "candidate_scan_frequency_hz")
_FRESHNESS_WARNING_KEYS = (
    "freshness_warning",
    "freshness_warnings",
    "freshness_state",
    "freshness_status",
    "freshness_reason",
    "freshness_reason_code",
    "reason_code",
    "reasons",
)

_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"
_LIVE_ACTION_KEY = "live_" + "order_action"
_BROKER_ACTION_KEY = "broker_" + "order_action"


@dataclass(frozen=True)
class MarketCloseStateConsistencyReport:
    schema_version: int
    source: str
    status: str
    reason_code: str
    reasons: tuple[str, ...]
    market_open: bool | None
    expected_market_state: str
    feed_market_open: bool | None
    feed_freshness_warning_present: bool
    top_market_state: str
    top_market_state_closed: bool
    source_candidate_count: int
    offhours_planning_enabled: bool
    executable_count: int
    runtime_health_quiet: bool
    high_frequency_loop_active: bool
    max_offhours_loop_frequency_hz: float
    violation_count: int
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
            "market_open": self.market_open,
            "expected_market_state": self.expected_market_state,
            "feed_market_open": self.feed_market_open,
            "feed_freshness_warning_present": self.feed_freshness_warning_present,
            "top_market_state": self.top_market_state,
            "top_market_state_closed": self.top_market_state_closed,
            "source_candidate_count": self.source_candidate_count,
            "offhours_planning_enabled": self.offhours_planning_enabled,
            "executable_count": self.executable_count,
            "runtime_health_quiet": self.runtime_health_quiet,
            "high_frequency_loop_active": self.high_frequency_loop_active,
            "max_offhours_loop_frequency_hz": self.max_offhours_loop_frequency_hz,
            "violation_count": self.violation_count,
            "read_only": self.read_only,
            "append": self.append,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def build_market_close_state_consistency_report(
    *,
    market_snapshot: Mapping[str, Any] | Any,
    feed_runtime: Mapping[str, Any] | Any | None = None,
    top_opportunities: Mapping[str, Any] | Any | None = None,
    runtime_health: Mapping[str, Any] | Any | None = None,
    max_offhours_loop_frequency_hz: float = DEFAULT_MAX_OFFHOURS_LOOP_FREQUENCY_HZ,
) -> MarketCloseStateConsistencyReport:
    """Build read-only evidence for market-close/off-hours consistency."""

    max_loop_hz = _non_negative_float(max_offhours_loop_frequency_hz, DEFAULT_MAX_OFFHOURS_LOOP_FREQUENCY_HZ)
    market_payload = _payload_or_none(market_snapshot)
    if market_payload is None:
        return _report(
            status=MARKET_CLOSE_STATUS_BLOCKED,
            reason_code=INVALID_MARKET_SNAPSHOT_REASON,
            reasons=(INVALID_MARKET_SNAPSHOT_REASON,),
            market_open=None,
            expected_market_state="UNKNOWN",
            feed_market_open=None,
            feed_freshness_warning_present=False,
            top_market_state="",
            top_market_state_closed=False,
            source_candidate_count=0,
            offhours_planning_enabled=False,
            executable_count=0,
            runtime_health_quiet=False,
            high_frequency_loop_active=False,
            max_offhours_loop_frequency_hz=max_loop_hz,
            metadata={"blocked_before_consistency_check": True},
        )

    market_open = _first_optional_bool(market_payload, _MARKET_OPEN_KEYS)
    if market_open is None:
        return _report(
            status=MARKET_CLOSE_STATUS_BLOCKED,
            reason_code=MISSING_MARKET_OPEN_REASON,
            reasons=(MISSING_MARKET_OPEN_REASON,),
            market_open=None,
            expected_market_state="UNKNOWN",
            feed_market_open=None,
            feed_freshness_warning_present=False,
            top_market_state="",
            top_market_state_closed=False,
            source_candidate_count=0,
            offhours_planning_enabled=False,
            executable_count=0,
            runtime_health_quiet=False,
            high_frequency_loop_active=False,
            max_offhours_loop_frequency_hz=max_loop_hz,
            metadata={"blocked_before_consistency_check": True},
        )

    feed_payload = _payload_or_none(feed_runtime) or {}
    top_payload = _payload_or_none(top_opportunities) or {}
    health_payload = _payload_or_none(runtime_health) or {}
    feed_market_open = _first_optional_bool(feed_payload, _MARKET_OPEN_KEYS)
    feed_warning = _has_freshness_warning(feed_payload)
    top_state = _first_text(top_payload, _MARKET_STATE_KEYS)
    top_state_closed = _is_closed_or_offhours(top_state)
    source_candidate_count = _first_non_negative_int(top_payload, _SOURCE_COUNT_KEYS)
    executable_count = _first_non_negative_int(top_payload, _EXECUTABLE_COUNT_KEYS)
    offhours_planning_enabled = _any_true(top_payload, _OFFHOURS_ALLOWED_KEYS)
    runtime_health_quiet = _runtime_health_is_quiet(health_payload)
    high_frequency_loop_active = _high_frequency_loop_active(health_payload, max_loop_hz)

    if market_open is True:
        return _report(
            status=MARKET_CLOSE_STATUS_NOT_APPLICABLE,
            reason_code=MARKET_OPEN_TRUE_REASON,
            reasons=(MARKET_OPEN_TRUE_REASON,),
            market_open=True,
            expected_market_state="MARKET_OPEN",
            feed_market_open=feed_market_open,
            feed_freshness_warning_present=feed_warning,
            top_market_state=top_state,
            top_market_state_closed=top_state_closed,
            source_candidate_count=source_candidate_count,
            offhours_planning_enabled=offhours_planning_enabled,
            executable_count=executable_count,
            runtime_health_quiet=runtime_health_quiet,
            high_frequency_loop_active=high_frequency_loop_active,
            max_offhours_loop_frequency_hz=max_loop_hz,
            metadata={"close_state_required": False, "evidence_only_no_runtime_change": True},
        )

    reasons: list[str] = []
    if feed_market_open is True and not feed_warning:
        reasons.append(FEED_MARKET_OPEN_CONFLICT_REASON)
    if not top_state:
        reasons.append(TOP_MARKET_STATE_MISSING_REASON)
    elif not top_state_closed:
        reasons.append(TOP_MARKET_STATE_NOT_CLOSED_REASON)
    if source_candidate_count > 0 and not offhours_planning_enabled:
        reasons.append(SOURCE_CANDIDATES_NOT_QUIET_REASON)
    if executable_count > 0:
        reasons.append(EXECUTABLES_NOT_ZERO_REASON)
    if not runtime_health_quiet:
        reasons.append(RUNTIME_HEALTH_NOT_QUIET_REASON)
    if high_frequency_loop_active:
        reasons.append(HIGH_FREQUENCY_LOOP_ACTIVE_REASON)

    status = MARKET_CLOSE_STATUS_INCONSISTENT if reasons else MARKET_CLOSE_STATUS_CONSISTENT
    if not reasons:
        reasons.append(CLOSE_STATE_OK_REASON)
    return _report(
        status=status,
        reason_code=reasons[0],
        reasons=tuple(reasons),
        market_open=False,
        expected_market_state="MARKET_CLOSED/OFFHOURS",
        feed_market_open=feed_market_open,
        feed_freshness_warning_present=feed_warning,
        top_market_state=top_state,
        top_market_state_closed=top_state_closed,
        source_candidate_count=source_candidate_count,
        offhours_planning_enabled=offhours_planning_enabled,
        executable_count=executable_count,
        runtime_health_quiet=runtime_health_quiet,
        high_frequency_loop_active=high_frequency_loop_active,
        max_offhours_loop_frequency_hz=max_loop_hz,
        metadata={
            "close_state_required": True,
            "evidence_only_no_runtime_change": True,
            "feed_runtime_present": bool(feed_payload),
            "top_opportunities_present": bool(top_payload),
            "runtime_health_present": bool(health_payload),
        },
    )


def write_market_close_state_consistency_evidence(
    report: MarketCloseStateConsistencyReport,
    path: str | Path,
) -> Path:
    """Write market-close consistency evidence."""

    return write_json_atomic(Path(path).expanduser(), report.to_payload())


def _report(**kwargs: Any) -> MarketCloseStateConsistencyReport:
    reasons = tuple(str(reason) for reason in kwargs.get("reasons", ()))
    kwargs["reasons"] = reasons
    kwargs["violation_count"] = 0 if kwargs.get("status") in {MARKET_CLOSE_STATUS_CONSISTENT, MARKET_CLOSE_STATUS_NOT_APPLICABLE} else len(reasons)
    return MarketCloseStateConsistencyReport(
        schema_version=MARKET_CLOSE_STATE_SCHEMA_VERSION,
        source=MARKET_CLOSE_STATE_SOURCE,
        **kwargs,
    )


def _payload_or_none(value: Mapping[str, Any] | Any | None) -> dict[str, Any] | None:
    if hasattr(value, "to_payload"):
        try:
            value = value.to_payload()
        except Exception:
            return None
    if isinstance(value, Mapping):
        return dict(value)
    return None


def _first_optional_bool(payload: Mapping[str, Any], keys: Sequence[str]) -> bool | None:
    for key in keys:
        if key in payload:
            parsed = _optional_bool(payload.get(key))
            if parsed is not None:
                return parsed
    return None


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "open", "active", "enabled", "running"}:
        return True
    if text in {"false", "0", "no", "n", "closed", "inactive", "disabled", "stopped"}:
        return False
    return None


def _first_text(payload: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _is_closed_or_offhours(value: str) -> bool:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    return any(token in normalized for token in _MARKET_CLOSED_TOKENS)


def _first_non_negative_int(payload: Mapping[str, Any], keys: Sequence[str]) -> int:
    for key in keys:
        if key not in payload:
            continue
        parsed = _optional_int(payload.get(key))
        if parsed is not None:
            return parsed
    return 0


def _optional_int(value: Any) -> int | None:
    try:
        out = int(value)
    except (TypeError, ValueError):
        return None
    return out if out >= 0 else None


def _any_true(payload: Mapping[str, Any], keys: Sequence[str]) -> bool:
    return any(_optional_bool(payload.get(key)) is True for key in keys if key in payload)


def _runtime_health_is_quiet(payload: Mapping[str, Any]) -> bool:
    if not payload:
        return False
    if _any_true(payload, _QUIET_BOOL_KEYS):
        return True
    state = _first_text(payload, _MARKET_STATE_KEYS + ("mode", "runtime_mode"))
    normalized = state.strip().lower().replace("-", "_").replace(" ", "_")
    return any(token in normalized for token in _QUIET_TOKENS)


def _high_frequency_loop_active(payload: Mapping[str, Any], max_loop_hz: float) -> bool:
    if not payload:
        return False
    if _any_true(payload, _LOOP_ACTIVE_KEYS):
        return True
    for key in _LOOP_FREQUENCY_KEYS:
        frequency = _optional_float(payload.get(key))
        if frequency is not None and frequency > max_loop_hz:
            return True
    return False


def _has_freshness_warning(payload: Mapping[str, Any]) -> bool:
    for key in _FRESHNESS_WARNING_KEYS:
        if key not in payload:
            continue
        value = payload.get(key)
        if isinstance(value, (list, tuple, set, frozenset)):
            joined = " ".join(str(item).lower() for item in value)
        else:
            joined = str(value).lower()
        if any(token in joined for token in ("stale", "warning", "freshness", "old", "expired")):
            return True
    return False


def _optional_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out


def _non_negative_float(value: Any, default: float) -> float:
    parsed = _optional_float(value)
    return default if parsed is None or parsed < 0 else parsed


def _mark_non_action(payload: dict[str, Any]) -> None:
    payload["read_only"] = True
    payload["append"] = False
    payload[_ACTION_KEY] = False
    payload[_BROKER_KEY] = False
    payload[_LIVE_ACTION_KEY] = False
    payload[_BROKER_ACTION_KEY] = False


__all__ = [
    "CLOSE_STATE_OK_REASON",
    "DEFAULT_MAX_OFFHOURS_LOOP_FREQUENCY_HZ",
    "EXECUTABLES_NOT_ZERO_REASON",
    "FEED_MARKET_OPEN_CONFLICT_REASON",
    "HIGH_FREQUENCY_LOOP_ACTIVE_REASON",
    "INVALID_MARKET_SNAPSHOT_REASON",
    "MARKET_CLOSE_STATE_SCHEMA_VERSION",
    "MARKET_CLOSE_STATE_SOURCE",
    "MARKET_CLOSE_STATUS_BLOCKED",
    "MARKET_CLOSE_STATUS_CONSISTENT",
    "MARKET_CLOSE_STATUS_INCONSISTENT",
    "MARKET_CLOSE_STATUS_NOT_APPLICABLE",
    "MARKET_OPEN_TRUE_REASON",
    "MISSING_MARKET_OPEN_REASON",
    "MarketCloseStateConsistencyReport",
    "RUNTIME_HEALTH_NOT_QUIET_REASON",
    "SOURCE_CANDIDATES_NOT_QUIET_REASON",
    "TOP_MARKET_STATE_MISSING_REASON",
    "TOP_MARKET_STATE_NOT_CLOSED_REASON",
    "build_market_close_state_consistency_report",
    "write_market_close_state_consistency_evidence",
]
