"""Common provenance contract for read-only live strategy candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class LiveCandidate:
    candidate_id: str
    strategy_id: str
    spec_sha: str
    timestamp: str
    underlying: str
    direction: str
    candidate_type: str
    confidence_raw: float | None
    regime: str
    reason: str
    data_cutoff: str
    execution_status: str = "advisory_only"

    def validate(self) -> None:
        required = ("candidate_id", "strategy_id", "spec_sha", "timestamp", "underlying", "candidate_type", "regime", "reason", "data_cutoff")
        if any(not str(getattr(self, key) or "").strip() for key in required):
            raise ValueError("live_candidate_identity_or_provenance_missing")
        if self.direction not in {"UP", "DOWN", "FLAT", "ABSTAIN", "BUY_CALL", "BUY_PUT"}:
            raise ValueError("live_candidate_direction_invalid")
        if self.execution_status != "advisory_only":
            raise ValueError("live_candidate_execution_status_not_advisory")
        if self.confidence_raw is not None and not 0.0 <= float(self.confidence_raw) <= 1.0:
            raise ValueError("live_candidate_confidence_invalid")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.__dict__.copy()


def candidate_from_mapping(row: Mapping[str, Any]) -> LiveCandidate:
    candidate = LiveCandidate(
        candidate_id=str(row.get("candidate_id") or ""), strategy_id=str(row.get("strategy_id") or ""),
        spec_sha=str(row.get("spec_sha") or ""), timestamp=str(row.get("timestamp") or ""),
        underlying=str(row.get("underlying") or ""), direction=str(row.get("direction") or ""),
        candidate_type=str(row.get("candidate_type") or ""),
        confidence_raw=None if row.get("confidence_raw") is None else float(row["confidence_raw"]),
        regime=str(row.get("regime") or ""), reason=str(row.get("reason") or ""),
        data_cutoff=str(row.get("data_cutoff") or ""),
        execution_status=str(row.get("execution_status") or "advisory_only"),
    )
    candidate.validate()
    return candidate
