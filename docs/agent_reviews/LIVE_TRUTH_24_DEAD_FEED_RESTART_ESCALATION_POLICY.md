# Agent Review Evidence — LIVE-TRUTH-24 Dead-Feed Restart Escalation Policy

mode: REVIEW
candidate_id: live_truth_24_dead_feed_restart_escalation_policy
decision: dead_feed_restart_escalation_policy
reason: force_full_restart_on_hard_feed_dead_states
timestamp: 2026-05-29T00:00:00Z
source: docs/agent_reviews/LIVE_TRUTH_24_DEAD_FEED_RESTART_ESCALATION_POLICY.md
read_only: false
append: false
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false

## Agent Work Contract

source_agent: GSD
action: GENERATE_PATCH
title: LIVE-TRUTH-24 — Dead-Feed Restart Escalation Policy
scope: Escalate hard feed-dead detections to a forced full restart that ignores only the cooldown (not storm/hourly/breaker/auth gates).
requested_paths:
  - core/kite_depth_ws.py
  - tests/test_kite_depth_restart.py
  - docs/agent_reviews/LIVE_TRUTH_24_DEAD_FEED_RESTART_ESCALATION_POLICY.md
allowed_paths:
  - core/kite_depth_ws.py
  - tests/test_kite_depth_restart.py
  - docs/agent_reviews/LIVE_TRUTH_24_DEAD_FEED_RESTART_ESCALATION_POLICY.md
forbidden_paths:
  - .env
  - "*.env"
  - credentials.py
  - main.py
  - run_live.sh
  - config/
  - core/broker*
  - core/order*
  - core/execution*
  - core/risk*
  - strategies/
expected_tests:
  - python -m py_compile core/kite_depth_ws.py
  - PYTHONPATH=. python -m pytest -q tests/test_kite_depth_restart.py
  - PYTHONPATH=. python -m pytest -q tests/test_kite_depth_ws_stability.py
acceptance_proof: Hard feed-dead reasons attempt restart with ignore_cooldown=True and force_full_restart=True; storm/hourly/breaker/auth gates still block; storm trip triggers breaker + risk halt.

## High-Risk Path Review

This PR changes `core/kite_depth_ws.py` (feed/WebSocket watchdog + restart paths), which is high-risk for LIVE safety.

Risk controls preserved:
- Auth latch remains fail-closed: `_AUTH_REQUIRED_LATCH` blocks all restarts.
- Breaker + guard remain authoritative: `feed_breaker_tripped()` and `feed_restart_guard.allow_restart(...)` still gate restarts.
- Restart storm + hourly rate limits are unchanged and still block: `FEED_RESTART_STORM_TRIP` and `FEED_MAX_FULL_RESTARTS_PER_HOUR` are still enforced.
- Risk halt remains: restart storm trip calls `core.risk_halt.set_halt("feed_restart_storm", ...)` and trips the feed breaker.

## Grill Me Review

Hard feed-dead states during market open (no ticks, stale depth, missing option subscriptions) are operationally equivalent to a dead bot. Waiting behind normal cooldown increases the time spent trading blind.

Pushback addressed:
- Escalation ignores only the cooldown gate. It does not bypass breaker/guard/hourly/storm limits.
- Forced full restart is bounded by existing storm/hourly controls and becomes fail-closed when storm trip occurs.

## Hermes Review

Design principle: split “restart eligibility” (breaker/guard/hourly/storm/auth) from “restart urgency” (cooldown). For hard feed-dead reasons, urgency must override cooldown, but eligibility must remain unchanged.

Hard feed-dead reasons covered:
- `tick_stalled` (DB ticks stale beyond threshold)
- `no_ticks_age=*` (no WebSocket ticks beyond threshold)
- `depth_stale_age=*` (depth store stale beyond threshold)
- `market_open_option_subscriptions_missing`
- `stale_option_freshness_drift_failed:*`

## GSD Review

Implementation is narrowly scoped:
- Adds escalation flags at existing watchdog restart call sites.
- Fixes restart storm risk halt call to use the existing `core.risk_halt.set_halt(...)` API.
- Adds deterministic tests proving cooldown bypass + forced full restart + storm/auth gating.

## QA / Safety Review

Tests prove:
- Hard feed-dead restarts ignore cooldown and force full restart (soft path is not used).
- Depth-stale and no-tick reasons both attempt the forced full restart.
- Option-subscription-missing reason forces full restart (and refuses soft path).
- Repeated hard restarts trip storm breaker and trigger both breaker + risk halt.
- Auth latch blocks a hard restart attempt and does not stop/start the feed.

## Scope Guard

Confirmed not touched:
- Candidate ranking/scoring logic.
- Broker adapters, order placement, or execution wiring.
- Strategy thresholds or strategy modules.
- Credentials and environment files.
- UI/dashboard code.

## Acceptance Proof

Run:

```bash
python -m py_compile core/kite_depth_ws.py
PYTHONPATH=. python -m pytest -q tests/test_kite_depth_restart.py
PYTHONPATH=. python -m pytest -q tests/test_kite_depth_ws_stability.py
```

Expected:
- Hard feed-dead reasons attempt forced full restart even during cooldown.
- Restart storm protection remains intact and halts on storm trip.
- Auth latch remains fail-closed.

## Runtime Proof Required After Merge

In a controlled PAPER run during market open (no orders):
- Induce a no-tick condition (pause WS messages) and confirm watchdog emits `FEED_NO_TICKS_DETECTED` and a forced full restart is attempted (`FEED_RESTART_FORCE_FULL_PATH`).
- Induce a depth-stale condition and confirm watchdog attempts forced full restart.
- Simulate missing option subscriptions during market open and confirm forced full restart attempt.
- Confirm storm trip produces `FEED_RESTART_STORM_TRIP` and a risk halt file write.

## What This PR Does Not Prove

- It does not prove a restart will always restore the feed (broker-side outages can persist).
- It does not prove end-to-end LIVE readiness.
- It does not change strategy behavior or ranking quality.

## Human Approval

Approve only if:
- CI is fully green.
- The diff remains limited to the declared allowed paths.
- Restart storm protection and auth latch behavior remain fail-closed.

