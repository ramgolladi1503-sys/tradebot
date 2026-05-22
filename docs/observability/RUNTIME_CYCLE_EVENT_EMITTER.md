# Runtime Cycle Event Emitter Shell

Status: PR-OBS-04  
Scope: read-only runtime-cycle event shell

## Purpose

The runtime-cycle event emitter creates validated observability events for one runtime cycle without wiring those events into the live trading runtime.

This shell exists so future runtime instrumentation can reuse a small, tested API instead of hand-building observability payloads.

## Contract

The emitter must:

- build `runtime.cycle.started` events
- build `runtime.cycle.completed` events
- build `runtime.cycle.failed` events
- use the existing `ObservabilityContext`
- use the existing `ObservabilityEvent` schema
- optionally write through `ObservabilityJsonLogger`
- preserve explicit safety fields:
  - `is_order_action: false`
  - `broker_api_called: false`
- reject failed-cycle events without a reason

## Out of scope

This PR does not add:

- live runtime wiring
- broker calls
- order actions
- strategy changes
- ranking changes
- risk changes
- dashboard changes
- OpenTelemetry
- Prometheus
- Grafana, Loki, Tempo, or Jaeger
- file sink ownership
- log rotation

## Example

```python
from core.observability import RuntimeCycleEventEmitter

emitter = RuntimeCycleEventEmitter(context)
event = emitter.cycle_started(timestamp=now, sequence=1)
payload = event.as_dict()
```

Optional JSON-line write:

```python
emitter.write_started(logger, timestamp=now, sequence=1)
```

## Acceptance proof

Run:

```bash
python -m pytest tests/test_observability_runtime_cycle.py tests/test_observability_json_logger.py tests/test_observability_events.py
python scripts/validate_agent_review_evidence.py
```

## Safety note

This shell creates observability data only. It must not be interpreted as proof that runtime observability is wired into live trading yet.
