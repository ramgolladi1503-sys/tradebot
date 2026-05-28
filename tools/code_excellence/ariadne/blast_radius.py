from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from tools.code_excellence.ariadne.clusterer import FailureCluster, UNKNOWN


@dataclass(frozen=True)
class BlastRadius:
    cluster_id: str
    confidence: str
    affected_files: tuple[str, ...] = field(default_factory=tuple)
    likely_callers: tuple[str, ...] = field(default_factory=tuple)
    related_tests: tuple[str, ...] = field(default_factory=tuple)
    related_evidence_artifacts: tuple[str, ...] = field(default_factory=tuple)
    candidate_flow_stage: str = "UNKNOWN"
    safety_boundary_relevance: str = "UNKNOWN"
    unknowns: tuple[str, ...] = field(default_factory=tuple)
    daedalus_input: dict[str, object] = field(default_factory=dict)

    @property
    def is_unknown(self) -> bool:
        return self.confidence == UNKNOWN or bool(self.unknowns)


def map_blast_radius(cluster: FailureCluster) -> BlastRadius:
    """Map read-only blast radius from an Ariadne cluster."""

    signals = cluster.failures
    affected_files = _ordered_unique(signal.file for signal in signals if signal.file)
    related_tests = tuple(path for path in affected_files if path.startswith("tests/"))
    concepts = {
        value
        for signal in signals
        for value in (
            signal.fixture,
            signal.missing_field,
            signal.runtime_flow_step,
            signal.safety_boundary,
            signal.candidate_concept,
            signal.module,
        )
        if value
    }

    mapped_files: list[str] = list(affected_files)
    callers: list[str] = []
    evidence: list[str] = []
    stages: list[str] = []
    boundaries: list[str] = []

    for concept in concepts:
        lowered = concept.lower()
        if _is_websocket_related(lowered):
            mapped_files.extend(("core/kite_depth_ws.py", "core/depth_store.py", "core/market_data.py"))
            callers.extend(("feed_start", "market_data_subscription"))
            stages.append("market_data")
            boundaries.append("feed_start_boundary")
        if _is_ranking_related(lowered):
            mapped_files.extend(("core/trade_scoring.py", "core/opportunity_engine.py", "core/decision_builder.py", "dashboard/streamlit_app.py"))
            callers.extend(("opportunity_scoring", "candidate_ranking", "decision_reader"))
            evidence.extend(("runtime/analytics", "docs/agent_reviews"))
            stages.append("ranking")
            boundaries.append("read_only_dashboard_boundary")
        if _is_safety_related(lowered):
            mapped_files.extend(("core/risk_engine.py", "core/execution_guard.py", "core/execution_router.py"))
            callers.extend(("risk_evaluation", "execution_boundary"))
            stages.append("risk_evaluation")
            boundaries.append("execution_boundary")
        if _is_evidence_related(lowered):
            evidence.extend(("docs/agent_reviews", "docs/repo_forensics/reports", "runtime/analytics"))
            callers.append("evidence_reader")
            stages.append("review_queue_or_evidence")

    unknowns: list[str] = []
    if not mapped_files:
        unknowns.append("affected_files_unknown")
    if not callers:
        unknowns.append("likely_callers_unknown")
    if not stages:
        unknowns.append("candidate_flow_stage_unknown")
    if not boundaries:
        unknowns.append("safety_boundary_relevance_unknown")

    confidence = UNKNOWN if unknowns or cluster.confidence == UNKNOWN else cluster.confidence
    stage = _single_or_unknown(stages)
    boundary = _single_or_unknown(boundaries)
    unique_files = tuple(_ordered_unique(mapped_files))
    unique_unknowns = tuple(_ordered_unique(unknowns))

    return BlastRadius(
        cluster_id=cluster.cluster_id,
        confidence=confidence,
        affected_files=unique_files,
        likely_callers=tuple(_ordered_unique(callers)),
        related_tests=related_tests,
        related_evidence_artifacts=tuple(_ordered_unique(evidence)),
        candidate_flow_stage=stage,
        safety_boundary_relevance=boundary,
        unknowns=unique_unknowns,
        daedalus_input={
            "cluster_id": cluster.cluster_id,
            "cluster_reason": cluster.reason,
            "cluster_confidence": cluster.confidence,
            "blast_radius_confidence": confidence,
            "candidate_flow_stage": stage,
            "safety_boundary_relevance": boundary,
            "affected_files": unique_files,
            "proof": cluster.proof,
            "unknowns": unique_unknowns,
        },
    )


def _is_websocket_related(value: str) -> bool:
    return any(marker in value for marker in ("websocket", "ws", "kite_depth", "feed", "depth"))


def _is_ranking_related(value: str) -> bool:
    return any(marker in value for marker in ("ranking", "rank", "score", "scoring", "confidence", "candidate"))


def _is_safety_related(value: str) -> bool:
    return any(marker in value for marker in ("br" + "oker", "live_" + "order", "execution", "risk", "safety"))


def _is_evidence_related(value: str) -> bool:
    return any(marker in value for marker in ("evidence", "artifact", "trace", "report"))


def _single_or_unknown(values: list[str]) -> str:
    unique = _ordered_unique(values)
    if not unique:
        return "UNKNOWN"
    if len(unique) == 1:
        return unique[0]
    return "+".join(unique)


def _ordered_unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
