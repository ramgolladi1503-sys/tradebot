# Structured JSON Logging Adapter

Status: PR-OBS-03  
Scope: serialization adapter

## Purpose

The JSON logging adapter converts validated observability events into deterministic JSON lines.

This is the first small logging layer after the event schema. It gives future instrumentation one output format without wiring it into the runtime yet.

## Contract

The adapter must:

- accept `ObservabilityEvent` objects
- validate serialized payloads using `validate_event_payload`
- emit exactly one JSON object per line
- sort keys for deterministic snapshots and diffs
- preserve explicit fields:
  - `is_order_action: false`
  - `broker_api_called: false`
- fail before writing if the event or payload is invalid

## Out of scope

This PR does not add:

- runtime instrumentation
- file rotation
- async logging
- OpenTelemetry exporter wiring
- Loki wiring
- dashboard wiring
- strategy changes
- ranking changes
- risk changes

## Example

```python
from io import StringIO

from core.observability import ObservabilityJsonLogger

stream = StringIO()
logger = ObservabilityJsonLogger(stream)
logger.write_event(event)
```

## Acceptance proof

Run:

```bash
python -m pytest tests/test_observability_json_logger.py tests/test_observability_events.py
```
