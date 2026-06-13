# AG Live Feed Stability Experiment Fixes (2026-06-10)

mode: LIVE
candidate_id: ag-live-feed-stability-experiment-fixes-20260610
decision: fail_closed_on_fatal_feed_state
reason: Hardens fail-closed behavior on Kite WebSocket lifecycle fatal feed state.
timestamp: 2026-06-10T20:30:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/ag-live-feed-stability-experiment-fixes-20260610.md

## Agent Work Contract
The agent must fix the current red CI on PR #544 with the smallest safe changes. Do not expand the PR scope. Keep trading safety parameters strict and fail closed.

## Scope Guard
In scope:
- Hardening fail-closed behavior in Phase2 adapter and symbol execution safety when feed is unhealthy or stale.
- Safely handling Twisted reactor lifecycle fatal states to prevent CPU spin/infinite restarts.
- Resolving CI unit test failures and lint/format issues on branch `ag/live-feed-stability-experiment-20260610`.

Out of scope:
- Auto-trading enabling or live orders.
- Changing strategy signals or ranking/scoring models.
- Changing live credentials or connecting to live broker APIs.

## High-Risk Path Review
High-risk changes are limited to:
- [core/kite_depth_ws.py](file:///Users/madhuram/tradebot/core/kite_depth_ws.py): Prevents Twisted reactor reconnect loops by checking startup state, marks state as `FEED_LIFECYCLE_FATAL` on terminal errors.
- [core/orchestrator.py](file:///Users/madhuram/tradebot/core/orchestrator.py): CPU spin protection in orchestrator monitoring loop when feed enters a terminal/fatal state.
These changes have been thoroughly reviewed for safety. Order placement and risk thresholds are untouched.

## Grill Me Review
Risk checked: No broker APIs are called, no orders are placed or modified. The system is designed to fail closed (`feed_ok=False` blocks Phase2 execution candidates).

## Hermes Review
Architectural changes preserve the feed-to-execution contract. Feed state and freshness metrics (LTP, depth, option tick ages) remain machine-readable and fail-closed.

## GSD Review
Small scoped fixes applied to tests to align the test payloads and environment isolation with the new strict feed truth validators.

## QA / Safety Review
Unit tests updated to supply required feed age/subscription fields. A new `setup_feed_ok_for_phase2` autouse fixture isolates the Phase2 adapter tests to run with a simulated healthy feed truth.

## Acceptance Proof
Run pytest on the test suite:
```bash
PYTHONPATH=. pytest
```
Verify that `validate_agent_review_evidence.py` passes:
```bash
python scripts/validate_agent_review_evidence.py --base-ref origin/main
```

## Runtime Proof Required After Merge
Inspect `logs/feed_runtime_latest.json` or `.runtime/feed_runtime_latest.json` after running the feed to verify `feed_ok` state propagation:
```bash
cat logs/feed_runtime_latest.json | jq '{feed_ok, reasons}'
```

## What This PR Does Not Prove
This PR does not prove long-term feed recovery stability over multiple market hours, nor does it prove live trading profitability. It only hardens the fail-closed lifecycle handling on fatal feed events.

## Human Approval
Requires explicit human review of PR #544 before merging.
