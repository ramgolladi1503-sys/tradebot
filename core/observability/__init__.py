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

__all__ = [
    "CORE_OBSERVABILITY_SPANS",
    "DEFAULT_OBSERVABILITY_METRICS",
    "CandidateLifecycleEventEmitter",
    "CandidateLifecycleEventError",
    "FeedStateEventEmitter",
    "FeedStateEventError",
    "MetricSample",
    "ObservabilityContext",
    "ObservabilityEvent",
    "ObservabilityEventError",
    "ObservabilityIdentityError",
    "ObservabilityIds",
    "ObservabilityJsonLogError",
    "ObservabilityJsonLogRecord",
    "ObservabilityJsonLogger",
    "ObservabilityMetricError",
    "ObservabilityMetricsRegistry",
    "ObservabilityTracer",
    "REQUIRED_EVENT_FIELDS",
    "RuntimeCycleEventEmitter",
    "RuntimeCycleEventError",
    "TraceSpanResult",
    "build_candidate_id",
    "build_cycle_id",
    "build_default_metrics_registry",
    "build_run_id",
    "build_span_id",
    "build_trace_id",
    "event_to_json_line",
    "normalize_identity_component",
    "payload_to_json_line",
    "trace_attributes",
    "validate_event_payload",
]
