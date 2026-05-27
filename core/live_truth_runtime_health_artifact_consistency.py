"""Runtime health artifact consistency evidence for LIVE-TRUTH-09.

This reducer compares latest runtime-health artifacts and reports whether they
agree on core runtime truth fields. It is read-only and does not wire into live
runtime, feeds, candidates, ranking, scoring, lifecycle state, or execution.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.events import write_json_atomic

RUNTIME_HEALTH_ARTIFACT_CONSISTENCY_SCHEMA_VERSION = 1
RUNTIME_HEALTH_ARTIFACT_CONSISTENCY_SOURCE = "live_truth_runtime_health_artifact_consistency_v1"

CONSISTENCY_STATUS_CONSISTENT = "RUNTIME_HEALTH_ARTIFACTS_CONSISTENT"
CONSISTENCY_STATUS_REVIEW = "RUNTIME_HEALTH_ARTIFACTS_REVIEW"
CONSISTENCY_STATUS_INCONSISTENT = "RUNTIME_HEALTH_ARTIFACTS_INCONSISTENT"
CONSISTENCY_STATUS_BLOCKED = "RUNTIME_HEALTH_ARTIFACTS_BLOCKED"

CONSISTENT_REASON = "runtime_health_artifacts_consistent"
NO_ARTIFACTS_REASON = "no_runtime_health_artifacts"
INVALID_ARTIFACT_REASON = "invalid_runtime_health_artifact"
INVALID_CONFIG_REASON = "invalid_runtime_health_artifact_consistency_config"
MISSING_REQUIRED_ARTIFACT_REASON = "missing_required_runtime_health_artifact"
MISSING_IDENTITY_FIELD_REASON = "missing_runtime_health_identity_field"
INCONSISTENT_RUNTIME_MODE_REASON = "inconsistent_runtime_mode"
INCONSISTENT_MARKET_OPEN_REASON = "inconsistent_market_open"
INCONSISTENT_RUNTIME_STATE_REASON = "inconsistent_runtime_state"
INCONSISTENT_FEED_OK_REASON = "inconsistent_feed_ok"
INCONSISTENT_WS_CONNECTED_REASON = "inconsistent_ws_connected"

DEFAULT_REQUIRED_FIELDS = ("runtime_mode", "market_open", "runtime_state")

_MODE_KEYS = ("runtime_mode", "mode", "session_mode", "trading_mode")
_MARKET_OPEN_KEYS = ("market_open", "is_market_open")
_RUNTIME_STATE_KEYS = ("runtime_state", "state", "runtime_status", "status")
_FEED_OK_KEYS = ("feed_ok", "feed_healthy", "feed_health_ok", "is_feed_ok")
_WS_CONNECTED_KEYS = ("ws_connected", "websocket_connected", "websocket_ok", "is_ws_connected")

_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"
_LIVE_ACTION_KEY = "live_" + "order_action"
_BROKER_ACTION_KEY = "broker_" + "order_action"


@dataclass(frozen=True)
class RuntimeHealthArtifactObservation:
    artifact_name: str
    valid: bool
    reason_code: str
    runtime_mode: str | None
    market_open: bool | None
    runtime_state: str | None
    feed_ok: bool | None
    ws_connected: bool | None
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "valid": self.valid,
            "reason_code": self.reason_code,
            "runtime_mode": self.runtime_mode,
            "market_open": self.market_open,
            "runtime_state": self.runtime_state,
            "feed_ok": self.feed_ok,
            "ws_connected": self.ws_connected,
            "source": self.source,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RuntimeHealthArtifactConsistencyReport:
    schema_version: int
    source: str
    status: str
    reason_code: str
    reasons: tuple[str, ...]
    artifact_count: int
    valid_artifact_count: int
    missing_required_artifacts: tuple[str, ...]
    inconsistent_fields: tuple[str, ...]
    field_values: dict[str, tuple[Any, ...]]
    observations: tuple[RuntimeHealthArtifactObservation, ...]
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
            "artifact_count": self.artifact_count,
            "valid_artifact_count": self.valid_artifact_count,
            "missing_required_artifacts": list(self.missing_required_artifacts),
            "inconsistent_fields": list(self.inconsistent_fields),
            "field_values": {key: list(values) for key, values in self.field_values.items()},
            "observations": [observation.to_payload() for observation in self.observations],
            "read_only": self.read_only,
            "append": self.append,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def build_runtime_health_artifact_consistency_report(
    artifacts: Mapping[str, Mapping[str, Any] | Any] | Mapping[str, Any] | Any,
    *,
    required_artifacts: Sequence[str] = (),
    required_fields: Sequence[str] = DEFAULT_REQUIRED_FIELDS,
) -> RuntimeHealthArtifactConsistencyReport:
    """Build read-only consistency evidence over runtime-health artifacts."""

    required_names = _normalize_required_names(required_artifacts)
    fields = _normalize_required_fields(required_fields)
    if fields is None:
        return _report(
            status=CONSISTENCY_STATUS_BLOCKED,
            reason_code=INVALID_CONFIG_REASON,
            reasons=(INVALID_CONFIG_REASON,),
            observations=(),
            missing_required_artifacts=(),
            inconsistent_fields=(),
            field_values={},
            metadata={"blocked_before_artifact_evaluation": True},
        )

    artifact_items = _extract_artifacts(artifacts)
    if not artifact_items:
        return _report(
            status=CONSISTENCY_STATUS_BLOCKED,
            reason_code=NO_ARTIFACTS_REASON,
            reasons=(NO_ARTIFACTS_REASON,),
            observations=(),
            missing_required_artifacts=required_names,
            inconsistent_fields=(),
            field_values={},
            metadata={
                "required_artifacts": list(required_names),
                "required_fields": list(fields),
                "blocked_before_artifact_evaluation": True,
            },
        )

    observed_names = tuple(sorted(str(name) for name in artifact_items))
    missing_required = tuple(name for name in required_names if name not in observed_names)
    observations = tuple(
        _parse_observation(str(name), value)
        for name, value in sorted(artifact_items.items(), key=lambda item: str(item[0]))
    )
    invalid = tuple(item for item in observations if not item.valid)
    valid = tuple(item for item in observations if item.valid)
    field_values = _field_values(valid)
    inconsistent_fields = _inconsistent_fields(field_values)
    missing_identity_fields = _missing_required_fields(valid, fields)

    reasons: list[str] = []
    if missing_required:
        reasons.append(MISSING_REQUIRED_ARTIFACT_REASON)
    if invalid:
        reasons.append(INVALID_ARTIFACT_REASON)
    if missing_identity_fields:
        reasons.append(MISSING_IDENTITY_FIELD_REASON)
    reasons.extend(_field_reason(field) for field in inconsistent_fields)

    if missing_required or invalid:
        status = CONSISTENCY_STATUS_BLOCKED
    elif inconsistent_fields:
        status = CONSISTENCY_STATUS_INCONSISTENT
    elif missing_identity_fields:
        status = CONSISTENCY_STATUS_REVIEW
    else:
        status = CONSISTENCY_STATUS_CONSISTENT
        reasons.append(CONSISTENT_REASON)

    deduped = _dedupe_preserve_order(reasons)
    return _report(
        status=status,
        reason_code=deduped[0],
        reasons=deduped,
        observations=observations,
        missing_required_artifacts=missing_required,
        inconsistent_fields=inconsistent_fields,
        field_values=field_values,
        metadata={
            "required_artifacts": list(required_names),
            "observed_artifacts": list(observed_names),
            "required_fields": list(fields),
            "missing_required_fields": list(missing_identity_fields),
            "evidence_only_no_runtime_change": True,
        },
    )


def write_runtime_health_artifact_consistency_evidence(
    report: RuntimeHealthArtifactConsistencyReport,
    path: str | Path,
) -> Path:
    """Write runtime-health artifact consistency evidence."""

    target = Path(path).expanduser()
    write_json_atomic(target, report.to_payload())
    return target


def _report(
    *,
    status: str,
    reason_code: str,
    reasons: tuple[str, ...],
    observations: tuple[RuntimeHealthArtifactObservation, ...],
    missing_required_artifacts: tuple[str, ...],
    inconsistent_fields: tuple[str, ...],
    field_values: Mapping[str, tuple[Any, ...]],
    metadata: dict[str, Any] | None = None,
) -> RuntimeHealthArtifactConsistencyReport:
    valid_count = sum(1 for item in observations if item.valid)
    return RuntimeHealthArtifactConsistencyReport(
        schema_version=RUNTIME_HEALTH_ARTIFACT_CONSISTENCY_SCHEMA_VERSION,
        source=RUNTIME_HEALTH_ARTIFACT_CONSISTENCY_SOURCE,
        status=status,
        reason_code=reason_code,
        reasons=reasons,
        artifact_count=len(observations),
        valid_artifact_count=valid_count,
        missing_required_artifacts=missing_required_artifacts,
        inconsistent_fields=inconsistent_fields,
        field_values={str(key): tuple(values) for key, values in field_values.items()},
        observations=observations,
        metadata=dict(metadata or {}),
    )


def _extract_artifacts(value: Mapping[str, Any] | Any) -> dict[str, Any]:
    payload = _payload_or_none(value)
    if payload is None:
        return {}

    for key in ("artifacts", "runtime_health_artifacts", "health_artifacts", "snapshots", "latest_artifacts"):
        nested = payload.get(key)
        if isinstance(nested, Mapping):
            return {str(name): item for name, item in nested.items()}

    return {str(name): item for name, item in payload.items()}


def _parse_observation(name: str, value: Mapping[str, Any] | Any) -> RuntimeHealthArtifactObservation:
    payload = _payload_or_none(value)
    if payload is None:
        return RuntimeHealthArtifactObservation(
            artifact_name=name,
            valid=False,
            reason_code=INVALID_ARTIFACT_REASON,
            runtime_mode=None,
            market_open=None,
            runtime_state=None,
            feed_ok=None,
            ws_connected=None,
            source="",
            metadata={"blocked_before_field_extraction": True},
        )

    return RuntimeHealthArtifactObservation(
        artifact_name=name,
        valid=True,
        reason_code=CONSISTENT_REASON,
        runtime_mode=_normalize_text(_first_present(payload, _MODE_KEYS)),
        market_open=_optional_bool(_first_present(payload, _MARKET_OPEN_KEYS)),
        runtime_state=_normalize_text(_first_present(payload, _RUNTIME_STATE_KEYS)),
        feed_ok=_optional_bool(_first_present(payload, _FEED_OK_KEYS)),
        ws_connected=_optional_bool(_first_present(payload, _WS_CONNECTED_KEYS)),
        source=str(payload.get("source") or ""),
        metadata={
            "available_identity_fields": sorted(
                key
                for key in (
                    *_MODE_KEYS,
                    *_MARKET_OPEN_KEYS,
                    *_RUNTIME_STATE_KEYS,
                    *_FEED_OK_KEYS,
                    *_WS_CONNECTED_KEYS,
                )
                if key in payload
            )
        },
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


def _first_present(payload: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in payload and payload.get(key) is not None and str(payload.get(key)).strip():
            return payload.get(key)
    return None


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    return text or None


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "healthy", "connected", "open", "ok"}:
        return True
    if text in {"false", "0", "no", "n", "unhealthy", "disconnected", "closed", "not_ok"}:
        return False
    return None


def _field_values(observations: Sequence[RuntimeHealthArtifactObservation]) -> dict[str, tuple[Any, ...]]:
    return {
        "runtime_mode": _unique_present(item.runtime_mode for item in observations),
        "market_open": _unique_present(item.market_open for item in observations),
        "runtime_state": _unique_present(item.runtime_state for item in observations),
        "feed_ok": _unique_present(item.feed_ok for item in observations),
        "ws_connected": _unique_present(item.ws_connected for item in observations),
    }


def _unique_present(values: Any) -> tuple[Any, ...]:
    out: list[Any] = []
    for value in values:
        if value is None:
            continue
        if value not in out:
            out.append(value)
    return tuple(out)


def _inconsistent_fields(values_by_field: Mapping[str, tuple[Any, ...]]) -> tuple[str, ...]:
    return tuple(
        field
        for field in ("runtime_mode", "market_open", "runtime_state", "feed_ok", "ws_connected")
        if len(values_by_field.get(field, ())) > 1
    )


def _missing_required_fields(
    observations: Sequence[RuntimeHealthArtifactObservation],
    required_fields: Sequence[str],
) -> tuple[str, ...]:
    missing: list[str] = []
    for observation in observations:
        for field in required_fields:
            if getattr(observation, field) is None:
                missing.append(f"{observation.artifact_name}:{field}")
    return tuple(missing)


def _field_reason(field: str) -> str:
    return {
        "runtime_mode": INCONSISTENT_RUNTIME_MODE_REASON,
        "market_open": INCONSISTENT_MARKET_OPEN_REASON,
        "runtime_state": INCONSISTENT_RUNTIME_STATE_REASON,
        "feed_ok": INCONSISTENT_FEED_OK_REASON,
        "ws_connected": INCONSISTENT_WS_CONNECTED_REASON,
    }.get(field, MISSING_IDENTITY_FIELD_REASON)


def _normalize_required_names(values: Sequence[str]) -> tuple[str, ...]:
    return _dedupe_preserve_order(str(value).strip() for value in values if str(value).strip())


def _normalize_required_fields(values: Sequence[str]) -> tuple[str, ...] | None:
    allowed = {"runtime_mode", "market_open", "runtime_state", "feed_ok", "ws_connected"}
    normalized = _dedupe_preserve_order(
        str(value).strip().lower().replace("-", "_").replace(" ", "_")
        for value in values
        if str(value).strip()
    )
    if not normalized or any(value not in allowed for value in normalized):
        return None
    return normalized


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
    "CONSISTENCY_STATUS_BLOCKED",
    "CONSISTENCY_STATUS_CONSISTENT",
    "CONSISTENCY_STATUS_INCONSISTENT",
    "CONSISTENCY_STATUS_REVIEW",
    "CONSISTENT_REASON",
    "DEFAULT_REQUIRED_FIELDS",
    "INCONSISTENT_FEED_OK_REASON",
    "INCONSISTENT_MARKET_OPEN_REASON",
    "INCONSISTENT_RUNTIME_MODE_REASON",
    "INCONSISTENT_RUNTIME_STATE_REASON",
    "INCONSISTENT_WS_CONNECTED_REASON",
    "INVALID_ARTIFACT_REASON",
    "INVALID_CONFIG_REASON",
    "MISSING_IDENTITY_FIELD_REASON",
    "MISSING_REQUIRED_ARTIFACT_REASON",
    "NO_ARTIFACTS_REASON",
    "RUNTIME_HEALTH_ARTIFACT_CONSISTENCY_SCHEMA_VERSION",
    "RUNTIME_HEALTH_ARTIFACT_CONSISTENCY_SOURCE",
    "RuntimeHealthArtifactConsistencyReport",
    "RuntimeHealthArtifactObservation",
    "build_runtime_health_artifact_consistency_report",
    "write_runtime_health_artifact_consistency_evidence",
]
