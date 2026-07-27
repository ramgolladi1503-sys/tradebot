from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ObservedUniverseResult:
    observed_existence_status: str
    identity_authority_status: str
    universe_completeness_status: str
    lot_size_status: str
    tick_size_status: str
    cost_authority_status: str
    blockers: tuple[str, ...]

