# Feed Reconnect Safety Logic Restore

mode: PAPER
candidate_id: PR_624_FEED_RECONNECT_SAFETY
decision: APPROVED
reason: Restoring critical feed reconnect state transition lost during a merge conflict.
timestamp: 2026-06-29T14:07:00Z
is_order_action: false
broker_api_called: false
source: Antigravity

## Agent Work Contract

source_agent: Antigravity
action: GENERATE_PATCH
title: Restore feed reconnect safety logic
scope: Restoring on_reconnect logic and test assertions.
requested_paths: core/kite_depth_ws.py, tests/test_feed_reconnect_safety.py
allowed_paths: core/kite_depth_ws.py, tests/test_feed_reconnect_safety.py, docs/agent_reviews/pr_624_feed_reconnect_safety.md
forbidden_paths: broker, order, execution, risk, strategy thresholds, credentials, environment files, live runtime outputs
expected_tests: test_feed_reconnect_safety.py
acceptance_proof: CI evidence gate has this document, tests pass.

## Scope Guard

In Scope:
- Restoring `_RUNTIME_STATE = "RUNNING"` on reconnect.
- Restoring `_resubscribe_full` on reconnect.
- Updating tests to expect this behavior.

Out of Scope:
- Any new features.
- Any other tests or broker logic.

## Grill Me Review

The main risk is that we blindly restore code without understanding it, but we did a full root cause analysis on the FATAL feed state loop and traced it back to this dropped code block during a bad Git merge. The change is safe.

## Hermes Review

No architectural changes. Just restoring dropped code that transitions `SUBSCRIBE_FAILED` back to `RUNNING` safely upon successful reconnection.

## GSD Review

Implemented:
- State transitions on websocket reconnect.
- Validation that missing logic caused feed stall.

## QA / Safety Review

Local validation:
Verified locally that all tests pass: `pytest -q tests/test_feed_reconnect_safety.py`
Verified that this prevents the reconnect loop.

## High-Risk Path Review

`core/kite_depth_ws.py` is high risk because it is feed management.
The change simply prevents the feed from staying in `SUBSCRIBE_FAILED` or `FATAL` indefinitely after a network blip, allowing normal recovery.

## Acceptance Proof

Acceptance criteria satisfied:
- CI passes.
- Code matches exactly what was previously approved before the merge conflict.

## Runtime Proof Required After Merge

Live deployment soak to ensure auto-reconnect transitions feed state back to RUNNING.

## What This PR Does Not Prove

This PR does not prove the actual external broker's stability, only that our internal state recovery is re-enabled.

## Human Approval

Approved by Ram.
