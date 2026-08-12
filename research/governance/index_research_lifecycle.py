"""Governed lifecycle decisions for offline index research."""

from __future__ import annotations

from dataclasses import dataclass

from .index_research_contract import DiscoveryResult, ResearchOutcome


@dataclass(frozen=True)
class FreezeDecision:
    index: str
    status: str
    model_sha256: str | None
    evidence_sha256: str | None


def freeze_model(result: DiscoveryResult) -> FreezeDecision:
    result.validate()
    if result.outcome is ResearchOutcome.QUALIFIED:
        return FreezeDecision(result.index, "MODEL_FROZEN", result.candidate_sha, result.evidence_sha256)
    if result.outcome is ResearchOutcome.NO_STRUCTURAL_EDGE_FOUND:
        return FreezeDecision(result.index, "NO_STRUCTURAL_EDGE_FOUND", None, result.evidence_sha256)
    return FreezeDecision(result.index, "BLOCKED_DATA", None, result.evidence_sha256)


def certify_offline(decision: FreezeDecision) -> str:
    if decision.status == "MODEL_FROZEN":
        if not decision.model_sha256 or not decision.evidence_sha256:
            raise ValueError("CERTIFICATION_PROVENANCE_REQUIRED")
        return "OFFLINE_CERTIFIED_PENDING_INDEPENDENT_REVIEW"
    if decision.status in {"NO_STRUCTURAL_EDGE_FOUND", "BLOCKED_DATA"}:
        return decision.status
    raise ValueError("UNKNOWN_FREEZE_STATUS")
