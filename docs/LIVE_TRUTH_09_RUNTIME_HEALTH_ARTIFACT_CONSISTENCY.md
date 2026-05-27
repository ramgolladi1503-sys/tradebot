# LIVE-TRUTH-09 — Runtime Health Artifact Consistency

## Purpose

This PR adds a read-only evidence reducer that checks whether latest runtime-health artifacts agree on core runtime truth fields.

It answers one narrow question:

> Are the runtime-health artifacts telling the same story, or are they contradicting each other?

This is not a runtime integration PR.

## Scope

Included:

- Add `core/live_truth_runtime_health_artifact_consistency.py`
- Add focused tests in `tests/test_live_truth_09_runtime_health_artifact_consistency.py`
- Produce a deterministic payload suitable for latest evidence files
- Classify artifact sets as:
  - `RUNTIME_HEALTH_ARTIFACTS_CONSISTENT`
  - `RUNTIME_HEALTH_ARTIFACTS_REVIEW`
  - `RUNTIME_HEALTH_ARTIFACTS_INCONSISTENT`
  - `RUNTIME_HEALTH_ARTIFACTS_BLOCKED`
- Preserve read-only and append-false evidence semantics
- Update `docs/EDGE_TODO.md`

Excluded:

- No runtime wiring
- No UI changes
- No ranking changes
- No strategy scoring changes
- No feed recovery changes
- No lifecycle changes
- No execution behavior changes

## What is checked

The reducer accepts a mapping of artifact name to payload. It extracts normalized identity fields from each artifact:

| Field | Example accepted keys |
| --- | --- |
| runtime mode | `runtime_mode`, `mode`, `session_mode`, `trading_mode` |
| market-open state | `market_open`, `is_market_open` |
| runtime state | `runtime_state`, `state`, `runtime_status`, `status` |
| feed health | `feed_ok`, `feed_healthy`, `feed_health_ok`, `is_feed_ok` |
| websocket connection | `ws_connected`, `websocket_connected`, `websocket_ok`, `is_ws_connected` |

The reducer then reports:

- missing required artifacts
- invalid artifact payloads
- missing required identity fields
- inconsistent runtime mode
- inconsistent market-open state
- inconsistent runtime state
- inconsistent feed health
- inconsistent websocket connection

## Status rules

### Consistent

Returned when all valid artifacts agree on configured fields and no required artifact is missing.

### Review

Returned when artifacts do not contradict each other but at least one configured identity field is missing.

Example:

```python
{
    "runtime_snapshot_latest": {"runtime_mode": "LIVE", "market_open": True, "runtime_state": "RUNNING"},
    "feed_runtime_latest": {"runtime_mode": "LIVE", "market_open": True},
}
```

This is a review state because `feed_runtime_latest` does not expose `runtime_state`.

### Inconsistent

Returned when valid artifacts contradict each other.

Example:

```python
{
    "runtime_snapshot_latest": {"runtime_mode": "LIVE", "market_open": True, "runtime_state": "RUNNING"},
    "top_opportunities_latest": {"runtime_mode": "LIVE", "market_open": False, "runtime_state": "RUNNING"},
}
```

This is inconsistent because one artifact says market is open and another says closed.

### Blocked

Returned when there are no artifacts, a required artifact is missing, config is invalid, or at least one artifact payload is not a mapping-compatible payload.

## Safety guarantees

The report payload always marks itself as read-only evidence:

```json
{
  "read_only": true,
  "append": false,
  "is_order_action": false,
  "broker_api_called": false,
  "live_order_action": false,
  "broker_order_action": false
}
```

The module writes only when `write_runtime_health_artifact_consistency_evidence(...)` is explicitly called by a test or future scoped integration.

## Test command

```bash
PYTHONPATH=. python -m pytest tests/test_live_truth_09_runtime_health_artifact_consistency.py
```

## Acceptance gates

- Consistent artifacts produce a consistent report
- Missing required artifact blocks the report
- Invalid artifact payload blocks the report
- Contradictory runtime mode is detected
- Contradictory market-open state is detected
- Missing required identity field creates review evidence
- Empty artifact input blocks the report
- Invalid field config blocks the report
- Nested artifact containers are supported
- Evidence writing is atomic through existing JSON writer
- Payload is JSON-serializable
