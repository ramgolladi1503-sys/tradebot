"""Causal, advisory-only contract for CAS_SW_RUNTIME_V2_1514."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping


CAS_SPEC_ID = "CAS_SW_RUNTIME_V2_1514"
FREEZE_HOUR = 15
FREEZE_MINUTE = 14
IST = timezone(timedelta(hours=5, minutes=30))


@dataclass(frozen=True)
class CASDecision:
    direction: str
    freeze_timestamp: str
    source_sha: str
    spec_sha: str
    execution_status: str = "advisory_only"

    def validate(self) -> None:
        if self.direction not in {"UP", "DOWN", "FLAT", "ABSTAIN"}:
            raise ValueError("cas_direction_invalid")
        if self.execution_status != "advisory_only":
            raise ValueError("cas_execution_status_not_advisory")
        if not self.source_sha or not self.spec_sha:
            raise ValueError("cas_identity_missing")

    @property
    def option_side(self) -> str | None:
        return {"UP": "CE", "DOWN": "PE"}.get(self.direction)


def freeze_cas_decision(
    *,
    completed_inputs: Mapping[str, datetime],
    freeze_timestamp: datetime,
    direction: str,
    source_sha: str,
    spec_sha: str,
) -> CASDecision:
    """Freeze only from completed one-minute inputs available before 15:14."""
    freeze_timestamp = freeze_timestamp.astimezone(IST)
    if freeze_timestamp.hour != FREEZE_HOUR or freeze_timestamp.minute != FREEZE_MINUTE:
        raise ValueError("cas_freeze_timestamp_not_1514_ist")
    if not completed_inputs:
        raise ValueError("cas_completed_inputs_missing")
    for name, timestamp in completed_inputs.items():
        if timestamp.astimezone(IST) >= freeze_timestamp:
            raise ValueError(f"cas_input_after_freeze:{name}")
    decision = CASDecision(
        direction=direction, freeze_timestamp=freeze_timestamp.isoformat(),
        source_sha=source_sha, spec_sha=spec_sha,
    )
    decision.validate()
    return decision
