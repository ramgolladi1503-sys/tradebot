# Agent Review Evidence — PR-FEED-15 Live/Paper Feed Policy Separation

## Agent Work Contract

### Goal

Add an explicit read-only feed policy contract that separates LIVE, PAPER, and SIM feed-health thresholds.

### Files changed

- `core/feed_policy.py`
- `tests/test_pr_feed_15_live_paper_feed_policy.py`
- `docs/PR_FEED_15_LIVE_PAPER_FEED_POLICY_SEPARATION.md`
- `docs/agent_reviews/pr_feed_15_live_paper_feed_policy_separation.md`

### Evidence Contract Fields

mode: PAPER
candidate_id: PR_FEED_15_LIVE_PAPER_FEED_POLICY_SEPARATION
message_decision: READ_ONLY_LIVE_PAPER_FEED_POLICY_SEPARATION
decision: READ_ONLY_LIVE_PAPER_FEED_POLICY_SEPARATION
reason: Feed policy now chooses explicit LIVE, PAPER, and SIM thresholds instead of sharing one implicit tolerance.
timestamp: 2026-05-25T09:50:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr_feed_15_live_paper_feed_policy_separation.md

### Non-goals

- No websocket lifecycle changes.
- No reconnect logic.
- No resubscribe logic.
- No token resolver changes.
- No ranking changes.
- No strategy changes.
- No dashboard UI changes.
- No broker calls.
- No order creation.

## Grill Me Review

### Pushback

One feed threshold across LIVE/PAPER/SIM creates fake confidence. LIVE should not inherit looser observation thresholds, and PAPER should not silently become LIVE-equivalent.

### Required proof

- Same payload can fail LIVE while passing PAPER.
- PAPER still blocks clearly stale feed.
- Invalid mode fails closed.
- SIM is explicitly observation-tolerant.

## Hermes Review

### Contract clarity

The policy module is read-only and delegates to canonical `classify_feed_health_truth(...)`. It does not change feed transport or runtime behavior.

### Safety boundary

The decision emits `is_order_action=false` and does not import broker or websocket runtime modules.

## GSD Review

### Minimality

The PR adds a new policy seam instead of rewriting feed health truth or runtime wiring. Existing callers remain backward-compatible.

### Determinism

Policy thresholds are constants by normalized mode alias.

## QA / Safety Review

Tests assert:

- LIVE is stricter than PAPER for the same feed-age payload.
- PAPER blocks clearly stale feed.
- Invalid mode returns a blocked non-action decision.
- LIVE requires explicit websocket truth.
- SIM allows observation without websocket requirement.
- JSON payload includes non-action evidence.

## Scope Guard

Confirmed not touched:

- Feed lifecycle.
- Reconnect/resubscribe behavior.
- Token resolution.
- Strategy code.
- Ranking code.
- Dashboard UI.
- Broker/order execution paths.

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_pr_feed_15_live_paper_feed_policy.py
```

Expected:

- feed policy tests pass.
- policy evidence remains read-only and non-action.
- invalid mode fails closed.

## Runtime Proof Required After Merge

Later runtime wiring must prove:

- LIVE uses `LIVE_STRICT`.
- PAPER uses `PAPER_OBSERVATION`.
- SIM/BACKTEST uses `SIM_OBSERVATION`.
- Unknown mode cannot silently fall back.

## What This PR Does Not Prove

- It does not prove websocket recovery.
- It does not prove token freshness.
- It does not wire runtime callers yet.
- It does not prove strategy edge or profitability.

## Human Approval

Proceed only if CI is green and the PR remains limited to read-only feed policy separation.


## High-Risk Path Review

N/A
