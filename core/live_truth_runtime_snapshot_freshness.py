"""Runtime snapshot freshness guard for LIVE-TRUTH-03.

This module validates that latest runtime evidence snapshots are recent enough to
be trusted. It is read-only: it does not refresh feeds, mutate runtime state,
create candidates, score candidates, or change execution behavior.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.events import write_json_atomic

RUNTIME_SNAPSHOT_FRESHNESS_SCHEMA_VERSION = 1
RUNTIME_SNAPSHOT_FRESHNESS_SOURCE = "live_truth_runtime_snapshot_freshness_v1"

FRESHNESS_STATUS_FRESH = "RUNTIME_SNAPSHOT_FRESH"
FRESHNESS_STATUS_STALE = "RUNTIME_SNAPSHOT_STALE"
FRESHNESS_STATUS_BLOCKED = "RUNTIME_SNAPSHOT_FRESHNESS_BLOCKED"

FRESH_REASON = "ok"
NO_SNAPSHOTS_REASON = "no_runtime_snapshots"
INVALID_SNAPSHOT_REASON = "invalid_runtime_snapshot"
MISSING_TIMESTAMP_REASON = "missing_runtime_snapshot_timestamp"
FUTURE_TIMESTAMP_REASON = "runtime_snapshot_timestamp_in_future"
STALE_TIMESTAMP_REASON = "runtime_snapshot_stale"
INVALID_FRESHNESS_CONFIG_REASON = "invalid_freshness_config"

DEFAULT_MAX_AGE_SEC = 60.0
DEFAULT_FUTURE_SKEW_TOLERANCE_SEC = 5.0

_TIMESTAMP_KEYS = (
    "generated_epoch",
    "updated_epoch",
    "last_update_epoch",
    "last_updated_epoch",
    "timestamp_epoch",
    "ts_epoch",
    "written_epoch",
    "asof_epoch",
    "as_of_epoch",
    "generated_at",
    "updated_at",
    "last_update_at",
    "last_updated_at",
    "timestamp",
    "ts",
)

_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"
_LIVE_ACTION_KEY = "live_" + "order_action"
_BROKER_ACTION_KEY = "broker_" + "order_action"


@dataclass(frozen=True)
class RuntimeSnapshotFreshnessArtifact:
    """Freshness result for one runtime snapshot artifact."""

    artifact_name: str
    valid: bool
    freshness_state: str
    reason_code: str
    timestamp_epoch: float | None
    timestamp_key: str | None
    age_sec: float | None
    max_age_sec: float
    market_open: bool | None = None
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "valid": self.valid,
            "freshness_state": self.freshness_state,
            "reason_code": self.reason_code,
            "timestamp_epoch": self.timestamp_epoch,
            "timestamp_key": self.timestamp_key,
            "age_sec": self.age_sec,
            "max_age_sec": self.max_age_sec,
            "market_open": self.market_open,
            "source": self.source,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RuntimeSnapshotFreshnessReport:
    """Read-only report over latest runtime snapshot freshness."""

    schema_version: int
    source: str
    status: str
    reason_code: str
    reasons: tuple[str, ...]
    now_epoch: float
    artifact_count: int
    fresh_count: int
    stale_count: int
    blocked_count: int
    artifacts: tuple[RuntimeSnapshotFreshnessArtifact, ...]
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
            "artifact_count": self.artifact_count,
            "fresh_count": self.fresh_count,
            "stale_count": self.stale_count,
            "blocked_count": self.blocked_count,
            "artifacts": [artifact.to_payload() for artifact in self.artifacts],
            "read_only": self.read_only,
            "append": self.append,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def build_runtime_snapshot_freshness_report(
    snapshots: Mapping[str, Mapping[str, Any] | Any],
    *,
    now_epoch: float,
    default_max_age_sec: float = DEFAULT_MAX_AGE_SEC,
    max_age_by_artifact: Mapping[str, float] | None = None,
    future_skew_tolerance_sec: float = DEFAULT_FUTURE_SKEW_TOLERANCE_SEC,
) -> RuntimeSnapshotFreshnessReport:
    """Build read-only freshness evidence for runtime snapshot artifacts."""

    now = _finite_float_or_none(now_epoch)
    default_age = _positive_float_or_none(default_max_age_sec)
    future_skew = _non_negative_float_or_none(future_skew_tolerance_sec)
    if now is None or default_age is None or future_skew is None:
        return _report(
            status=FRESHNESS_STATUS_BLOCKED,
            reason_code=INVALID_FRESHNESS_CONFIG_REASON,
            reasons=(INVALID_FRESHNESS_CONFIG_REASON,),
            now_epoch=0.0 if now is None else now,
            artifacts=(),
            metadata={"blocked_before_snapshot_evaluation": True},
        )

    if not isinstance(snapshots, Mapping) or not snapshots:
        return _report(
            status=FRESHNESS_STATUS_BLOCKED,
            reason_code=NO_SNAPSHOTS_REASON,
            reasons=(NO_SNAPSHOTS_REASON,),
            now_epoch=now,
            artifacts=(),
            metadata={"blocked_before_snapshot_evaluation": True},
        )

    age_overrides = dict(max_age_by_artifact or {})
    artifacts = tuple(
        _evaluate_artifact(
            artifact_name=str(name),
            snapshot=value,
            now_epoch=now,
            max_age_sec=_max_age_for(str(name), default_age, age_overrides),
            future_skew_tolerance_sec=future_skew,
        )
        for name, value in sorted(snapshots.items(), key=lambda item: str(item[0]))
    )
    blocked = tuple(item for item in artifacts if item.freshness_state == FRESHNESS_STATUS_BLOCKED)
    stale = tuple(item for item in artifacts if item.freshness_state == FRESHNESS_STATUS_STALE)
    fresh = tuple(item for item in artifacts if item.freshness_state == FRESHNESS_STATUS_FRESH)
    reasons = _dedupe_preserve_order(item.reason_code for item in artifacts if item.reason_code != FRESH_REASON)
    if blocked:
        status = FRESHNESS_STATUS_BLOCKED
    elif stale:
        status = FRESHNESS_STATUS_STALE
    else:
        status = FRESHNESS_STATUS_FRESH
    return _report(
        status=status,
        reason_code=reasons[0] if reasons else FRESH_REASON,
        reasons=reasons,
        now_epoch=now,
        artifacts=artifacts,
        metadata={
            "default_max_age_sec": default_age,
            "future_skew_tolerance_sec": future_skew,
            "evaluated_artifacts": [item.artifact_name for item in artifacts],
            "evidence_only_no_runtime_change": True,
        },
    )


def write_runtime_snapshot_freshness_evidence(
    report: RuntimeSnapshotFreshnessReport,
    path: str | Path,
) -> Path:
    """Write a runtime freshness report as read-only evidence."""

    return write_json_atomic(Path(path).expanduser(), report.to_payload())


def _evaluate_artifact(
    *,
    artifact_name: str,
    snapshot: Mapping[str, Any] | Any,
    now_epoch: float,
    max_age_sec: float,
    future_skew_tolerance_sec: float,
) -> RuntimeSnapshotFreshnessArtifact:
    payload = _payload_or_none(snapshot)
    if payload is None:
        return RuntimeSnapshotFreshnessArtifact(
            artifact_name=artifact_name,
            valid=False,
            freshness_state=FRESHNESS_STATUS_BLOCKED,
            reason_code=INVALID_SNAPSHOT_REASON,
            timestamp_epoch=None,
            timestamp_key=None,
            age_sec=None,
            max_age_sec=max_age_sec,
            metadata={"blocked_before_timestamp_check": True},
        )
    timestamp_key, timestamp_epoch = _timestamp_from_payload(payload)
    if timestamp_epoch is None:
        return RuntimeSnapshotFreshnessArtifact(
            artifact_name=artifact_name,
            valid=False,
            freshness_state=FRESHNESS_STATUS_BLOCKED,
            reason_code=MISSING_TIMESTAMP_REASON,
            timestamp_epoch=None,
            timestamp_key=None,
            age_sec=None,
            max_age_sec=max_age_sec,
            market_open=_optional_bool(payload.get("market_open")),
            source=str(payload.get("source") or ""),
        )
    age_sec = round(now_epoch - timestamp_epoch, 6)
    if age_sec < -future_skew_tolerance_sec:
        return RuntimeSnapshotFreshnessArtifact(
            artifact_name=artifact_name,
            valid=False,
            freshness_state=FRESHNESS_STATUS_BLOCKED,
            reason_code=FUTURE_TIMESTAMP_REASON,
            timestamp_epoch=timestamp_epoch,
            timestamp_key=timestamp_key,
            age_sec=age_sec,
            max_age_sec=max_age_sec,
            market_open=_optional_bool(payload.get("market_open")),
            source=str(payload.get("source") or ""),
        )
    if age_sec > max_age_sec:
        return RuntimeSnapshotFreshnessArtifact(
            artifact_name=artifact_name,
            valid=True,
            freshness_state=FRESHNESS_STATUS_STALE,
            reason_code=STALE_TIMESTAMP_REASON,
            timestamp_epoch=timestamp_epoch,
            timestamp_key=timestamp_key,
            age_sec=age_sec,
            max_age_sec=max_age_sec,
            market_open=_optional_bool(payload.get("market_open")),
            source=str(payload.get("source") or ""),
        )
    return RuntimeSnapshotFreshnessArtifact(
        artifact_name=artifact_name,
        valid=True,
        freshness_state=FRESHNESS_STATUS_FRESH,
        reason_code=FRESH_REASON,
        timestamp_epoch=timestamp_epoch,
        timestamp_key=timestamp_key,
        age_sec=max(0.0, age_sec),
        max_age_sec=max_age_sec,
        market_open=_optional_bool(payload.get("market_open")),
        source=str(payload.get("source") or ""),
    )


def _report(
    *,
    status: str,
    reason_code: str,
    reasons: tuple[str, ...],
    now_epoch: float,
    artifacts: tuple[RuntimeSnapshotFreshnessArtifact, ...],
    metadata: dict[str, Any] | None = None,
) -> RuntimeSnapshotFreshnessReport:
    fresh_count = sum(1 for item in artifacts if item.freshness_state == FRESHNESS_STATUS_FRESH)
    stale_count = sum(1 for item in artifacts if item.freshness_state == FRESHNESS_STATUS_STALE)
    blocked_count = sum(1 for item in artifacts if item.freshness_state == FRESHNESS_STATUS_BLOCKED)
    return RuntimeSnapshotFreshnessReport(
        schema_version=RUNTIME_SNAPSHOT_FRESHNESS_SCHEMA_VERSION,
        source=RUNTIME_SNAPSHOT_FRESHNESS_SOURCE,
        status=status,
        reason_code=reason_code,
        reasons=reasons,
        now_epoch=now_epoch,
        artifact_count=len(artifacts),
        fresh_count=fresh_count,
        stale_count=stale_count,
        blocked_count=blocked_count,
        artifacts=artifacts,
        metadata=dict(metadata or {}),
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


def _timestamp_from_payload(payload: Mapping[str, Any]) -> tuple[str | None, float | None]:
    for key in _TIMESTAMP_KEYS:
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


def _max_age_for(name: str, default: float, overrides: Mapping[str, Any]) -> float:
    override = _positive_float_or_none(overrides.get(name))
    return default if override is None else override


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
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
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
    "DEFAULT_FUTURE_SKEW_TOLERANCE_SEC",
    "DEFAULT_MAX_AGE_SEC",
    "FRESHNESS_STATUS_BLOCKED",
    "FRESHNESS_STATUS_FRESH",
    "FRESHNESS_STATUS_STALE",
    "FRESH_REASON",
    "FUTURE_TIMESTAMP_REASON",
    "INVALID_FRESHNESS_CONFIG_REASON",
    "INVALID_SNAPSHOT_REASON",
    "MISSING_TIMESTAMP_REASON",
    "NO_SNAPSHOTS_REASON",
    "RUNTIME_SNAPSHOT_FRESHNESS_SCHEMA_VERSION",
    "RUNTIME_SNAPSHOT_FRESHNESS_SOURCE",
    "RuntimeSnapshotFreshnessArtifact",
    "RuntimeSnapshotFreshnessReport",
    "STALE_TIMESTAMP_REASON",
    "build_runtime_snapshot_freshness_report",
    "write_runtime_snapshot_freshness_evidence",
]
