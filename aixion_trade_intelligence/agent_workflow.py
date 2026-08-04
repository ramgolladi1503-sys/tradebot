from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence, TypedDict


class AnalystCallable(Protocol):
    def __call__(self, *, deterministic_metrics: Mapping[str, object], evidence: Sequence[Mapping[str, object]]) -> Mapping[str, object]: ...


class CriticCallable(Protocol):
    def __call__(self, *, deterministic_metrics: Mapping[str, object], evidence: Sequence[Mapping[str, object]], draft: Mapping[str, object]) -> Mapping[str, object]: ...


def _canonical_hash(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate_evidence(evidence: Sequence[Mapping[str, object]]) -> tuple[dict[str, object], ...]:
    normalized: list[dict[str, object]] = []
    for row in evidence:
        source_path = str(row.get("source_path") or "").strip()
        content_hash = str(row.get("content_hash") or "").strip()
        if not source_path or not content_hash:
            raise ValueError("agent_evidence_identity_missing")
        normalized.append({"source_path": source_path, "content_hash": content_hash, "content": str(row.get("content") or ""), "metadata": dict(row.get("metadata") or {})})
    return tuple(normalized)


@dataclass(frozen=True)
class ControlledReview:
    deterministic_metrics_hash: str
    draft: dict[str, object]
    critique: dict[str, object]
    final: dict[str, object]
    evidence_refs: tuple[str, ...]

    def to_record(self) -> dict[str, object]:
        return {"deterministic_metrics_hash": self.deterministic_metrics_hash, "draft": dict(self.draft), "critique": dict(self.critique), "final": dict(self.final), "evidence_refs": list(self.evidence_refs)}


def run_controlled_review(*, deterministic_metrics: Mapping[str, object], evidence: Sequence[Mapping[str, object]], analyst: AnalystCallable, critic: CriticCallable) -> ControlledReview:
    metrics = dict(deterministic_metrics)
    metrics_hash = _canonical_hash(metrics)
    safe_evidence = _validate_evidence(evidence)
    draft = dict(analyst(deterministic_metrics=metrics, evidence=safe_evidence))
    if _canonical_hash(metrics) != metrics_hash:
        raise RuntimeError("analyst_mutated_deterministic_metrics")
    critique = dict(critic(deterministic_metrics=metrics, evidence=safe_evidence, draft=draft))
    if _canonical_hash(metrics) != metrics_hash:
        raise RuntimeError("critic_mutated_deterministic_metrics")
    unsupported = critique.get("unsupported_claims") or []
    contradictions = critique.get("contradictions") or []
    if not isinstance(unsupported, list) or not isinstance(contradictions, list):
        raise ValueError("critic_contract_invalid")
    final = {"status": "REVIEW_REJECTED" if unsupported or contradictions else "REVIEW_ACCEPTED", "analysis": draft, "unsupported_claims": list(unsupported), "contradictions": list(contradictions), "fact_inference_boundary": critique.get("fact_inference_boundary") or {}}
    return ControlledReview(metrics_hash, draft, critique, final, tuple(sorted({str(row["source_path"]) for row in safe_evidence})))


class ReviewState(TypedDict, total=False):
    deterministic_metrics: dict[str, object]
    deterministic_metrics_hash: str
    evidence: list[dict[str, object]]
    draft: dict[str, object]
    critique: dict[str, object]
    final: dict[str, object]


def build_langgraph_review(*, analyst: AnalystCallable, critic: CriticCallable):
    """Build a model-agnostic LangGraph review; caller owns model and credentials."""
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError("langgraph_not_installed") from exc

    def validate_node(state: ReviewState) -> ReviewState:
        metrics = dict(state.get("deterministic_metrics") or {})
        evidence = _validate_evidence(state.get("evidence") or [])
        return {**state, "deterministic_metrics": metrics, "deterministic_metrics_hash": _canonical_hash(metrics), "evidence": [dict(row) for row in evidence]}

    def analyst_node(state: ReviewState) -> ReviewState:
        metrics = dict(state["deterministic_metrics"])
        expected = str(state["deterministic_metrics_hash"])
        draft = dict(analyst(deterministic_metrics=metrics, evidence=state["evidence"]))
        if _canonical_hash(metrics) != expected:
            raise RuntimeError("analyst_mutated_deterministic_metrics")
        return {**state, "draft": draft}

    def critic_node(state: ReviewState) -> ReviewState:
        metrics = dict(state["deterministic_metrics"])
        expected = str(state["deterministic_metrics_hash"])
        critique = dict(critic(deterministic_metrics=metrics, evidence=state["evidence"], draft=state["draft"]))
        if _canonical_hash(metrics) != expected:
            raise RuntimeError("critic_mutated_deterministic_metrics")
        return {**state, "critique": critique}

    def finalize_node(state: ReviewState) -> ReviewState:
        critique = dict(state["critique"])
        unsupported = critique.get("unsupported_claims") or []
        contradictions = critique.get("contradictions") or []
        return {**state, "final": {"status": "REVIEW_REJECTED" if unsupported or contradictions else "REVIEW_ACCEPTED", "analysis": dict(state["draft"]), "unsupported_claims": list(unsupported), "contradictions": list(contradictions), "fact_inference_boundary": critique.get("fact_inference_boundary") or {}}}

    graph = StateGraph(ReviewState)
    graph.add_node("validate", validate_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("critic", critic_node)
    graph.add_node("finalize", finalize_node)
    graph.add_edge(START, "validate")
    graph.add_edge("validate", "analyst")
    graph.add_edge("analyst", "critic")
    graph.add_edge("critic", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()
