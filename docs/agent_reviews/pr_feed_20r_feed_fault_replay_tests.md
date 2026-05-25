# Agent Review Evidence — PR-FEED-20R Feed Fault Replay Tests

## Agent Work Contract

### Goal

Add end-to-end feed fault replay tests for the canonical feed-hardening acceptance proof before moving to strategy intelligence work.

### Files changed

- `tests/test_pr_feed_20r_feed_fault_replay_tests.py`
- `docs/PR_FEED_20R_FEED_FAULT_REPLAY_TESTS.md`
- `docs/agent_reviews/pr_feed_20r_feed_fault_replay_tests.md`

### Evidence Contract Fields

mode: PAPER
candidate_id: PR_FEED_20R_FEED_FAULT_REPLAY_TESTS
message_decision: READ_ONLY_FEED_FAULT_REPLAY_TESTS
decision: READ_ONLY_FEED_FAULT_REPLAY_TESTS
reason: Feed fault replay tests now prove healthy, stale, disconnected, subscription-failed, and recovered states through feed evidence, hold, and ranking contracts.
timestamp: 2026-05-25T10:32:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr_feed_20r_feed_fault_replay_tests.md

### Non-goals

- No websocket lifecycle changes.
- No reconnect implementation.
- No resubscribe implementation.
- No token resolver changes.
- No runtime file writing.
- No dashboard work.
- No strategy changes.
- No broker calls.
- No order creation.

## Grill Me Review

### Pushback

Feed contracts are incomplete unless replay tests prove faults actually suppress executable ranking and recovery restores ranking. Without this, the system may have many contracts but no end-to-end safety proof.

### Required proof

- Healthy feed allows executable ranking.
- Stale feed produces hold and zero executable ranking.
- Recovery clears hold.
- Websocket disconnect blocks ranking.
- Subscription failure blocks symbol-level feed.
- LIVE policy is stricter than PAPER for the same payload.

## Hermes Review

### Contract clarity

The tests compose existing production contracts: `feed_runtime_evidence`, `feed_health_truth`, `feed_hold_gate`, and `candidate_ranking`.

### Safety boundary

The PR is test-only plus docs. It does not import broker, websocket runtime, order, or dashboard modules.

## GSD Review

### Minimality

This PR corrects the roadmap gap with tests only. It does not modify production behavior.

### Determinism

Replay frames are deterministic in-memory payloads with no clock, network, broker, or file dependencies.

## QA / Safety Review

Tests assert:

- Healthy → stale → recovered transition behavior.
- Websocket disconnect → reconnect behavior.
- Subscription failure behavior.
- LIVE/PAPER policy split.
- Non-action evidence serialization.

## Scope Guard

Confirmed not touched:

- Feed lifecycle.
- Reconnect/resubscribe behavior.
- Token resolution.
- Runtime artifact writing.
- Strategy code.
- Dashboard UI.
- Broker/order execution paths.

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_pr_feed_20r_feed_fault_replay_tests.py tests/test_pr_feed_20_feed_runtime_evidence_bundle.py tests/test_pr_feed_16_feed_config_hardening.py tests/test_pr_feed_15_live_paper_feed_policy.py
```

Expected:

- feed fault replay tests pass.
- runtime evidence bundle tests remain green.
- feed config hardening tests remain green.
- feed policy tests remain green.

## Runtime Proof Required After Merge

Later runtime wiring and replay PRs must prove:

- Real runtime feed snapshots can be converted into the replay payload shape.
- Runtime evidence bundles are emitted for actual cycles.
- Live/paper mode used in replay matches configured runtime mode.
- No order action path treats replay evidence as permission to trade.

## What This PR Does Not Prove

- It does not prove real websocket recovery.
- It does not prove real token resubscription.
- It does not write runtime evidence artifacts.
- It does not prove strategy edge or profitability.

## Human Approval

Proceed only if CI is green and the PR remains limited to read-only feed fault replay tests.
