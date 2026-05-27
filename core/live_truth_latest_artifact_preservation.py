"""Latest-artifact non-empty preservation for LIVE-TRUTH-02."""

from __future__ import annotations

import json
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.events import write_json_atomic

LATEST_ARTIFACT_PRESERVATION_SCHEMA_VERSION = 1
LATEST_ARTIFACT_PRESERVATION_SOURCE = "live_truth_latest_artifact_preservation_v1"

LATEST_ARTIFACT_STATUS_WRITTEN = "LATEST_ARTIFACT_INCOMING_WRITTEN"
LATEST_ARTIFACT_STATUS_PRESERVED = "LATEST_ARTIFACT_PREVIOUS_NON_EMPTY_PRESERVED"
LATEST_ARTIFACT_STATUS_BLOCKED = "LATEST_ARTIFACT_PRESERVATION_BLOCKED"

INVALID_INCOMING_PAYLOAD_REASON = "invalid_incoming_payload"
INCOMING_NON_EMPTY_REASON = "incoming_artifact_non_empty"
INCOMING_EMPTY_PREVIOUS_NON_EMPTY_REASON = "incoming_artifact_empty_previous_non_empty"
INCOMING_EMPTY_NO_PREVIOUS_REASON = "incoming_artifact_empty_no_previous_non_empty"
PREVIOUS_PAYLOAD_UNREADABLE_REASON = "previous_payload_unreadable"

DEFAULT_COUNT_KEYS = (
    "source_candidate_count",
    "candidate_count",
    "candidates_count",
    "ranked_total_count",
    "ranked_executable_count",
    "executable_count",
    "reportable_executable_count",
    "top_executable_count",
    "top_opportunities_executable_count",
    "top_opportunities_source_candidate_count",
    "symbol_count",
    "item_count",
    "row_count",
    "rows_count",
    "total_count",
)

DEFAULT_SEQUENCE_KEYS = (
    "candidates",
    "ranked_candidates",
    "opportunities",
    "top_opportunities",
    "items",
    "rows",
    "symbols",
)

DEFAULT_SIGNAL_KEYS = (
    "top_reportable_executable",
    "top_executable",
    "top_reportable_executable_snapshot",
    "top_executable_trace",
    "runtime_candidate_handoff_latest",
)


