from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from core.observability.context import ObservabilityContext

CORE_OBSERVABILITY_SPANS = (
    "runtime.cycle",
    "feed.snapshot_build",
    "feed.freshness_check",
    "option_chain.resolve",
    "strategy.generate_candidates",
    "candidate.normalize",
    "candidate.score",
    "candidate.rank",
    "risk.evaluate",
    "dashboard.write_state",
    "paper.submit",
)


class SpanLike(Protocol):
    def set_attribute(self, key: str, value: object) -> None: ...


class TracerLike(Protocol):
    def start_span(self, name: str, attributes: Mapping[str, object]) -> object: ...


@dataclass(frozen=True)
class TraceSpanResult:
    name: str
    attributes: Mapping[str, object]
    enabled: bool
    started: bool
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        payload = {
            "name": self.name,
            "enabled": self.enabled,
            "started": self.started,
        }
        if self.error:
            payload["error"] = self.error
        payload.update(dict(self.attributes))
        return payload


@dataclass(frozen=True)
class ObservabilityTracer:
    """Disabled-by-default tracing adapter for observability spans."""

    enabled: bool = False
    tracer: TracerLike | None = None

    def span(self, name: str, context: ObservabilityContext, **attributes: object) -> TraceSpanResult:
        span_attributes = trace_attributes(context, **attributes)
        if not self.enabled or self.tracer is None:
            return TraceSpanResult(name=name, attributes=span_attributes, enabled=self.enabled, started=False)
        try:
            span = self.tracer.start_span(name, span_attributes)
            if hasattr(span, "set_attribute"):
                for key, value in span_attributes.items():
                    span.set_attribute(key, value)
            return TraceSpanResult(name=name, attributes=span_attributes, enabled=True, started=True)
        except Exception as exc:  # noqa: BLE001 - tracing must be non-fatal.
            return TraceSpanResult(
                name=name,
                attributes=span_attributes,
                enabled=True,
                started=False,
                error=f"{type(exc).__name__}:{exc}",
            )


@dataclass(frozen=True)
class OpenTelemetryTracerAdapter:
    """Small adapter around an OpenTelemetry tracer object."""

    tracer: object

    def start_span(self, name: str, attributes: Mapping[str, object]) -> object:
        if not hasattr(self.tracer, "start_span"):
            raise TypeError("tracer_missing_start_span")
        return self.tracer.start_span(name, attributes=dict(attributes))


def trace_attributes(context: ObservabilityContext, **attributes: object) -> dict[str, object]:
    payload = context.as_dict()
    payload.update(attributes)
    return payload


__all__ = [
    "CORE_OBSERVABILITY_SPANS",
    "ObservabilityTracer",
    "OpenTelemetryTracerAdapter",
    "TraceSpanResult",
    "trace_attributes",
]
