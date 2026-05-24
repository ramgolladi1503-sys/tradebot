"""Read-only freshness guard for latest runtime/report artifacts."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

LATEST_ARTIFACT_FRESHNESS_SCHEMA_VERSION = 1

FRESH_STATUS = "fresh"
STALE_STATUS = "stale"
MISSING_STATUS = "missing"
INVALID_STATUS = "invalid"
FUTURE_STATUS = "future_timestamp"
UNKNOWN_STATUS = "unknown_timestamp"

DEFAULT_MAX_AGE_SECONDS = 120.0
DEFAULT_FUTURE_TOLERANCE_SECONDS = 5.0
_TIMESTAMP_FIELDS = (
    "generated_epoch",
    "updated_epoch",
    "created_epoch",
    "timestamp_epoch",
    "epoch",
)


@dataclass(frozen=True)
class LatestArtifactFreshnessDecision:
    artifact_name: str
    path: str | None
    status: str
    fresh: bool = False
    age_seconds: float | None = None
    max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS
    timestamp_source: str | None = None
    reasons: tuple[str, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LatestArtifactFreshnessReport:
    is_order_action = False
    broker_api_called = False
    live_order_action = False
    broker_order_action = False

    schema_version: int
    read_only: bool
    artifact_count: int
    fresh_count: int
    stale_count: int
    missing_count: int
    invalid_count: int
    decisions: tuple[LatestArtifactFreshnessDecision, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "is_order_action": False,
            "broker_api_called": False,
            "live_order_action": False,
            "broker_order_action": False,
            "artifact_count": self.artifact_count,
            "fresh_count": self.fresh_count,
            "stale_count": self.stale_count,
            "missing_count": self.missing_count,
            "invalid_count": self.invalid_count,
            "decisions": [decision.to_payload() for decision in self.decisions],
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def assess_latest_artifact_freshness(
    artifact_name: str,
    *,
    path: str | Path | None = None,
    payload: Mapping[str, Any] | None = None,
    now_epoch: float | None = None,
    max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
    future_tolerance_seconds: float = DEFAULT_FUTURE_TOLERANCE_SECONDS,
) -> LatestArtifactFreshnessDecision:
    """Assess one latest artifact without mutating runtime state."""
    now = _safe_float(now_epoch, default=time.time())
    normalized_max_age = max(0.0, _safe_float(max_age_seconds, default=DEFAULT_MAX_AGE_SECONDS))
    normalized_future_tolerance = max(
        0.0,
        _safe_float(future_tolerance_seconds, default=DEFAULT_FUTURE_TOLERANCE_SECONDS),
    )
    normalized_path = str(path) if path is not None else None

    if payload is None:
        if path is None:
            return _decision(
                artifact_name,
                normalized_path,
                MISSING_STATUS,
                normalized_max_age,
                reasons=("artifact_payload_and_path_missing",),
            )
        loaded_payload, load_reason = _load_payload(path)
        if loaded_payload is None:
            status = MISSING_STATUS if load_reason == "artifact_path_missing" else INVALID_STATUS
            return _decision(
                artifact_name,
                normalized_path,
                status,
                normalized_max_age,
                reasons=(load_reason,),
            )
        payload = loaded_payload

    timestamp, timestamp_source = _extract_timestamp(payload)
    if timestamp is None:
        return _decision(
            artifact_name,
            normalized_path,
            UNKNOWN_STATUS,
            normalized_max_age,
            reasons=("artifact_timestamp_missing",),
        )

    age = round(now - timestamp, 6)
    if age < -normalized_future_tolerance:
        return _decision(
            artifact_name,
            normalized_path,
            FUTURE_STATUS,
            normalized_max_age,
            age_seconds=age,
            timestamp_source=timestamp_source,
            reasons=("artifact_timestamp_in_future",),
        )
    if age > normalized_max_age:
        return _decision(
            artifact_name,
            normalized_path,
            STALE_STATUS,
            normalized_max_age,
            age_seconds=age,
            timestamp_source=timestamp_source,
            reasons=("artifact_age_exceeds_max_age",),
        )
    return _decision(
        artifact_name,
        normalized_path,
        FRESH_STATUS,
        normalized_max_age,
        fresh=True,
        age_seconds=max(0.0, age),
        timestamp_source=timestamp_source,
        reasons=("artifact_fresh",),
    )


def assess_latest_artifacts_freshness(
    artifacts: Mapping[str, Mapping[str, Any] | str | Path | None],
    *,
    now_epoch: float | None = None,
    max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
) -> LatestArtifactFreshnessReport:
    """Assess a mapping of artifact names to payloads or paths."""
    decisions = tuple(
        assess_latest_artifact_freshness(
            name,
            path=value if isinstance(value, (str, Path)) else None,
            payload=value if isinstance(value, Mapping) else None,
            now_epoch=now_epoch,
            max_age_seconds=max_age_seconds,
        )
        for name, value in artifacts.items()
    )
    blockers = tuple(sorted({reason for decision in decisions if not decision.fresh for reason in decision.reasons}))
    warnings = tuple(sorted({reason for decision in decisions if decision.status in {UNKNOWN_STATUS, FUTURE_STATUS} for reason in decision.reasons}))
    return LatestArtifactFreshnessReport(
        schema_version=LATEST_ARTIFACT_FRESHNESS_SCHEMA_VERSION,
        read_only=True,
        artifact_count=len(decisions),
        fresh_count=sum(1 for decision in decisions if decision.status == FRESH_STATUS),
        stale_count=sum(1 for decision in decisions if decision.status == STALE_STATUS),
        missing_count=sum(1 for decision in decisions if decision.status == MISSING_STATUS),
        invalid_count=sum(1 for decision in decisions if decision.status == INVALID_STATUS),
        decisions=decisions,
        blockers=blockers,
        warnings=warnings,
        metadata={
            "freshness_guard": "latest_artifact_freshness_guard_v1",
            "scope": "read_only_no_runtime_mutation",
            "max_age_seconds": max_age_seconds,
            "is_order_action": False,
            "broker_api_called": False,
            "live_order_action": False,
            "broker_order_action": False,
        },
        generated_epoch=_safe_float(now_epoch, default=time.time()),
    )


def _decision(
    artifact_name: str,
    path: str | None,
    status: str,
    max_age_seconds: float,
    *,
    fresh: bool = False,
    age_seconds: float | None = None,
    timestamp_source: str | None = None,
    reasons: tuple[str, ...],
) -> LatestArtifactFreshnessDecision:
    return LatestArtifactFreshnessDecision(
        artifact_name=str(artifact_name),
        path=path,
        status=status,
        fresh=bool(fresh),
        age_seconds=age_seconds,
        max_age_seconds=max_age_seconds,
        timestamp_source=timestamp_source,
        reasons=reasons,
        context={
            "contract_version": "edge50.v1",
            "is_order_action": False,
            "broker_api_called": False,
            "live_order_action": False,
            "broker_order_action": False,
        },
    )


def _load_payload(path: str | Path) -> tuple[Mapping[str, Any] | None, str]:
    artifact_path = Path(path)
    if not artifact_path.exists() or not artifact_path.is_file():
        return None, "artifact_path_missing"
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None, "artifact_payload_invalid_json"
    if not isinstance(payload, Mapping):
        return None, "artifact_payload_not_object"
    return payload, "artifact_payload_loaded"


def _extract_timestamp(payload: Mapping[str, Any]) -> tuple[float | None, str | None]:
    for field in _TIMESTAMP_FIELDS:
        value = payload.get(field)
        if value is None:
            continue
        timestamp = _safe_float(value, default=None)
        if timestamp is not None:
            return timestamp, field
    nested = payload.get("metadata")
    if isinstance(nested, Mapping):
        for field in _TIMESTAMP_FIELDS:
            value = nested.get(field)
            if value is None:
                continue
            timestamp = _safe_float(value, default=None)
            if timestamp is not None:
                return timestamp, f"metadata.{field}"
    return None, None


def _safe_float(value: Any, *, default: float | None) -> float | None:
    try:
        if value in (None, "", "None"):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


__all__ = [
    "DEFAULT_MAX_AGE_SECONDS",
    "FRESH_STATUS",
    "FUTURE_STATUS",
    "INVALID_STATUS",
    "LATEST_ARTIFACT_FRESHNESS_SCHEMA_VERSION",
    "MISSING_STATUS",
    "STALE_STATUS",
    "UNKNOWN_STATUS",
    "LatestArtifactFreshnessDecision",
    "LatestArtifactFreshnessReport",
    "assess_latest_artifact_freshness",
    "assess_latest_artifacts_freshness",
]
