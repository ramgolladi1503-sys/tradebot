from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class EvidenceClaim:
    claim: str
    evidence_refs: tuple[str, ...]
    claim_type: str

    def __post_init__(self) -> None:
        if not self.claim.strip() or not self.evidence_refs:
            raise ValueError("claim_requires_text_and_evidence")
        if self.claim_type not in {"FACT", "SUPPORTED_INFERENCE", "HYPOTHESIS"}:
            raise ValueError("claim_type_invalid")
        if any(not ref.strip() for ref in self.evidence_refs):
            raise ValueError("empty_evidence_reference")


@dataclass(frozen=True)
class AnalystState:
    session_id: str
    deterministic_metrics: Mapping[str, object]
    retrieved_evidence: tuple[Mapping[str, object], ...]
    claims: tuple[EvidenceClaim, ...] = ()
    contradictions: tuple[str, ...] = ()
    verdict: str = "UNREVIEWED"


class NarrativeProvider(Protocol):
    def __call__(
        self,
        metrics: Mapping[str, object],
        evidence: Sequence[Mapping[str, object]],
    ) -> Sequence[Mapping[str, object]]: ...


def validate_claims(
    raw_claims: Sequence[Mapping[str, object]],
    *,
    allowed_evidence_refs: set[str],
) -> tuple[EvidenceClaim, ...]:
    claims: list[EvidenceClaim] = []
    for row in raw_claims:
        refs = tuple(str(value) for value in row.get("evidence_refs", ()))
        claim = EvidenceClaim(
            claim=str(row.get("claim") or ""),
            evidence_refs=refs,
            claim_type=str(row.get("claim_type") or ""),
        )
        unknown = sorted(set(claim.evidence_refs) - allowed_evidence_refs)
        if unknown:
            raise ValueError(f"claim_references_unknown_evidence={','.join(unknown)}")
        claims.append(claim)
    return tuple(claims)


def detect_metric_contradictions(
    claims: Sequence[EvidenceClaim], metrics: Mapping[str, object]
) -> tuple[str, ...]:
    contradictions: list[str] = []
    valid = metrics.get("valid")
    ready = metrics.get("ready_for_profitability_claim")
    for claim in claims:
        lowered = claim.claim.lower()
        if valid is False and "data is valid" in lowered:
            contradictions.append("CLAIM_CONTRADICTS_DATA_VALIDITY")
        if ready is False and any(
            marker in lowered
            for marker in ("profitability certified", "edge certified", "ready for live")
        ):
            contradictions.append("CLAIM_CONTRADICTS_PROFITABILITY_READINESS")
    return tuple(sorted(set(contradictions)))


class ControlledAnalystWorkflow:
    def __init__(self, narrative_provider: NarrativeProvider) -> None:
        self.narrative_provider = narrative_provider

    def run(self, state: AnalystState) -> AnalystState:
        evidence_refs = {
            str(row.get("source_path") or row.get("evidence_ref") or "")
            for row in state.retrieved_evidence
        }
        evidence_refs.discard("")
        if not evidence_refs:
            return AnalystState(
                session_id=state.session_id,
                deterministic_metrics=state.deterministic_metrics,
                retrieved_evidence=state.retrieved_evidence,
                verdict="EVIDENCE_NOT_AVAILABLE",
            )
        raw_claims = self.narrative_provider(
            state.deterministic_metrics, state.retrieved_evidence
        )
        claims = validate_claims(raw_claims, allowed_evidence_refs=evidence_refs)
        contradictions = detect_metric_contradictions(
            claims, state.deterministic_metrics
        )
        verdict = "REJECTED_CONTRADICTORY_ANALYSIS" if contradictions else "CITED_ANALYSIS_ACCEPTED"
        return AnalystState(
            session_id=state.session_id,
            deterministic_metrics=state.deterministic_metrics,
            retrieved_evidence=state.retrieved_evidence,
            claims=claims,
            contradictions=contradictions,
            verdict=verdict,
        )


def build_optional_langgraph_workflow(
    narrative_provider: NarrativeProvider,
):
    try:
        from langgraph.graph import END, StateGraph
    except ImportError as exc:
        raise RuntimeError("langgraph_not_installed") from exc

    workflow = ControlledAnalystWorkflow(narrative_provider)
    graph = StateGraph(dict)

    def review_node(raw_state: dict) -> dict:
        reviewed = workflow.run(
            AnalystState(
                session_id=str(raw_state["session_id"]),
                deterministic_metrics=dict(raw_state["deterministic_metrics"]),
                retrieved_evidence=tuple(raw_state["retrieved_evidence"]),
            )
        )
        return {
            **raw_state,
            "claims": [claim.__dict__ for claim in reviewed.claims],
            "contradictions": list(reviewed.contradictions),
            "verdict": reviewed.verdict,
        }

    graph.add_node("evidence_review", review_node)
    graph.set_entry_point("evidence_review")
    graph.add_edge("evidence_review", END)
    return graph.compile()
