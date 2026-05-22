"""Read-only observability helpers for Tradebot.

The observability package must not mutate trading behavior. It only creates
stable identifiers, context payloads, and validated event dictionaries that
later tracing, logging, metrics, and evidence writers can reuse.
"""

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

__all__ = [
    "ObservabilityContext",
    "ObservabilityEvent",
    "ObservabilityEventError",
    "ObservabilityIdentityError",
    "ObservabilityIds",
    "REQUIRED_EVENT_FIELDS",
    "build_candidate_id",
    "build_cycle_id",
    "build_run_id",
    "build_span_id",
    "build_trace_id",
    "normalize_identity_component",
    "validate_event_payload",
]
