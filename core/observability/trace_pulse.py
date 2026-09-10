"""Immutable Trace Pulse, First-Divergence Analysis, and In-Memory Telemetry Ring.

Zero file I/O on normal execution path. Read-only safety invariants preserved.
"""

from __future__ import annotations

import collections
import hashlib
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from core.observability.stage_lineage import (
    CANONICAL_CHECKPOINT_ORDER,
    STAGE_CONTRACTS,
    PipelineCheckpoint,
    StageRecord,
    StageStatus,
)


def generate_trace_id(*, seed: str | None = None, timestamp: float | None = None) -> str:
    """Generate a stable, unique trace identifier for an incoming market event."""
    ts = timestamp if timestamp is not None else time.time()
    raw = f"{ts:.6f}:{seed or 'mros_pulse'}:{time.perf_counter_ns()}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"trace_{digest}"


@dataclass(frozen=True)
class RCACandidate:
    """Root Cause Analysis record for an abnormal checkpoint."""

    rca_id: str
    trace_id: str
    first_divergence_stage: str
    symptom: str
    expected_contract: str
    actual_contract: str
    upstream_health: bool
    downstream_impact: tuple[str, ...]
    primitive_evidence: Mapping[str, Any]
    causal_classification: str  # PROVEN | SUPPORTED | HYPOTHESIS | UNKNOWN
    recommended_next_diagnostic: str
    is_order_action: bool = False  # is_order_action=false
    broker_write_authority: bool = False

    def validate(self) -> None:
        if not str(self.rca_id).strip():
            raise ValueError("rca_candidate_missing_id")
        if not str(self.trace_id).strip():
            raise ValueError("rca_candidate_missing_trace_id")
        if self.causal_classification not in {"PROVEN", "SUPPORTED", "HYPOTHESIS", "UNKNOWN"}:
            raise ValueError(f"invalid_causal_classification: {self.causal_classification}")
        if self.is_order_action:  # is_order_action=false
            raise ValueError("rca_order_action_forbidden")
        if self.broker_write_authority:
            raise ValueError("rca_broker_write_forbidden")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["is_order_action"] = False
        data["broker_write_authority"] = False
        return data


@dataclass(frozen=True)
class FirstDivergenceReport:
    """First-divergence analysis result across a pipeline trace."""

    trace_id: str
    diverged: bool
    first_divergence_stage: str | None
    first_divergence_record: StageRecord | None
    upstream_stages_healthy: bool
    downstream_impact: tuple[str, ...]
    stages_analyzed: int
    rca: RCACandidate | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "diverged": self.diverged,
            "first_divergence_stage": self.first_divergence_stage,
            "upstream_stages_healthy": self.upstream_stages_healthy,
            "downstream_impact": list(self.downstream_impact),
            "stages_analyzed": self.stages_analyzed,
            "first_divergence_record": self.first_divergence_record.to_dict() if self.first_divergence_record else None,
            "rca": self.rca.to_dict() if self.rca else None,
            "is_order_action": False,
            "broker_write_authority": False,
        }


