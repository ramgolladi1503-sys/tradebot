# Agent Review Evidence — FEED-STAB-02 Feed Supervisor State Machine

## Agent Work Contract

### Goal

Add a read-only FeedSupervisor state machine that consumes existing feed, recovery, subscription, and freshness evidence and produces deterministic feed-readiness snapshots without selecting strategies or creating order intent.

### Files changed

- `core/feed_supervisor.py`
- `tests/test_feed_supervisor_state_machine.py`
- `docs/agent_reviews/feed-stab-02-feed-supervisor-state-machine.md`

### Evidence Contract Fields

mode: REVIEW
candidate_id: FEED_STAB_02_FEED_SUPERVISOR_STATE_MACHINE
decision: INTRODUCE_FEED_SUPERVISOR_STATE_MACHINE
reason: FeedSupervisor now classifies feed readiness into explicit read-only states without broker calls, order intent, or runtime mutation.
timestamp: 2026-06-09T00:00:00+05:30
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/feed-stab-02-feed-supervisor-state-machine.md

### Non-goals

- No strategy selection.
- No ranking/scoring changes.
- No broker calls.
- No order creation.
- No dashboard wiring.
- No runtime feed routing changes.

## Grill Me Review

### Pushback

A feed supervisor can become fake safety if it silently marks readiness without fresh evidence. This PR keeps the classifier fail-closed: incomplete or stale evidence stays out of `CANDIDATE_READY`.

### Required proof

- Feed states classify deterministically.
- Readiness requires verified subscription and freshness evidence.
- Recovery, timeout, restart-required, auth-required, and shutdown paths remain explicit.
- Non-action fields remain explicit.

## Hermes Review

### Contract clarity

`FeedSupervisorSnapshot` is a read-only evidence contract. It carries state, blockers, recovery status, freshness flags, and sanitized symbol sets.

### Safety boundary

The snapshot emits `is_order_action=false`, `broker_api_called=false`, `live_order_action=false`, `broker_order_action=false`, and `allowed_for_live_execution=false`. It does not import broker, order, strategy, scoring, or dashboard modules.

## GSD Review

### Minimality

The PR adds only the supervisor seam and its focused tests. It does not wire runtime routing, strategy selection, or broker behavior.

### Determinism

Classification is deterministic over supplied payload fields. No network, broker, or time dependency is required.

## QA / Safety Review

Tests assert:

- booting and connecting states;
- connected, subscribing, and verifying transitions;
- candidate-ready promotion from verified fresh evidence;
- warming-up behavior before readiness;
- recovery-blocked, restart-required, auth-required, and shutdown states;
- snapshot payload serialization and non-action flags.

## Scope Guard

Confirmed not touched:

- `strategies/`
- `core/order*`
- `core/broker*`
- `dashboard/`
- `credentials.py`
- `.env`

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_feed_supervisor_state_machine.py -q
PYTHONPATH=. python -m pytest tests/test_feed_recovery_coordinator.py tests/test_feed_runtime_state_machine.py tests/test_kite_depth_ws_stability.py -q
git diff --check
python scripts/validate_agent_review_evidence.py --base-ref origin/main
PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/feed_stab_02_changed_paths.txt
```

Expected:

- FeedSupervisor state-machine tests pass.
- Adjacent feed/recovery tests pass.
- Snapshot payload remains read-only and non-order-action.

## Runtime Proof Required After Merge

Runtime wiring remains unchanged in this PR.

## What This PR Does Not Prove

- Feed quality.
- Trading edge.
- Order safety beyond the snapshot contract.
- Runtime wiring.

## Human Approval

Proceed only if CI is green and the PR remains limited to the read-only FeedSupervisor state machine.


## High-Risk Path Review

N/A
