# Agent Review Evidence — PR-OBS-03 Structured JSON Logging Adapter

## Agent Work Contract

Goal: add the smallest structured JSON logging adapter after the decision-event schema.

Scope:

- add `core/observability/json_logger.py`
- export adapter helpers from `core/observability/__init__.py`
- add focused tests for deterministic JSONL serialization and stream writes
- document the adapter contract

Out of scope:

- runtime instrumentation
- file sink ownership
- async logging
- tracing backend wiring
- metrics backend wiring
- dashboard work
- strategy changes
- ranking changes
- risk changes

## Grill Me Review

Risk: adapter could accept invalid payloads and create false evidence.

Control: every record validates through `validate_event_payload` before serialization or write.

Risk: writer could partially write invalid events.

Control: `write_event` builds and validates the record before writing to the stream; invalid events leave the stream unchanged in tests.

Risk: snapshots become noisy.

Control: JSON output uses sorted keys and compact separators.

## Hermes Review

The adapter is intentionally simple and deterministic. It owns no runtime lifecycle and does not create a file sink. Future PRs can wire it into runtime once the contract is stable.

## GSD Review

This PR moves observability forward without pretending to solve ranking, feed quality, or execution quality. It creates a safe JSONL format that later PRs can use for candidate lifecycle logging.

## Scope Guard

No trading behavior is changed. No strategy, ranker, risk, broker, or dashboard module is modified.

## Acceptance Evidence

Expected command:

```bash
python -m pytest tests/test_observability_json_logger.py tests/test_observability_events.py
```

Required proof:

- event JSONL output ends with one newline
- output is valid JSON
- keys are deterministic
- invalid raw payloads are rejected
- stream writer writes one line and flushes
- invalid candidate event is rejected before stream write
