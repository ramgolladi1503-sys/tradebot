from __future__ import annotations

from typing import Mapping

from core.observability import (
    CORE_OBSERVABILITY_SPANS,
    ObservabilityContext,
    ObservabilityIds,
    ObservabilityTracer,
    TraceSpanResult,
    trace_attributes,
)


def _context() -> ObservabilityContext:
    return ObservabilityContext(
        ids=ObservabilityIds(
            run_id="run_obs_07",
            cycle_id="cycle_obs_07_000001",
            trace_id="trace_obs_07",
            candidate_id="candidate_obs_07",
        ),
        stage="candidate.score",
        execution_mode="PAPER",
        attributes={"strategy_id": "opening_drive", "symbol": "NIFTY"},
    )


class _RecordingSpan:
    def __init__(self) -> None:
        self.attributes: dict[str, object] = {}

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value


class _RecordingTracer:
    def __init__(self) -> None:
        self.started: list[tuple[str, Mapping[str, object]]] = []
        self.span = _RecordingSpan()

    def start_span(self, name: str, attributes: Mapping[str, object]) -> _RecordingSpan:
        self.started.append((name, dict(attributes)))
        return self.span


class _FailingTracer:
    def start_span(self, name: str, attributes: Mapping[str, object]) -> object:
        raise RuntimeError("trace backend unavailable")


def test_core_span_names_are_declared() -> None:
    assert "runtime.cycle" in CORE_OBSERVABILITY_SPANS
    assert "feed.freshness_check" in CORE_OBSERVABILITY_SPANS
    assert "candidate.score" in CORE_OBSERVABILITY_SPANS
    assert "risk.evaluate" in CORE_OBSERVABILITY_SPANS


def test_trace_attributes_preserve_identity_and_context_fields() -> None:
    attrs = trace_attributes(_context(), latency_ms=12, score=0.84)

    assert attrs["run_id"] == "run_obs_07"
    assert attrs["cycle_id"] == "cycle_obs_07_000001"
    assert attrs["trace_id"] == "trace_obs_07"
    assert attrs["candidate_id"] == "candidate_obs_07"
    assert attrs["stage"] == "candidate.score"
    assert attrs["execution_mode"] == "PAPER"
    assert attrs["strategy_id"] == "opening_drive"
    assert attrs["symbol"] == "NIFTY"
    assert attrs["latency_ms"] == 12
    assert attrs["score"] == 0.84


def test_disabled_tracer_does_not_start_span() -> None:
    backend = _RecordingTracer()
    tracer = ObservabilityTracer(enabled=False, tracer=backend)

    result = tracer.span("candidate.score", _context(), latency_ms=3)

    assert isinstance(result, TraceSpanResult)
    assert result.enabled is False
    assert result.started is False
    assert result.error is None
    assert backend.started == []
    assert result.as_dict()["trace_id"] == "trace_obs_07"


def test_enabled_tracer_records_span_attributes() -> None:
    backend = _RecordingTracer()
    tracer = ObservabilityTracer(enabled=True, tracer=backend)

    result = tracer.span("candidate.score", _context(), latency_ms=5)

    assert result.enabled is True
    assert result.started is True
    assert result.error is None
    assert backend.started == [("candidate.score", result.attributes)]
    assert backend.span.attributes["trace_id"] == "trace_obs_07"
    assert backend.span.attributes["candidate_id"] == "candidate_obs_07"
    assert backend.span.attributes["latency_ms"] == 5


def test_tracing_failure_is_reported_without_raising() -> None:
    tracer = ObservabilityTracer(enabled=True, tracer=_FailingTracer())

    result = tracer.span("runtime.cycle", _context())

    assert result.enabled is True
    assert result.started is False
    assert result.error == "RuntimeError:trace backend unavailable"
    assert result.as_dict()["trace_id"] == "trace_obs_07"


def test_tracing_does_not_mutate_business_result() -> None:
    tracer = ObservabilityTracer(enabled=True, tracer=_FailingTracer())
    business_result = {"decision": "hold"}

    trace_result = tracer.span("strategy.generate_candidates", _context(), decision=business_result["decision"])

    assert trace_result.started is False
    assert business_result["decision"] == "hold"
