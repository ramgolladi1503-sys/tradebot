# OpenTelemetry Tracing Integration

Status: PR-OBS-07  
Scope: disabled-by-default tracing adapter only

## Purpose

Tracing lets Tradebot follow one runtime cycle or candidate path through named spans after identity and event contracts are stable.

This PR adds a safe tracing adapter. It does not wire tracing into live runtime, strategy, ranking, risk, dashboard, paper execution, or broker paths.

## Span contract

Core span names:

```text
runtime.cycle
feed.snapshot_build
feed.freshness_check
option_chain.resolve
strategy.generate_candidates
candidate.normalize
candidate.score
candidate.rank
risk.evaluate
dashboard.write_state
paper.submit
```

Every span attribute set should preserve available observability context fields:

- `run_id`
- `cycle_id`
- `trace_id`
- `span_id`
- `candidate_id` when available
- `stage`
- `execution_mode`
- `strategy_id` when available
- `symbol` when available

## Safety contract

Tracing is disabled by default.

When disabled, span calls return metadata and do not start a backend span.

When enabled with an injected tracer, span calls pass attributes to the tracer.

If the tracing backend fails, the adapter reports the error in the trace result and does not raise into caller logic.

Tracing must never:

- change strategy output
- change ranking output
- change risk output
- change dashboard output
- call brokers
- place orders
- rescue missing data
- hide business exceptions
- convert advisory data into executable data

## Out of scope

This PR does not add:

- runtime wiring
- OpenTelemetry package dependency
- collector configuration
- Tempo or Jaeger setup
- Prometheus metrics
- Grafana dashboards
- Loki log correlation
- evidence aggregation

The local stack comes later after metrics and tracing contracts are stable.

## Example

```python
from core.observability import ObservabilityTracer

tracer = ObservabilityTracer(enabled=False)
result = tracer.span("candidate.score", context, latency_ms=12)
```

## Acceptance proof

Run:

```bash
python -m pytest tests/test_observability_tracing.py tests/test_observability_ids.py tests/test_observability_events.py
python scripts/validate_agent_review_evidence.py
```

## Runtime proof required later

A future wiring PR must prove actual runtime spans are emitted from safe boundaries and that tracing failure does not change trading behavior.
