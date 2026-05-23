# Feed Freshness and Fallback Safety Events

Status: PR-OBS-06  
Scope: read-only feed freshness and quote-source event shell

## Purpose

Feed-state events make stale feed and recovered quote states visible in observability records before any future runtime wiring is added.

This PR adds a small shell for building validated feed and quote-source events. It does not read market data, recover quotes, change candidate state, change strategy output, alter risk, update dashboard state, or call broker paths.

## Contract

The emitter builds validated events for:

- `feed.fresh`
- `feed.stale`
- `quote.real`
- `quote.missing`
- `quote.fallback_used`
- `execution.blocked_fallback`
- `execution.blocked_stale_feed`

Every event must preserve:

- `run_id`
- `cycle_id`
- `trace_id`
- `span_id`
- `stage`
- `decision`
- `timestamp`
- `execution_mode`
- `is_order_action: false`
- `broker_api_called: false`

Candidate-scoped quote or block events must preserve `candidate_id`.

Blocked events must include a reason.

## Safety invariant

The shell rejects unsafe serialized states:

```text
fallback_state = recovered_fallback and executable = true
feed_state = stale and executable = true
fallback_state = recovered_fallback and decision = executable
feed_state = stale and decision = executable
```

Fallback quote data may be visible or displayable for review, but this shell must never describe it as executable.

Stale feed state may be visible for debugging, but this shell must never describe it as executable.

## Out of scope

This PR does not add:

- live feed wiring
- strategy changes
- ranking changes
- risk changes
- dashboard changes
- paper execution changes
- broker calls
- order actions
- OpenTelemetry
- Prometheus
- Grafana, Loki, Tempo, or Jaeger
- evidence aggregation

## Example

```python
from core.observability import FeedStateEventEmitter

emitter = FeedStateEventEmitter(context)
event = emitter.feed_stale(timestamp=now, feed_age_ms=5000)
payload = event.as_dict()
```

Optional JSON-line write:

```python
emitter.write_event(logger, event)
```

## Acceptance proof

Run:

```bash
python -m pytest tests/test_observability_feed_state.py tests/test_observability_events.py tests/test_observability_json_logger.py
python scripts/validate_agent_review_evidence.py
```

## Safety note

This shell creates observability data only. It must not be treated as proof that real feed runtime is already instrumented. Runtime proof requires a later scoped wiring PR.
