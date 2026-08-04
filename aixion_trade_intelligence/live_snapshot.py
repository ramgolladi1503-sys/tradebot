from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .session import SessionAnalysis


@dataclass(frozen=True)
class LiveSessionSnapshot:
    monitoring_valid: bool
    monitoring_verdict: str
    final_session_complete: bool
    monitoring_only: bool
    blockers: tuple[str, ...]
    verification: dict[str, object]
    session_analysis: dict[str, object]

    def to_record(self) -> dict[str, object]:
        return {
            "monitoring_valid": self.monitoring_valid,
            "monitoring_verdict": self.monitoring_verdict,
            "final_session_complete": self.final_session_complete,
            "monitoring_only": self.monitoring_only,
            "blockers": list(self.blockers),
            "verification": dict(self.verification),
            "session_analysis": dict(self.session_analysis),
        }


def _mapping(value: object, *, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"live_snapshot_{name}_missing")
    return value


def build_live_session_snapshot(
    analysis: SessionAnalysis,
    *,
    verification: Mapping[str, object],
) -> LiveSessionSnapshot:
    manifest = _mapping(analysis.manifest, name="manifest")
    lifecycle = _mapping(manifest.get("required_lifecycle"), name="required_lifecycle")
    errors_raw = manifest.get("lifecycle_errors")
    if not isinstance(errors_raw, list):
        raise ValueError("live_snapshot_lifecycle_errors_missing")
    lifecycle_errors = tuple(str(value) for value in errors_raw)
    blockers: list[str] = []
    if not bool(verification.get("valid")):
        blockers.append("EVENT_LOG_VERIFICATION_FAILED")
    if int(verification.get("session_count") or 0) != 1:
        blockers.append("EVENT_LOG_SESSION_COUNT_INVALID")
    if not bool(lifecycle.get("SESSION_STARTED")):
        blockers.append("SESSION_START_MISSING_OR_DUPLICATE")
    final_complete = bool(manifest.get("valid"))
    allowed_active_error = lifecycle_errors == ("SESSION_ENDED_COUNT=0",)
    if not final_complete and not allowed_active_error:
        blockers.extend(f"LIFECYCLE:{value}" for value in lifecycle_errors)
    if int(manifest.get("producer_sequence_gap_total") or 0) != 0:
        blockers.append("PRODUCER_SEQUENCE_GAP")
    if int(manifest.get("producer_sequence_duplicate_total") or 0) != 0:
        blockers.append("PRODUCER_SEQUENCE_DUPLICATE")
    if int(manifest.get("invalid_quality_event_count") or 0) != 0:
        blockers.append("INVALID_DATA_QUALITY")
    if int(manifest.get("partial_quality_event_count") or 0) != 0:
        blockers.append("PARTIAL_DATA_QUALITY")
    monitoring_valid = not blockers
    if final_complete and monitoring_valid:
        verdict = "FINAL_SESSION_COMPLETE"
    elif monitoring_valid:
        verdict = "LIVE_MONITORING_HEALTHY"
    else:
        verdict = "LIVE_MONITORING_BLOCKED"
    return LiveSessionSnapshot(
        monitoring_valid=monitoring_valid,
        monitoring_verdict=verdict,
        final_session_complete=final_complete,
        monitoring_only=not final_complete,
        blockers=tuple(dict.fromkeys(blockers)),
        verification=dict(verification),
        session_analysis=analysis.to_record(),
    )
