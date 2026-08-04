from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Iterable

from .contracts import CanonicalEvent
from .storage import event_log_hash


@dataclass(frozen=True)
class SessionAnalysis:
    manifest: dict[str, object]
    candidate_funnel: dict[str, object]
    runtime_timeline: list[dict[str, object]]
    outcome_readiness: dict[str, object]

    @property
    def analysis_hash(self) -> str:
        payload = {
            "manifest": self.manifest,
            "candidate_funnel": self.candidate_funnel,
            "runtime_timeline": self.runtime_timeline,
            "outcome_readiness": self.outcome_readiness,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def to_record(self) -> dict[str, object]:
        return {
            "manifest": self.manifest,
            "candidate_funnel": self.candidate_funnel,
            "runtime_timeline": self.runtime_timeline,
            "outcome_readiness": self.outcome_readiness,
            "analysis_hash": self.analysis_hash,
        }


def _percentile(values: list[float], fraction: float) -> float | None:
    finite = sorted(value for value in values if math.isfinite(value))
    if not finite:
        return None
    if len(finite) == 1:
        return finite[0]
    position = (len(finite) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return finite[lower]
    weight = position - lower
    return finite[lower] * (1.0 - weight) + finite[upper] * weight


def _milliseconds(later: datetime, earlier: datetime) -> float:
    return (later - earlier).total_seconds() * 1000.0


class SessionAnalyzer:
    """Deterministic, fail-closed session evidence analyzer."""

    _CANDIDATE_STAGE = {
        "STRATEGY_EVALUATED": "strategy_evaluated",
        "SIGNAL_GENERATED": "signal_generated",
        "CANDIDATE_CREATED": "candidate_created",
        "CANDIDATE_BLOCKED": "candidate_blocked",
        "CANDIDATE_RANKED": "candidate_ranked",
        "APPROVAL_REQUESTED": "approval_requested",
        "APPROVAL_DECIDED": "approval_decided",
        "ORDER_EVENT": "order_event",
        "FILL_EVENT": "fill_event",
        "POSITION_EVENT": "position_event",
        "OUTCOME_LABEL": "outcome_label",
    }
    _HARD_INVALID_QUALITY_STATES = {"UNKNOWN", "UNTRUSTED", "STALE"}
    _PARTIAL_QUALITY_STATES = {"PARTIAL", "DEGRADED", "FALLBACK", "RECOVERED_FALLBACK"}

    def analyze(self, events: Iterable[CanonicalEvent]) -> SessionAnalysis:
        ordered = sorted(events, key=lambda event: (event.event_time, event.event_id))
        if not ordered:
            raise ValueError("empty_session")
        session_ids = {event.session_id for event in ordered}
        if len(session_ids) != 1:
            raise ValueError("multiple_sessions")

        event_counts = Counter(event.event_type for event in ordered)
        authority_counts = Counter(event.authority_class for event in ordered)
        quality_counts = Counter(event.data_quality_state for event in ordered)
        source_counts = Counter(event.source_provider for event in ordered)
        instrument_keys = {event.instrument_key for event in ordered if event.instrument_key}
        strategy_versions = sorted({f"{event.strategy_id}:{event.strategy_version}" for event in ordered if event.strategy_id})

        source_receive_latency = [_milliseconds(event.receive_time, event.source_time) for event in ordered if event.source_time is not None and event.receive_time >= event.source_time]
        receive_persist_latency = [_milliseconds(event.persist_time, event.receive_time) for event in ordered if event.persist_time >= event.receive_time]
        event_gaps_ms = [_milliseconds(current.event_time, previous.event_time) for previous, current in zip(ordered, ordered[1:]) if current.event_time >= previous.event_time]

        producer_sequences: dict[str, list[int]] = defaultdict(list)
        for event in ordered:
            if event.producer_sequence is not None:
                producer_sequences[event.source_component].append(event.producer_sequence)
        sequence_gaps: dict[str, int] = {}
        for component, sequences in producer_sequences.items():
            sequence_gaps[component] = sum(max(current - previous - 1, 0) for previous, current in zip(sequences, sequences[1:]))

        required_lifecycle = {
            "SESSION_STARTED": event_counts["SESSION_STARTED"] > 0,
            "SESSION_ENDED": event_counts["SESSION_ENDED"] > 0,
        }
        invalid_quality_events = sum(
            count
            for state, count in quality_counts.items()
            if state.upper().startswith("INVALID")
            or state.upper() in self._HARD_INVALID_QUALITY_STATES
        )
        partial_quality_events = sum(
            count
            for state, count in quality_counts.items()
            if state.upper() in self._PARTIAL_QUALITY_STATES
        )
        lifecycle_complete = all(required_lifecycle.values())
        sequence_gap_total = sum(sequence_gaps.values())
        manifest_valid = (
            lifecycle_complete
            and invalid_quality_events == 0
            and partial_quality_events == 0
            and sequence_gap_total == 0
        )
        if manifest_valid:
            verdict = "VALID_OFFLINE_SESSION_EVIDENCE"
        elif not lifecycle_complete:
            verdict = "INCOMPLETE_SESSION"
        elif sequence_gap_total:
            verdict = "INVALID_SEQUENCE_COVERAGE"
        elif invalid_quality_events:
            verdict = "INVALID_DATA_QUALITY"
        else:
            verdict = "PARTIAL_DATA_QUALITY"

        manifest = {
            "session_id": ordered[0].session_id,
            "run_id": ordered[0].run_id,
            "first_event_time": ordered[0].event_time.isoformat(),
            "last_event_time": ordered[-1].event_time.isoformat(),
            "event_count": len(ordered),
            "event_types": dict(sorted(event_counts.items())),
            "source_providers": dict(sorted(source_counts.items())),
            "authority_classes": dict(sorted(authority_counts.items())),
            "data_quality_states": dict(sorted(quality_counts.items())),
            "instrument_count": len(instrument_keys),
            "strategy_versions": strategy_versions,
            "required_lifecycle": required_lifecycle,
            "producer_sequence_gaps": dict(sorted(sequence_gaps.items())),
            "producer_sequence_gap_total": sequence_gap_total,
            "invalid_quality_event_count": invalid_quality_events,
            "partial_quality_event_count": partial_quality_events,
            "source_to_receive_latency_ms": {
                "count": len(source_receive_latency),
                "p50": _percentile(source_receive_latency, 0.50),
                "p95": _percentile(source_receive_latency, 0.95),
                "p99": _percentile(source_receive_latency, 0.99),
                "max": max(source_receive_latency) if source_receive_latency else None,
            },
            "receive_to_persist_latency_ms": {
                "count": len(receive_persist_latency),
                "p50": _percentile(receive_persist_latency, 0.50),
                "p95": _percentile(receive_persist_latency, 0.95),
                "p99": _percentile(receive_persist_latency, 0.99),
                "max": max(receive_persist_latency) if receive_persist_latency else None,
            },
            "event_gap_ms": {
                "count": len(event_gaps_ms),
                "median": median(event_gaps_ms) if event_gaps_ms else None,
                "p95": _percentile(event_gaps_ms, 0.95),
                "max": max(event_gaps_ms) if event_gaps_ms else None,
            },
            "event_log_sha256": event_log_hash(ordered),
            "verdict": verdict,
            "valid": manifest_valid,
        }

        stage_counts = Counter()
        candidate_stages: dict[str, set[str]] = defaultdict(set)
        blockers = Counter()
        for event in ordered:
            stage = self._CANDIDATE_STAGE.get(event.event_type)
            if stage:
                stage_counts[stage] += 1
                if event.candidate_id:
                    candidate_stages[event.candidate_id].add(stage)
            if event.event_type == "CANDIDATE_BLOCKED":
                reason = str(event.payload.get("reason") or event.payload.get("block_reason") or "UNSPECIFIED")
                blockers[reason] += 1

        complete_candidates = sum(1 for stages in candidate_stages.values() if "candidate_created" in stages and "outcome_label" in stages)
        candidate_funnel = {
            "stage_counts": dict(sorted(stage_counts.items())),
            "candidate_count": len(candidate_stages),
            "complete_candidate_to_outcome_count": complete_candidates,
            "blocker_counts": dict(sorted(blockers.items())),
            "candidate_stages": {candidate_id: sorted(stages) for candidate_id, stages in sorted(candidate_stages.items())},
        }

        runtime_timeline = [
            {
                "event_time": event.event_time.isoformat(),
                "event_type": event.event_type,
                "source_component": event.source_component,
                "data_quality_state": event.data_quality_state,
                "payload": event.payload,
            }
            for event in ordered
            if event.event_type in {
                "SESSION_STARTED",
                "SESSION_ENDED",
                "FEED_TRUTH_UPDATED",
                "RUNTIME_HEALTH_UPDATED",
                "RISK_STATE_CHANGED",
                "INCIDENT_RAISED",
            }
        ]

        candidate_created = stage_counts["candidate_created"]
        outcome_labels = stage_counts["outcome_label"]
        outcome_readiness = {
            "candidate_created_count": candidate_created,
            "outcome_label_count": outcome_labels,
            "candidate_to_outcome_coverage": outcome_labels / candidate_created if candidate_created else None,
            "ready_for_strategy_diagnosis": bool(manifest_valid and candidate_created > 0 and complete_candidates == candidate_created),
            "ready_for_profitability_claim": False,
            "reason": "OFFLINE_EVIDENCE_ONLY_REQUIRES_CAUSAL_OPTION_FILL_AND_HOLDOUT_CERTIFICATION",
        }

        return SessionAnalysis(manifest, candidate_funnel, runtime_timeline, outcome_readiness)