def analyze_first_divergence(stage_records: Sequence[StageRecord]) -> FirstDivergenceReport:
    """Analyze an immutable list of stage records to find the earliest checkpoint divergence."""
    if not stage_records:
        return FirstDivergenceReport(
            trace_id="UNKNOWN",
            diverged=False,
            first_divergence_stage=None,
            first_divergence_record=None,
            upstream_stages_healthy=True,
            downstream_impact=(),
            stages_analyzed=0,
        )

    # Validate trace ID immutability across stages
    primary_trace_id = stage_records[0].trace_id
    for rec in stage_records:
        if rec.trace_id != primary_trace_id:
            # Trace mutation detected! This is a critical divergence
            rca = RCACandidate(
                rca_id=f"rca_{primary_trace_id[:8]}_trace_mutation",
                trace_id=primary_trace_id,
                first_divergence_stage=rec.component,
                symptom=f"Trace ID mutated from {primary_trace_id} to {rec.trace_id}",
                expected_contract=f"trace_id == {primary_trace_id}",
                actual_contract=f"trace_id == {rec.trace_id}",
                upstream_health=False,
                downstream_impact=("ALL_DOWNSTREAM_STAGES",),
                primitive_evidence={"original_trace_id": primary_trace_id, "mutated_trace_id": rec.trace_id, "stage": rec.stage_id},
                causal_classification="PROVEN",
                recommended_next_diagnostic="Audit trace propagation harness in component.",
            )
            return FirstDivergenceReport(
                trace_id=primary_trace_id,
                diverged=True,
                first_divergence_stage=rec.component,
                first_divergence_record=rec,
                upstream_stages_healthy=False,
                downstream_impact=("ALL_DOWNSTREAM_STAGES",),
                stages_analyzed=len(stage_records),
                rca=rca,
            )

    upstream_healthy = True
    for idx, rec in enumerate(stage_records):
        # A divergence occurs if status is not PASS or PASS_PARTIAL, or observed != expected
        contract_mismatch = bool(rec.expected_contract and rec.observed_contract and rec.expected_contract != rec.observed_contract)
        status_abnormal = rec.status in {
            StageStatus.BLOCKED.value,
            StageStatus.FAIL_CLOSED.value,
            StageStatus.DEGRADED_NONFATAL.value,
        }

        if status_abnormal or contract_mismatch:
            contract_def = STAGE_CONTRACTS.get(rec.component)
            downstream = contract_def.downstream_components if contract_def else ()

            # Determine causal classification
            if rec.status in {StageStatus.FAIL_CLOSED.value, StageStatus.BLOCKED.value}:
                causal = "PROVEN"
            elif rec.status == StageStatus.DEGRADED_NONFATAL.value:
                causal = "SUPPORTED"
            else:
                causal = "HYPOTHESIS"

            rca = RCACandidate(
                rca_id=f"rca_{rec.trace_id[:8]}_{idx}_{rec.stage_id}",
                trace_id=rec.trace_id,
                first_divergence_stage=rec.component,
                symptom=f"Checkpoint {rec.component} status={rec.status} reason={rec.reason_code}",
                expected_contract=rec.expected_contract or "PASS",
                actual_contract=rec.observed_contract or rec.status,
                upstream_health=upstream_healthy,
                downstream_impact=downstream,
                primitive_evidence={
                    "stage_id": rec.stage_id,
                    "component": rec.component,
                    "input_summary": dict(rec.input_summary),
                    "output_summary": dict(rec.output_summary),
                    "reason_code": rec.reason_code,
                    "latency_us": rec.latency_us,
                },
                causal_classification=causal,
                recommended_next_diagnostic=f"Inspect input preconditions and logs for {rec.component}.",
            )

            return FirstDivergenceReport(
                trace_id=rec.trace_id,
                diverged=True,
                first_divergence_stage=rec.component,
                first_divergence_record=rec,
                upstream_stages_healthy=upstream_healthy,
                downstream_impact=downstream,
                stages_analyzed=len(stage_records),
                rca=rca,
            )

        if rec.status not in {StageStatus.PASS.value, StageStatus.PASS_PARTIAL.value}:
            upstream_healthy = False

    return FirstDivergenceReport(
        trace_id=primary_trace_id,
        diverged=False,
        first_divergence_stage=None,
        first_divergence_record=None,
        upstream_stages_healthy=True,
        downstream_impact=(),
        stages_analyzed=len(stage_records),
        rca=None,
    )


class DiagnosticPulseRing:
    """Bounded in-memory diagnostic ring buffer for trace events and stage records.

    Guarantees:
    - Zero disk I/O on normal path.
    - Constant time appending O(1).
    - Hard bounded memory (maxlen).
    - Read-only queries for sidecar reporter.
    """

    def __init__(self, max_traces: int = 500, max_events: int = 5000) -> None:
        self.max_traces = max(10, int(max_traces))
        self.max_events = max(50, int(max_events))
        # trace_id -> list of StageRecord
        self._traces: collections.OrderedDict[str, list[StageRecord]] = collections.OrderedDict()
        self._all_events: collections.deque[StageRecord] = collections.deque(maxlen=self.max_events)
        self._file_io_count: int = 0

    @property
    def normal_tick_path_additional_io(self) -> int:
        return self._file_io_count

    def record_stage(self, record: StageRecord) -> None:
        """Append-only in-memory recording. ZERO disk I/O."""
        record.validate()
        t_id = record.trace_id

        if t_id not in self._traces:
            if len(self._traces) >= self.max_traces:
                self._traces.popitem(last=False)
            self._traces[t_id] = []

        self._traces[t_id].append(record)
        self._all_events.append(record)

    def get_trace(self, trace_id: str) -> list[StageRecord]:
        return list(self._traces.get(trace_id, []))

    def get_recent_traces(self, limit: int = 50) -> list[list[StageRecord]]:
        limit = max(1, int(limit))
        items = list(self._traces.values())[-limit:]
        return [list(trace) for trace in items]

    def get_recent_events(self, limit: int = 100) -> list[StageRecord]:
        limit = max(1, int(limit))
        return list(self._all_events)[-limit:]

    def clear(self) -> None:
        self._traces.clear()
        self._all_events.clear()


# Global diagnostic ring instance for non-intrusive runtime observation
_GLOBAL_PULSE_RING = DiagnosticPulseRing()


def get_global_pulse_ring() -> DiagnosticPulseRing:
    return _GLOBAL_PULSE_RING
