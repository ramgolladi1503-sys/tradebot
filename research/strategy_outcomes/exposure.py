from __future__ import annotations

from collections.abc import Iterable

from research.strategy_outcomes.contract import OutcomeCandidate


def exposure_keys(candidates: Iterable[OutcomeCandidate]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        key = f"{candidate.session_key}:{candidate.symbol}:{candidate.direction}:{candidate.proposal_ready_at}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def duplicate_directional_exposure(candidates: Iterable[OutcomeCandidate]) -> tuple[str, ...]:
    return tuple(sorted(key for key, count in exposure_keys(candidates).items() if count > 1))
