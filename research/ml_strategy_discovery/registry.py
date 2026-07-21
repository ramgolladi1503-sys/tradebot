from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from .contracts import (
    CandidateStatus,
    CandidateStrategySpec,
    canonical_json,
    semantic_hash,
)

_ALLOWED_TRANSITIONS = {
    CandidateStatus.RESEARCH_CANDIDATE: {
        CandidateStatus.VALIDATION_READY,
        CandidateStatus.REJECTED,
    },
    CandidateStatus.VALIDATION_READY: {
        CandidateStatus.HOLDOUT_CERTIFIED,
        CandidateStatus.REJECTED,
    },
    CandidateStatus.HOLDOUT_CERTIFIED: {
        CandidateStatus.SHADOW_ONLY,
        CandidateStatus.REJECTED,
    },
    CandidateStatus.SHADOW_ONLY: {CandidateStatus.REJECTED},
    CandidateStatus.REJECTED: set(),
}


class CandidateRegistry:
    """In-memory, immutable-export research registry.

    It deliberately has no LIVE status and no activation or persistence effects.
    """

    def __init__(
        self,
        candidates: Iterable[CandidateStrategySpec] = (),
    ) -> None:
        self._candidates: dict[str, CandidateStrategySpec] = {}
        self._transition_evidence: dict[str, dict[str, str]] = {}
        for candidate in candidates:
            self.add(candidate)

    def add(self, candidate: CandidateStrategySpec) -> None:
        candidate.validate()
        if candidate.candidate_id in self._candidates:
            raise ValueError(
                f"duplicate candidate_id: {candidate.candidate_id}"
            )
        self._candidates[candidate.candidate_id] = candidate

    def get(self, candidate_id: str) -> CandidateStrategySpec:
        try:
            return self._candidates[candidate_id]
        except KeyError as exc:
            raise KeyError(f"unknown candidate_id: {candidate_id}") from exc

    def transition(
        self,
        candidate_id: str,
        new_status: CandidateStatus,
        *,
        evidence_hash: str,
    ) -> CandidateStrategySpec:
        if (
            len(evidence_hash) != 64
            or any(
                character not in "0123456789abcdef"
                for character in evidence_hash
            )
        ):
            raise ValueError(
                "status transition requires a SHA-256 evidence hash"
            )
        current = self.get(candidate_id)
        if new_status not in _ALLOWED_TRANSITIONS[current.status]:
            raise ValueError(
                "forbidden candidate transition: "
                f"{current.status.value} -> {new_status.value}"
            )
        updated = replace(current, status=new_status)
        updated.validate()
        self._candidates[candidate_id] = updated
        self._transition_evidence.setdefault(candidate_id, {})[
            new_status.value
        ] = evidence_hash
        return updated

    def snapshot(self) -> tuple[CandidateStrategySpec, ...]:
        return tuple(
            self._candidates[key] for key in sorted(self._candidates)
        )

    def export_json(self) -> str:
        return canonical_json(
            {
                "candidates": self.snapshot(),
                "transition_evidence": self._transition_evidence,
            }
        )

    @property
    def evidence_hash(self) -> str:
        return semantic_hash(
            {
                "candidates": self.snapshot(),
                "transition_evidence": self._transition_evidence,
            }
        )
