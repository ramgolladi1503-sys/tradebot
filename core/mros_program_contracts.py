"""Offline-safe contracts shared by the MROS T09-T35 architecture lanes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json
from typing import Mapping, Sequence


class EvidenceStatus(str, Enum):
    READY = "READY"
    BLOCKED_DATA = "BLOCKED_DATA"
    BLOCKED_LIVE_WINDOW = "BLOCKED_LIVE_WINDOW"
    PROSPECTIVE_EVIDENCE_PENDING = "PROSPECTIVE_EVIDENCE_PENDING"


def _sha(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@dataclass(frozen=True)
class IndianSessionState:
    session_date: str
    index_artifact_sha256: Mapping[str, str]
    complete: bool
    missing_indices: tuple[str, ...] = ()

    def validate(self) -> None:
        required = {"NIFTY", "BANKNIFTY", "SENSEX"}
        if set(self.index_artifact_sha256) != required:
            raise ValueError("THREE_INDEX_IDENTITY_REQUIRED")
        if any(len(value) != 64 for value in self.index_artifact_sha256.values()):
            raise ValueError("INDEX_ARTIFACT_SHA_REQUIRED")
        if not self.complete or self.missing_indices:
            raise ValueError("THREE_INDEX_SESSION_INCOMPLETE")


@dataclass(frozen=True)
class PredictionRecord:
    prediction_sha256: str
    model_sha256: str
    cutoff: datetime
    predicted_value: float | None
    status: EvidenceStatus = EvidenceStatus.READY

    def immutable_payload(self) -> dict[str, object]:
        return {"prediction_sha256": self.prediction_sha256, "model_sha256": self.model_sha256, "cutoff": self.cutoff.isoformat(), "predicted_value": self.predicted_value, "status": self.status.value}


@dataclass(frozen=True)
class ProspectiveLedgerEntry:
    prediction_sha256: str
    outcome_value: float | None
    outcome_observed_at: datetime | None
    append_sequence: int

    def validate(self) -> None:
        if self.append_sequence < 1 or not self.prediction_sha256:
            raise ValueError("LEDGER_IDENTITY_REQUIRED")
        if self.outcome_value is None and self.outcome_observed_at is not None:
            raise ValueError("MISSING_OUTCOME_TIMESTAMP_MISMATCH")


@dataclass(frozen=True)
class V2Hypothesis:
    hypothesis_id: str
    source_names: tuple[str, ...]
    economic_rationale: str
    predeclared: bool
    v1_model_sha256: str

    def validate(self) -> None:
        if not self.hypothesis_id or not self.source_names or not self.economic_rationale:
            raise ValueError("HYPOTHESIS_SPEC_INCOMPLETE")
        if not self.predeclared:
            raise ValueError("UNDECLARED_SEARCH_FORBIDDEN")
        if len(self.v1_model_sha256) != 64:
            raise ValueError("V1_BINDING_REQUIRED")


@dataclass(frozen=True)
class IntradayRegimeSpec:
    targets_minutes: tuple[int, ...]
    causal_cutoff: str
    gap_target_separate: bool
    baselines: tuple[str, ...]

    def validate(self) -> None:
        if self.targets_minutes != (30, 60, 120):
            raise ValueError("INTRADAY_TARGETS_MUST_BE_EXPLICIT")
        if not self.causal_cutoff or not self.gap_target_separate or not self.baselines:
            raise ValueError("INTRADAY_CAUSAL_SPEC_INCOMPLETE")


def seal_snapshot_metadata(payload: Mapping[str, object]) -> dict[str, object]:
    """Seal metadata only; this does not assert data completeness or live truth."""

    result = dict(payload)
    result["artifact_sha256"] = _sha(payload)
    result["read_only"] = True
    result["broker_write_authority"] = False
    result["order_authority"] = False
    result["paper_authorized"] = False
    result["live_authorized"] = False
    return result
