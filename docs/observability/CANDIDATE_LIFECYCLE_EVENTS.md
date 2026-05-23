# Candidate Lifecycle Decision Events

Status: PR-OBS-05  
Scope: read-only candidate lifecycle event shell

## Purpose

Candidate lifecycle events make candidate movement reviewable from birth to terminal state.

This PR adds a small shell for building validated candidate lifecycle events. It does not wire those events into the strategy, ranking, risk, dashboard, paper execution, or live runtime paths.

## Contract

The emitter must build validated events for:

- `candidate.generated`
- `candidate.normalized`
- `candidate.scored`
- `candidate.ranked`
- `candidate.downgraded`
- `candidate.blocked`
- `candidate.displayed`
- `candidate.paper_ready`
- `candidate.paper_submitted`
- `candidate.ignored`

Every event must preserve:

- `run_id`
- `cycle_id`
- `trace_id`
- `span_id`
- `candidate_id`
- `stage`
- `decision`
- `timestamp`
- `execution_mode`
- `is_order_action: false`
- `broker_api_called: false`

Blocked, downgraded, and ignored candidate events must include a reason.

## Out of scope

This PR does not add:

- candidate pipeline wiring
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
- lifecycle evidence aggregation

## Example

```python
from core.observability import CandidateLifecycleEventEmitter

emitter = CandidateLifecycleEventEmitter(context, candidate_id="candidate_1")
event = emitter.generated(timestamp=now, symbol="NIFTY")
payload = event.as_dict()
```

Optional JSON-line write:

```python
emitter.write_event(logger, event)
```

## Acceptance proof

Run:

```bash
python -m pytest tests/test_observability_candidate_lifecycle.py tests/test_observability_events.py tests/test_observability_json_logger.py
python scripts/validate_agent_review_evidence.py
```

## Safety note

This shell creates observability data only. It must not be treated as proof that every live candidate already has lifecycle evidence. That proof requires later safe pipeline wiring and evidence checks.
