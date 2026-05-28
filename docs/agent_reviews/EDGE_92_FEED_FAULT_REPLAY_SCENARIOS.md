# Agent Review — EDGE-92 Feed Fault Replay Scenarios

## Agent Work Contract

Build EDGE-92 as a narrow replay-evidence PR after EDGE-91A. The work must remain deterministic, read-only, and limited to feed-fault replay proof.

## Scope Guard

In scope: `core/feed_fault_replay_scenarios.py`, focused tests, docs, agent review, and TODO sequencing.

Out of scope: UI changes, runtime wiring, strategy behavior, ranking behavior, allocation behavior, feed reconnect behavior, token resubscribe behavior, and execution behavior.

Files changed: `core/feed_fault_replay_scenarios.py`, `tests/test_feed_fault_replay_scenarios.py`, `docs/EDGE_92_FEED_FAULT_REPLAY_SCENARIOS.md`, `docs/agent_reviews/EDGE_92_FEED_FAULT_REPLAY_SCENARIOS.md`, and `docs/EDGE_TODO.md`.

Files not touched: runtime entrypoints, dashboard files, strategy providers, ranking modules, execution modules, broker modules, and feed websocket lifecycle code.

## Grill Me Review

Weak assumption: feed-fault replay could become fake precision if it invents feed semantics.

Mitigation: EDGE-92 reuses existing `classify_feed_health_truth(...)` and `classify_feed_hold(...)` contracts.

Failure mode: a healthy scenario could be treated as blocked, or an unsafe scenario could be treated as clear.

Mitigation: tests cover healthy, disconnected, stale, option-feed, invalid, and expectation mismatch paths.

Missing proof: this PR does not prove strategy expectancy or final edge. It only proves feed-fault replay classification.

Verdict: proceed only as read-only replay evidence.

## Hermes Review

Scope pass/fail: PASS.

Boundary violations: none expected.

The module does not import runtime, dashboard, strategy, ranking, execution, or feed websocket lifecycle modules.

Protected behavior is represented as evidence only. No reconnect, resubscribe, ranking, or execution behavior is changed.

Verdict: PASS if CI confirms changed-path scope and tests.

## GSD Review

Purpose: add deterministic feed-fault replay scenarios.

Scope: read-only replay evidence only.

Files changed: listed in Scope Guard.

Tests or reason not required: focused tests are required and included.

Evidence: `pytest tests/test_feed_fault_replay_scenarios.py -q`.

Risks: future PRs may confuse replay evidence with runtime feed recovery. EDGE-92 intentionally does not recover feeds.

Next PR: EDGE-93 Strategy Replay Proof Pack.

## QA / Safety Review

Focused tests cover:

- healthy feed clear path
- websocket disconnected
- stale LTP and depth ages
- option-feed symbol block
- missing candidate id
- invalid feed payload
- expectation mismatch
- batch report summary
- read-only payload fields

Required non-action proof: `is_order_action=false`, `broker_api_called=false`, `live_order_action=false`, `broker_order_action=false`.

## Acceptance Proof

Run:

```bash
pytest tests/test_feed_fault_replay_scenarios.py -q
```

Expected: all focused tests pass.

Evidence auditor fields:

- mode: PAPER
- candidate_id: EDGE-92-FEED-FAULT-REPLAY
- decision: FEED_FAULT_REPLAY_EVIDENCE_ONLY
- reason: READ_ONLY_FEED_FAULT_REPLAY
- timestamp: 2026-05-28T04:05:00Z
- is_order_action: false
- broker_api_called: false
- source: docs/agent_reviews/EDGE_92_FEED_FAULT_REPLAY_SCENARIOS.md

## Runtime Proof Required After Merge

No runtime proof is required because EDGE-92 is not wired into runtime behavior.

Future runtime consumers must provide separate integration proof before using this evidence in live or paper flows.

## What This PR Does Not Prove

This PR does not prove strategy edge, ranking quality, execution readiness, feed recovery, dashboard behavior, or paper/live readiness.

It only proves deterministic feed-fault replay evidence generation.

## Human Approval

Human review is required before merge because EDGE-92 is part of the replay and edge-readiness proof chain.

## High-Risk Path Review

high-risk path review: this PR touches `core/`. The new core file is read-only replay evidence and does not import runtime, dashboard, strategy, ranking, execution, or feed websocket lifecycle modules.
