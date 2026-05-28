# EDGE-92 — Feed Fault Replay Scenarios

## Purpose

EDGE-92 adds deterministic replay evidence for feed-fault scenarios before the strategy replay proof pack.

The goal is to prove whether replayed candidates should be blocked when feed truth is unsafe, stale, disconnected, incomplete, or symbol-specific unhealthy.

## Scope

This PR adds read-only evidence only:

- `core/feed_fault_replay_scenarios.py`
- `tests/test_feed_fault_replay_scenarios.py`
- this documentation
- agent-review evidence
- TODO sequencing update

## Reused contracts

EDGE-92 reuses existing feed contracts instead of creating a parallel model:

- `core.feed_health_truth.classify_feed_health_truth(...)`
- `core.feed_hold_gate.classify_feed_hold(...)`

## Scenario coverage

The replay evidence covers:

- healthy feed clear path
- websocket disconnected
- stale LTP tick age
- stale depth tick age
- option-feed block reason by symbol
- missing candidate id
- invalid feed payload
- expectation mismatch between expected replay outcome and actual hold behavior
- batch report summary across clear and blocked scenarios

## Output contract

`build_feed_fault_replay_evidence(...)` returns one scenario evidence row.

`build_feed_fault_replay_report(...)` returns a batch report with:

- schema version
- source
- status
- scenario counts
- blocked scenario count
- clear scenario count
- invalid scenario count
- reasons
- evidence rows
- metadata

Payloads are explicitly read-only:

- `read_only=True`
- `append=False`
- `is_order_action=False`
- `broker_api_called=False`
- `live_order_action=False`
- `broker_order_action=False`

## Boundaries

EDGE-92 does not:

- change ranking
- change strategy behavior
- change execution behavior
- wire dashboard/UI
- write runtime artifacts
- reconnect feeds
- resubscribe tokens
- mutate live state

## Acceptance proof

Run:

```bash
pytest tests/test_feed_fault_replay_scenarios.py -q
```

Expected result: all focused tests pass.

## Follow-up

After EDGE-92 is merged green, continue to PR #318 — EDGE-93 Strategy Replay Proof Pack.
