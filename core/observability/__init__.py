"""Observability helpers for Tradebot."""

from core.observability.candidate_lifecycle import (
    CandidateLifecycleEventEmitter,
    CandidateLifecycleEventError,
)
from core.observability.context import ObservabilityContext
from core.observability.events import (
    ObservabilityEvent,
    ObservabilityEventError,
    REQUIRED_EVENT_FIELDS,
    validate_event_payload,
)
from core.observability.evidence_bundle import (
    EVIDENCE_FILENAMES,
    ObservabilityEvidenceBundle,
    ObservabilityEvidenceBundleError,
    build_observability_evidence_bundle,
    write_observability_evidence_bundle,
)
from core.observability.feed_state import (
    FeedStateEventEmitter,
    FeedStateEventError,
)
from core.observability.ids import (
    ObservabilityIdentityError,
    ObservabilityIds,
    build_candidate_id,
    build_cycle_id,
    build_run_id,
    build_span_id,
    build_trace_id,
    normalize_identity_component,
)
from core.observability.json_logger import (
    ObservabilityJsonLogError,
    ObservabilityJsonLogRecord,
    ObservabilityJsonLogger,
    event_to_json_line,
    payload_to_json_line,
)
from core.observability.metrics import (
    DEFAULT_OBSERVABILITY_METRICS,
    MetricSample,
    ObservabilityMetricError,
    ObservabilityMetricsRegistry,
    build_default_metrics_registry,
)
from core.observability.runtime_cycle import (
    RuntimeCycleEventEmitter,
    RuntimeCycleEventError,
)
from core.observability.tracing import (
    CORE_OBSERVABILITY_SPANS,
    ObservabilityTracer,
    TraceSpanResult,
    trace_attributes,
)

from core.observability.candidate_attribution import (
    CandidateEmptyClass,
    CandidateLifecycleLedger,
    CandidateLifecycleStage,
    CandidateTransitionRecord,
    EmptyPoolSummaryClass,
    StrategyCoverageTracker,
    StrategyEvaluationAttribution,
    StrategyMetricsRecord,
)
from core.observability.independent_verifier import (
    IndependentObservabilityVerifier,
    VerificationError,
)
from core.observability.sidecar_reporter import (
    DEFAULT_REPORT_INTERVAL_MINUTES,
    SidecarReporter,
)
from core.observability.stage_lineage import (
    CANONICAL_CHECKPOINT_ORDER,
    STAGE_CONTRACTS,
    PipelineCheckpoint,
    StageContractDefinition,
    StageRecord,
    StageStatus,
    create_stage_record,
)
from core.observability.token_health_model import (
    RoleAwareHealthReport,
    RoleMetrics,
    SystemHealthStatus,
    TokenDependencyGraph,
    TokenObservation,
    TokenRole,
)
from core.observability.trace_pulse import (
    DiagnosticPulseRing,
    FirstDivergenceReport,
    RCACandidate,
    analyze_first_divergence,
    generate_trace_id,
    get_global_pulse_ring,
)

from core.observability.production_bridge import (
    ProductionObservabilityBridge,
    get_production_candidate_ledger,
    get_production_pulse_ring,
    get_production_strategy_tracker,
    get_production_token_graph,
)

__all__ = [
    "CANONICAL_CHECKPOINT_ORDER",
    "CORE_OBSERVABILITY_SPANS",
    "DEFAULT_OBSERVABILITY_METRICS",
    "DEFAULT_REPORT_INTERVAL_MINUTES",
    "EVIDENCE_FILENAMES",
    "CandidateEmptyClass",
    "CandidateLifecycleEventEmitter",
    "CandidateLifecycleEventError",
    "CandidateLifecycleLedger",
    "CandidateLifecycleStage",
    "CandidateTransitionRecord",
    "DiagnosticPulseRing",
    "EmptyPoolSummaryClass",
    "FeedStateEventEmitter",
    "FeedStateEventError",
    "FirstDivergenceReport",
    "IndependentObservabilityVerifier",
    "MetricSample",
    "ObservabilityContext",
    "ObservabilityEvent",
    "ObservabilityEventError",
    "ObservabilityEvidenceBundle",
    "ObservabilityEvidenceBundleError",
    "ObservabilityIdentityError",
    "ObservabilityIds",
    "ObservabilityJsonLogError",
    "ObservabilityJsonLogRecord",
    "ObservabilityJsonLogger",
    "ObservabilityMetricError",
    "ObservabilityMetricsRegistry",
    "ObservabilityTracer",
    "PipelineCheckpoint",
    "ProductionObservabilityBridge",
    "RCACandidate",
    "REQUIRED_EVENT_FIELDS",
    "RoleAwareHealthReport",
    "RoleMetrics",
    "RuntimeCycleEventEmitter",
    "RuntimeCycleEventError",
    "STAGE_CONTRACTS",
    "SidecarReporter",
    "StageContractDefinition",
    "StageRecord",
    "StageStatus",
    "StrategyCoverageTracker",
    "StrategyEvaluationAttribution",
    "StrategyMetricsRecord",
    "SystemHealthStatus",
    "TokenDependencyGraph",
    "TokenObservation",
    "TokenRole",
    "TraceSpanResult",
    "VerificationError",
    "analyze_first_divergence",
    "build_candidate_id",
    "build_cycle_id",
    "build_default_metrics_registry",
    "build_observability_evidence_bundle",
    "build_run_id",
    "build_span_id",
    "build_trace_id",
    "create_stage_record",
    "event_to_json_line",
    "generate_trace_id",
    "get_global_pulse_ring",
    "get_production_candidate_ledger",
    "get_production_pulse_ring",
    "get_production_strategy_tracker",
    "get_production_token_graph",
    "normalize_identity_component",
    "payload_to_json_line",
    "trace_attributes",
    "validate_event_payload",
    "write_observability_evidence_bundle",
]