@dataclass(frozen=True)
class LatestArtifactPreservationDecision:
    """Decision describing whether a latest artifact write should be preserved."""

    schema_version: int
    source: str
    status: str
    reason_code: str
    reasons: tuple[str, ...]
    artifact_name: str
    incoming_payload_valid: bool
    incoming_non_empty: bool
    previous_payload_present: bool
    previous_payload_valid: bool
    previous_non_empty: bool
    write_incoming: bool
    preserved_previous: bool
    selected_payload: dict[str, Any]
    incoming_summary: dict[str, Any]
    previous_summary: dict[str, Any]
    read_only: bool = True
    append: bool = False
    generated_epoch: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "status": self.status,
            "reason_code": self.reason_code,
            "reasons": list(self.reasons),
            "artifact_name": self.artifact_name,
            "incoming_payload_valid": self.incoming_payload_valid,
            "incoming_non_empty": self.incoming_non_empty,
            "previous_payload_present": self.previous_payload_present,
            "previous_payload_valid": self.previous_payload_valid,
            "previous_non_empty": self.previous_non_empty,
            "write_incoming": self.write_incoming,
            "preserved_previous": self.preserved_previous,
            "selected_payload": dict(self.selected_payload),
            "incoming_summary": dict(self.incoming_summary),
            "previous_summary": dict(self.previous_summary),
            "read_only": self.read_only,
            "append": self.append,
            "generated_epoch": self.generated_epoch,
            "metadata": dict(self.metadata),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def build_latest_artifact_preservation_decision(
    incoming_payload: Mapping[str, Any] | Any,
    previous_payload: Mapping[str, Any] | Any | None = None,
    *,
    artifact_name: str = "latest_artifact",
    count_keys: Iterable[str] = DEFAULT_COUNT_KEYS,
    sequence_keys: Iterable[str] = DEFAULT_SEQUENCE_KEYS,
    signal_keys: Iterable[str] = DEFAULT_SIGNAL_KEYS,
    now_epoch: float | None = None,
) -> LatestArtifactPreservationDecision:
    """Decide whether an incoming latest-artifact payload may overwrite the old one."""

    generated_epoch = float(time.time() if now_epoch is None else now_epoch)
    incoming = _payload_or_none(incoming_payload)
    previous = _payload_or_none(previous_payload)
    previous_present = previous_payload is not None
    previous_valid = previous is not None if previous_present else True

    count_key_tuple = tuple(str(key) for key in count_keys)
    sequence_key_tuple = tuple(str(key) for key in sequence_keys)
    signal_key_tuple = tuple(str(key) for key in signal_keys)

    if incoming is None:
        return _decision(
            status=LATEST_ARTIFACT_STATUS_BLOCKED,
            reason_code=INVALID_INCOMING_PAYLOAD_REASON,
            reasons=(INVALID_INCOMING_PAYLOAD_REASON,),
            artifact_name=artifact_name,
            incoming_payload_valid=False,
            incoming_non_empty=False,
            previous_payload_present=previous_present,
            previous_payload_valid=previous_valid,
            previous_non_empty=_is_non_empty_artifact(previous or {}, count_key_tuple, sequence_key_tuple, signal_key_tuple),
            write_incoming=False,
            preserved_previous=False,
            selected_payload={},
            incoming_summary={},
            previous_summary=_artifact_summary(previous or {}, count_key_tuple, sequence_key_tuple, signal_key_tuple),
            generated_epoch=generated_epoch,
            metadata={"blocked_before_write": True, "evidence_only_no_runtime_change": True},
        )

    incoming_non_empty = _is_non_empty_artifact(incoming, count_key_tuple, sequence_key_tuple, signal_key_tuple)
    previous_non_empty = _is_non_empty_artifact(previous or {}, count_key_tuple, sequence_key_tuple, signal_key_tuple)
    incoming_summary = _artifact_summary(incoming, count_key_tuple, sequence_key_tuple, signal_key_tuple)
    previous_summary = _artifact_summary(previous or {}, count_key_tuple, sequence_key_tuple, signal_key_tuple)

    if incoming_non_empty:
        return _decision(
            status=LATEST_ARTIFACT_STATUS_WRITTEN,
            reason_code=INCOMING_NON_EMPTY_REASON,
            reasons=(INCOMING_NON_EMPTY_REASON,),
            artifact_name=artifact_name,
            incoming_payload_valid=True,
            incoming_non_empty=True,
            previous_payload_present=previous_present,
            previous_payload_valid=previous_valid,
            previous_non_empty=previous_non_empty,
            write_incoming=True,
            preserved_previous=False,
            selected_payload=incoming,
            incoming_summary=incoming_summary,
            previous_summary=previous_summary,
            generated_epoch=generated_epoch,
            metadata={"preservation_rule": "incoming_non_empty_replaces_previous", "evidence_only_no_runtime_change": True},
        )

    if previous_non_empty:
        reasons = [INCOMING_EMPTY_PREVIOUS_NON_EMPTY_REASON]
        if previous_present and not previous_valid:
            reasons.append(PREVIOUS_PAYLOAD_UNREADABLE_REASON)
        return _decision(
            status=LATEST_ARTIFACT_STATUS_PRESERVED,
            reason_code=INCOMING_EMPTY_PREVIOUS_NON_EMPTY_REASON,
            reasons=tuple(reasons),
            artifact_name=artifact_name,
            incoming_payload_valid=True,
            incoming_non_empty=False,
            previous_payload_present=previous_present,
            previous_payload_valid=previous_valid,
            previous_non_empty=True,
            write_incoming=False,
            preserved_previous=True,
            selected_payload=previous or {},
            incoming_summary=incoming_summary,
            previous_summary=previous_summary,
            generated_epoch=generated_epoch,
            metadata={"preservation_rule": "empty_incoming_cannot_overwrite_previous_non_empty", "evidence_only_no_runtime_change": True},
        )

    return _decision(
        status=LATEST_ARTIFACT_STATUS_WRITTEN,
        reason_code=INCOMING_EMPTY_NO_PREVIOUS_REASON,
        reasons=(INCOMING_EMPTY_NO_PREVIOUS_REASON,),
        artifact_name=artifact_name,
        incoming_payload_valid=True,
        incoming_non_empty=False,
        previous_payload_present=previous_present,
        previous_payload_valid=previous_valid,
        previous_non_empty=False,
        write_incoming=True,
        preserved_previous=False,
        selected_payload=incoming,
        incoming_summary=incoming_summary,
        previous_summary=previous_summary,
        generated_epoch=generated_epoch,
        metadata={"preservation_rule": "no_previous_non_empty_payload_to_preserve", "evidence_only_no_runtime_change": True},
    )


