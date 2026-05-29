# Agent Review Evidence — LIVE-TRUTH-26 Runtime Feed Truth State Machine

## Agent Work Contract

### Goal

Create one canonical runtime feed truth state so downstream candidate generation and ranking do not trust process-alive or `_KITE_TICKER is not None` signals.

### Files changed

- `core/feed_truth_state.py`
- `core/kite_depth_ws.py`
- `core/review_queue.py`
- `tests/test_feed_runtime_states.py`
- `docs/agent_reviews/live_truth_26_runtime_feed_truth_state_machine.md`

### Evidence Contract Fields

mode: LIVE
candidate_id: LIVE_TRUTH_26_RUNTIME_FEED_TRUTH_STATE_MACHINE
message_decision: RUNTIME_FEED_TRUTH_STATE_CANONICALIZATION
decision: RUNTIME_FEED_TRUTH_STATE_CANONICALIZATION
reason: Feed runtime snapshots now include a canonical `feed_truth_state` derived from runtime feed facts (market state, ws connectivity, tick ages, option subscription/tick/blocker status, and restart verification), not from ticker-object presence.
timestamp: 2026-05-29T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/live_truth_26_runtime_feed_truth_state_machine.md

### Non-goals

- No broker calls.
- No order behavior changes.
- No ranking weight changes.
- No dashboard/UI changes.
- No removal of existing runtime snapshot detail fields.

## Grill Me Review

### Pushback

If any code path still treats “ticker exists” or “process alive” as feed health, LIVE candidates can be misclassified as safe during a dead feed incident.

### Required proof

- Market open + `_KITE_TICKER` exists but `last_tick_age_sec` is missing => `feed_truth_state` is not `LIVE`.
- Market open + stale/missing ticks => `feed_truth_state=DEAD`.
- Market open + connected + fresh option tick + blockers OK => `feed_truth_state=LIVE`.
- Partial coverage with fresh ticks => `feed_truth_state=DEGRADED`.

## Hermes Review

### Contract clarity

`core/feed_truth_state.py` is a pure classifier that returns a canonical state plus reasons. It is read-only and must not be used as evidence of broker or order activity.

### Safety boundary

The classifier consumes only runtime snapshot facts already present in `feed_runtime_latest.json` and restart verification overlays. It does not reconnect, resubscribe, place orders, or call external APIs.

## GSD Review

### Minimality

The change is limited to:

- Adding the canonical classifier (`core/feed_truth_state.py`).
- Writing `feed_truth_state` fields into the existing feed runtime snapshot writer (`core/kite_depth_ws.py`).
- Exposing the new fields in review queue status snapshot (`core/review_queue.py`) without changing scoring or ranking.

### Determinism

Classification is deterministic over the supplied payload and configured SLA thresholds.

## QA / Safety Review

Tests assert:

- Ticker object / ws_connected truth without tick evidence does not produce `LIVE`.
- Stale tick / blocked option feed yields `DEAD`.
- Fresh tick + option tick + blockers OK yields `LIVE`.
- Missing option token coverage yields `DEGRADED` (not executable strict LIVE).

## High-Risk Path Review

High-risk module touched: `core/kite_depth_ws.py`.

Safety review notes:

- Only adds additional derived snapshot fields: `feed_truth_state`, `feed_truth_reason_code`, `feed_truth_reasons`, `feed_truth_strict_live`.
- Does not change websocket connect/restart behavior, token resolver behavior, or any broker/execution paths.
- Fails closed: `LIVE` requires explicit tick-age evidence and healthy option feed truth; absence of tick evidence yields `STARTING`/non-LIVE.

## Scope Guard

Confirmed not touched:

- Ranking/scoring weights.
- Candidate execution/order placement logic.
- Broker adapters.
- UI/dashboard code.
- Token resolution contracts.

## Acceptance Proof

Run:

```bash
python -m py_compile core/kite_depth_ws.py core/feed_truth_state.py core/review_queue.py
PYTHONPATH=. python -m pytest -q tests/test_feed_runtime_states.py
PYTHONPATH=. python -m pytest -q tests/test_feed_debug.py
```

Expected:

- New canonical truth state fields are present in runtime snapshot JSON.
- Canonical state is not `LIVE` without tick proof.
- Existing feed runtime snapshot tests remain green.

## Runtime Proof Required After Merge

During a live observation window, capture:

- `logs/feed_runtime_latest.json` includes `feed_truth_state` and `feed_truth_strict_live`.
- When feed ticks stall during market open, `feed_truth_state` transitions to `DEAD` (strict live false).
- When feed recovers with verified option ticks and blockers OK, `feed_truth_state` transitions to `LIVE` (strict live true).

## What This PR Does Not Prove

- It does not prove broker connectivity or order placement safety (explicitly out of scope).
- It does not prove profitability or strategy signal quality.
- It does not by itself guarantee all downstream gates consume the new state everywhere (future wiring may still be required).

## Human Approval

Merge only after:

- CI is green.
- Review confirms no widening of LIVE eligibility (strict live requires tick evidence).
