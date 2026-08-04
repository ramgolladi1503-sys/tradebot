from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class DashboardReadModel:
    session: dict[str, object]
    data_truth: dict[str, object]
    candidate_funnel: dict[str, object]
    runtime_timeline: tuple[dict[str, object], ...]
    research_status: dict[str, object]

    def to_record(self) -> dict[str, object]:
        return {
            "session": dict(self.session),
            "data_truth": dict(self.data_truth),
            "candidate_funnel": dict(self.candidate_funnel),
            "runtime_timeline": [dict(row) for row in self.runtime_timeline],
            "research_status": dict(self.research_status),
        }


def build_dashboard_read_model(
    session_analysis: Mapping[str, object],
    *,
    certification: Mapping[str, object] | None = None,
) -> DashboardReadModel:
    manifest = session_analysis.get("manifest")
    funnel = session_analysis.get("candidate_funnel")
    timeline = session_analysis.get("runtime_timeline")
    readiness = session_analysis.get("outcome_readiness")
    if not isinstance(manifest, Mapping):
        raise ValueError("dashboard_manifest_missing")
    if not isinstance(funnel, Mapping):
        raise ValueError("dashboard_candidate_funnel_missing")
    if not isinstance(timeline, Sequence) or isinstance(timeline, (str, bytes)):
        raise ValueError("dashboard_runtime_timeline_missing")
    if not isinstance(readiness, Mapping):
        raise ValueError("dashboard_outcome_readiness_missing")
    session = {
        "session_id": manifest.get("session_id"),
        "run_id": manifest.get("run_id"),
        "verdict": manifest.get("verdict"),
        "valid": manifest.get("valid"),
        "first_event_time": manifest.get("first_event_time"),
        "last_event_time": manifest.get("last_event_time"),
    }
    data_truth = {
        "event_count": manifest.get("event_count"),
        "instrument_count": manifest.get("instrument_count"),
        "invalid_quality_event_count": manifest.get("invalid_quality_event_count"),
        "producer_sequence_gap_total": manifest.get("producer_sequence_gap_total"),
        "source_to_receive_latency_ms": manifest.get("source_to_receive_latency_ms"),
        "receive_to_persist_latency_ms": manifest.get("receive_to_persist_latency_ms"),
        "event_gap_ms": manifest.get("event_gap_ms"),
        "event_log_sha256": manifest.get("event_log_sha256"),
    }
    research_status = {
        "ready_for_strategy_diagnosis": readiness.get("ready_for_strategy_diagnosis"),
        "ready_for_profitability_claim": readiness.get("ready_for_profitability_claim"),
        "reason": readiness.get("reason"),
        "certification_verdict": certification.get("verdict") if certification else "NOT_EVALUATED",
    }
    return DashboardReadModel(
        session=session,
        data_truth=data_truth,
        candidate_funnel=dict(funnel),
        runtime_timeline=tuple(dict(row) for row in timeline if isinstance(row, Mapping)),
        research_status=research_status,
    )