def write_latest_artifact_preserving_non_empty(
    path: str | Path,
    incoming_payload: Mapping[str, Any] | Any,
    *,
    artifact_name: str | None = None,
    evidence_path: str | Path | None = None,
    count_keys: Iterable[str] = DEFAULT_COUNT_KEYS,
    sequence_keys: Iterable[str] = DEFAULT_SEQUENCE_KEYS,
    signal_keys: Iterable[str] = DEFAULT_SIGNAL_KEYS,
    now_epoch: float | None = None,
) -> LatestArtifactPreservationDecision:
    """Write incoming latest evidence unless it would erase previous non-empty evidence."""

    target = Path(path).expanduser()
    previous = _read_json_mapping(target)
    decision = build_latest_artifact_preservation_decision(
        incoming_payload,
        previous,
        artifact_name=artifact_name or target.name,
        count_keys=count_keys,
        sequence_keys=sequence_keys,
        signal_keys=signal_keys,
        now_epoch=now_epoch,
    )
    if decision.write_incoming:
        write_json_atomic(target, decision.selected_payload)
    if evidence_path is not None:
        write_json_atomic(Path(evidence_path).expanduser(), decision.to_payload())
    return decision


def _decision(**kwargs: Any) -> LatestArtifactPreservationDecision:
    return LatestArtifactPreservationDecision(
        schema_version=LATEST_ARTIFACT_PRESERVATION_SCHEMA_VERSION,
        source=LATEST_ARTIFACT_PRESERVATION_SOURCE,
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


def _read_json_mapping(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except Exception:
        return None
    return dict(value) if isinstance(value, Mapping) else None


def _is_non_empty_artifact(
    payload: Mapping[str, Any],
    count_keys: tuple[str, ...],
    sequence_keys: tuple[str, ...],
    signal_keys: tuple[str, ...],
) -> bool:
    if not isinstance(payload, Mapping) or not payload:
        return False
    for key in count_keys:
        if _positive_int(payload.get(key)) > 0:
            return True
    for key in sequence_keys:
        if _non_empty_sequence(payload.get(key)):
            return True
    for key in signal_keys:
        if _meaningful_value(payload.get(key)):
            return True
    return False


def _artifact_summary(
    payload: Mapping[str, Any],
    count_keys: tuple[str, ...],
    sequence_keys: tuple[str, ...],
    signal_keys: tuple[str, ...],
) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or not payload:
        return {"non_empty": False, "positive_count_keys": [], "non_empty_sequence_keys": [], "non_empty_signal_keys": []}
    positive_count_keys = [key for key in count_keys if _positive_int(payload.get(key)) > 0]
    non_empty_sequence_keys = [key for key in sequence_keys if _non_empty_sequence(payload.get(key))]
    non_empty_signal_keys = [key for key in signal_keys if _meaningful_value(payload.get(key))]
    return {
        "non_empty": bool(positive_count_keys or non_empty_sequence_keys or non_empty_signal_keys),
        "positive_count_keys": positive_count_keys,
        "non_empty_sequence_keys": non_empty_sequence_keys,
        "non_empty_signal_keys": non_empty_signal_keys,
        "source": str(payload.get("source") or ""),
        "status": str(payload.get("status") or ""),
        "generated_epoch": payload.get("generated_epoch"),
    }


def _positive_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except Exception:
        return 0


def _non_empty_sequence(value: Any) -> bool:
    if isinstance(value, (str, bytes, bytearray)) or value is None:
        return False
    if isinstance(value, Mapping):
        return bool(value)
    try:
        return len(list(value)) > 0
    except TypeError:
        return False


def _meaningful_value(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return bool(value)
    if isinstance(value, (list, tuple, set, frozenset)):
        return bool(value)
    return bool(value)


__all__ = [
    "DEFAULT_COUNT_KEYS",
    "DEFAULT_SEQUENCE_KEYS",
    "DEFAULT_SIGNAL_KEYS",
    "INCOMING_EMPTY_NO_PREVIOUS_REASON",
    "INCOMING_EMPTY_PREVIOUS_NON_EMPTY_REASON",
    "INCOMING_NON_EMPTY_REASON",
    "INVALID_INCOMING_PAYLOAD_REASON",
    "LATEST_ARTIFACT_PRESERVATION_SCHEMA_VERSION",
    "LATEST_ARTIFACT_PRESERVATION_SOURCE",
    "LATEST_ARTIFACT_STATUS_BLOCKED",
    "LATEST_ARTIFACT_STATUS_PRESERVED",
    "LATEST_ARTIFACT_STATUS_WRITTEN",
    "LatestArtifactPreservationDecision",
    "build_latest_artifact_preservation_decision",
    "write_latest_artifact_preserving_non_empty",
]
