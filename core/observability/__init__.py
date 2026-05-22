"""Read-only observability identity helpers for Tradebot.

The observability package must not mutate trading behavior. It only creates
stable identifiers and context payloads that later tracing, logging, metrics,
and evidence writers can reuse.
"""

from core.observability.context import ObservabilityContext
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
    "ObservabilityIdentityError",
    "ObservabilityIds",
    "build_candidate_id",
    "build_cycle_id",
    "build_run_id",
    "build_span_id",
    "build_trace_id",
    "normalize_identity_component",
]
