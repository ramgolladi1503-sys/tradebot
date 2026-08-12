"""Read-only Indian evidence lifecycle contracts for T15-T20."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Mapping


@dataclass(frozen=True)
class DailyState:
    session_date: str
    indices: Mapping[str, Mapping[str, object]]
    snapshot_sha256: str
    artifact_sha256: str


def finalize_after_close(session_date: str, indices: Mapping[str, Mapping[str, object]], snapshot_sha256: str) -> DailyState:
    required = {"NIFTY", "BANKNIFTY", "SENSEX"}
    if set(indices) != required or any(not row.get("complete") for row in indices.values()):
        raise ValueError("THREE_INDEX_FINALIZATION_INCOMPLETE")
    payload = {"session_date": session_date, "indices": indices, "snapshot_sha256": snapshot_sha256}
    return DailyState(session_date, indices, snapshot_sha256, _sha(payload))


def score_frozen_models(state: DailyState, model_shas: Mapping[str, str]) -> dict[str, object]:
    if set(model_shas) != {"NIFTY", "BANKNIFTY", "SENSEX"} or any(len(sha) != 64 for sha in model_shas.values()):
        raise ValueError("FROZEN_MODEL_BINDINGS_REQUIRED")
    return {"daily_state_sha256": state.artifact_sha256, "model_shas": dict(sorted(model_shas.items())), "read_only": True}


def build_preopen_report(state: DailyState, scores: Mapping[str, object], *, cutoff: datetime) -> dict[str, object]:
    return {"session_date": state.session_date, "prior_state_sha256": state.artifact_sha256, "scores": dict(scores), "cutoff": cutoff.isoformat(), "leakage_status": "PRE_CUTOFF_ONLY"}


def record_actual_open(report: Mapping[str, object], actual_opens: Mapping[str, float]) -> dict[str, object]:
    if "prior_state_sha256" not in report or set(actual_opens) != {"NIFTY", "BANKNIFTY", "SENSEX"}:
        raise ValueError("ACTUAL_OPEN_BINDING_REQUIRED")
    return {"prediction_report_sha256": _sha(report), "actual_opens": dict(actual_opens)}


def append_ledger(entries: tuple[Mapping[str, object], ...], entry: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    if entries and entry.get("prediction_sha256") in {item.get("prediction_sha256") for item in entries}:
        raise ValueError("LEDGER_DUPLICATE_PREDICTION")
    return (*entries, dict(entry))


def run_research_schedule(*, has_live_authority: bool = False) -> str:
    if has_live_authority:
        raise ValueError("EXECUTION_AUTHORITY_FORBIDDEN")
    return "READ_ONLY_SCHEDULE_READY"


def _sha(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
