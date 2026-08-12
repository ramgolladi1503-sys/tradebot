"""Causal, provenance-bound global context evidence contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Mapping


def _digest(value: Mapping[str, object]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class GlobalObservation:
    source: str
    observed_at: datetime
    value: float | None
    raw_sha256: str

    def validate(self, *, cutoff: datetime) -> None:
        if not self.source or len(self.raw_sha256) != 64:
            raise ValueError("GLOBAL_PROVENANCE_REQUIRED")
        if self.observed_at > cutoff:
            raise ValueError("GLOBAL_FUTURE_OBSERVATION")
        if self.value is not None and self.value != self.value:
            raise ValueError("GLOBAL_NONFINITE_OBSERVATION")


def build_causal_snapshot(observations: Mapping[str, GlobalObservation], *, cutoff: datetime) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for name, observation in sorted(observations.items()):
        observation.validate(cutoff=cutoff)
        normalized[name] = {
            "source": observation.source,
            "observed_at": observation.observed_at.isoformat(),
            "value": observation.value,
            "raw_sha256": observation.raw_sha256,
        }
    payload = {"cutoff": cutoff.isoformat(), "observations": normalized}
    return {**payload, "snapshot_sha256": _digest(payload)}
