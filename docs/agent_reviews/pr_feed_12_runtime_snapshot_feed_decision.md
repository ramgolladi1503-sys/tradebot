# Agent Review Evidence — PR-FEED-12 Runtime Snapshot Feed Decision

## Agent Work Contract

### Goal

Expose canonical feed-health truth in runtime snapshots as a read-only derived payload.

### Files changed

- `core/runtime_snapshot_producer.py`
- `tests/test_pr_feed_12_runtime_snapshot_feed_decision.py`
- `docs/PR_FEED_12_RUNTIME_SNAPSHOT_FEED_DECISION.md`
- `docs/agent_reviews/pr_feed_12_runtime_snapshot_feed_decision.md`

### Evidence Contract Fields

mode: PAPER
candidate_id: PR_FEED_12_RUNTIME_SNAPSHOT_FEED_DECISION
decision: READ_ONLY_RUNTIME_SNAPSHOT_FEED_DECISION
reason: Runtime snapshots now expose canonical feed-health truth derived from feed runtime evidence.
timestamp: 2026-05-24T20:21:04Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr_feed_12_runtime_snapshot_feed_decision.md

### Non-goals

- No websocket lifecycle changes.
- No reconnect logic.
- No resubscribe logic.
- No subscription changes.
- No token-selection changes.
- No strategy changes.
- No dashboard UI changes.
- No external adapter changes.
- No order intent.

## Grill Me Review

### Pushback

Raw feed runtime payload alone is not enough for downstream safety. Every consumer should not reinterpret raw feed flags differently.

### Required proof

- Healthy feed evidence creates a clear snapshot.
- Unhealthy feed evidence carries canonical blockers.
- Invalid feed payload fails closed.
- Unsafe runtime state fails closed.
- The snapshot remains read-only and non-action.

## Hermes Review

### Contract clarity

The new snapshot is derived from `feed_runtime_latest`; it does not mutate feed state or alter feed lifecycle behavior.

### Serialization

The payload is plain JSON-compatible dict/list/scalar data and is written through the existing atomic snapshot writer.

## GSD Review

### Minimality

The PR changes one producer file, adds one focused test file, and records documentation/evidence. It does not touch strategy, token selection, dashboard UI, websocket lifecycle, or external adapters.

### Determinism

Tests call the pure payload builder directly with fixed payloads and deterministic thresholds.

## QA / Safety Review

Tests assert:

- `read_only=True`
- `is_order_action=False`
- `append=False`
- `feed_ok=true` for healthy evidence
- `feed_ok=false` for unhealthy/invalid evidence
- canonical blockers are present for unsafe feed state

## Scope Guard

Confirmed not touched:

- Websocket lifecycle.
- Reconnect/resubscribe behavior.
- Subscription management.
- Token selection.
- Strategy code.
- Dashboard UI.
- External adapters.

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_pr_feed_12_runtime_snapshot_feed_decision.py
```

Expected:

- `feed_health_truth_latest` payload is deterministic.
- Healthy feed is clear.
- Unsafe feed is blocked.
- Invalid payload fails closed.

## Runtime Proof Required After Merge

After merge, capture a runtime snapshot sample proving:

- `runtime/feed_health_truth_latest.json` exists.
- The payload contains `feed_health_truth`.
- The payload carries `feed_ok` and `blockers`.
- The payload is derived from `feed_runtime_latest`.
- The snapshot remains read-only and non-action.

## What This PR Does Not Prove

- It does not prove websocket recovery.
- It does not prove token resolver correctness.
- It does not prove dashboard rendering.
- It does not prove strategy edge.

## Human Approval

Proceed only if CI is green and the PR remains limited to runtime snapshot feed-decision wiring.
