"""Observability helpers for Tradebot."""

from core.observability.context import ObservabilityContext
from core.observability.events import (
    ObservabilityEvent,
    ObservabilityEventError,
    REQUIRED_EVENT_FIELDS,
    validate_event_payload,
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
from core.observability.runtime_cycle import (
    RuntimeCycleEventEmitter,
    RuntimeCycleEventError,
)

__all__ = [
    "ObservabilityContext",
    "ObservabilityEvent",
    "ObservabilityEventError",
    "ObservabilityIdentityError",
    "ObservabilityIds",
    "ObservabilityJsonLogError",
    "ObservabilityJsonLogRecord",
    "ObservabilityJsonLogger",
    "REQUIRED_EVENT_FIELDS",
    "RuntimeCycleEventEmitter",
    "RuntimeCycleEventError",
    "build_candidate_id",
    "build_cycle_id",
    "build_run_id",
    "build_span_id",
    "build_trace_id",
    "event_to_json_line",
    "normalize_identity_component",
    "payload_to_json_line",
    "validate_event_payload",
]
