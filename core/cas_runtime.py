"""Durable, advisory-only CAS_SW_RUNTIME_V2_1514 runtime state machine."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.cas_v2_consumer_contract import CAS_SPEC_ID, IST, freeze_cas_decision

WAITING_FOR_1510 = "WAITING_FOR_1510"
WAITING_FOR_1513 = "WAITING_FOR_1513"
DIRECTION_INPUTS_READY = "DIRECTION_INPUTS_READY"
FROZEN = "FROZEN"


@dataclass(frozen=True)
class CASRuntime:
    session_date: str
    session_id: str
    source_sha: str
    cas_spec_sha: str
    state: str = WAITING_FOR_1510
    inputs: dict[str, dict[str, Any]] | None = None
    decision: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "inputs", dict(self.inputs or {}))

    @property
    def boundary(self) -> datetime:
        return datetime.fromisoformat(f"{self.session_date}T15:14:00+05:30")

    def capture(self, *, input_name: str, value: Any, market_timestamp: datetime,
                capture_timestamp: datetime | None = None, source: str = "canonical_live_sqlite") -> "CASRuntime":
        ts = market_timestamp.astimezone(IST)
        if input_name not in {"15:10", "15:13"}:
            raise ValueError("cas_input_name_invalid")
        if ts.time() >= self.boundary.time():
            raise ValueError("cas_input_after_freeze")
        if input_name in self.inputs:
            return self
        record = {"input_name": input_name, "value": value,
                  "market_timestamp": ts.isoformat(),
                  "capture_timestamp": (capture_timestamp or datetime.now(timezone.utc)).isoformat(),
                  "source": source, "session_id": self.session_id,
                  "source_sha": self.source_sha, "cas_spec_id": CAS_SPEC_ID,
                  "cas_spec_sha": self.cas_spec_sha, "causal": True}
        inputs = dict(self.inputs); inputs[input_name] = record
        state = DIRECTION_INPUTS_READY if {"15:10", "15:13"} <= inputs.keys() else WAITING_FOR_1513
        return CASRuntime(self.session_date, self.session_id, self.source_sha, self.cas_spec_sha, state, inputs, self.decision)

    def freeze(self, *, now: datetime, direction: str) -> "CASRuntime":
        if self.state == FROZEN:
            return self
        boundary = now.astimezone(IST).replace(hour=15, minute=14, second=0, microsecond=0)
        if now.astimezone(IST) < boundary:
            return self
        if self.state != DIRECTION_INPUTS_READY:
            return self
        completed = {name: datetime.fromisoformat(row["market_timestamp"]) for name, row in self.inputs.items()}
        decision = freeze_cas_decision(completed_inputs=completed, freeze_timestamp=boundary,
                                       direction=direction, source_sha=self.source_sha, spec_sha=self.cas_spec_sha)
        return CASRuntime(self.session_date, self.session_id, self.source_sha, self.cas_spec_sha, FROZEN, self.inputs, asdict(decision))

    def persist(self, path: str | Path) -> None:
        destination = Path(path); destination.parent.mkdir(parents=True, exist_ok=True)
        tmp = destination.with_suffix(destination.suffix + ".tmp")
        tmp.write_text(json.dumps(asdict(self), sort_keys=True, indent=2, default=str) + "\n", encoding="utf-8")
        tmp.replace(destination)

    @classmethod
    def recover(cls, path: str | Path, *, session_id: str, source_sha: str, cas_spec_sha: str) -> "CASRuntime":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("session_id") != session_id or payload.get("source_sha") != source_sha:
            raise ValueError("cas_runtime_lineage_mismatch")
        if payload.get("cas_spec_sha") != cas_spec_sha or payload.get("cas_spec_id") not in (None, CAS_SPEC_ID):
            raise ValueError("cas_runtime_spec_mismatch")
        if payload.get("session_date") != session_id[-10:]:
            raise ValueError("cas_runtime_session_date_mismatch")
        runtime = cls(payload["session_date"], session_id, source_sha, cas_spec_sha, payload.get("state", WAITING_FOR_1510), payload.get("inputs"), payload.get("decision"))
        if runtime.state == DIRECTION_INPUTS_READY and set(runtime.inputs) != {"15:10", "15:13"}:
            raise ValueError("cas_runtime_state_inconsistent")
        return runtime
