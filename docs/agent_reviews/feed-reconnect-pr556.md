---
mode: agent_assisted
candidate_id: feed-reconnect-pr556
agent: gsd
date: 2026-06-11
---

# Agent Review Evidence: Feed Rewiring and Reconnect Logic (PR #556)

## Scope
This PR moves the `DEPTH_WS_ALLOW_SOFT_RECONNECTS` and `KiteTicker` internal auto-reconnect logic out of PR #555 to keep it strictly focused on feed process lifecycle.

## What changed?
1. `config/config.py`: Enforced `DEPTH_WS_USE_SUBPROCESS = True` and set `DEPTH_WS_ALLOW_SOFT_RECONNECTS = False`.
2. `core/auth.py`: Disabled `KiteTicker` internal auto-reconnect (`reconnect=False`).
3. `core/kite_depth_ws.py`: Bypassed soft resubscribe logic when `DEPTH_WS_ALLOW_SOFT_RECONNECTS` is False, enforcing subprocess restart.

## Why does this move safety/stability/readiness forward?
These changes directly prevent the `ReactorNotRestartable` crash when the websocket disconnects mid-session. By turning off Twisted's internal reconnects and Kite's auto-reconnects, we rely purely on the orchestrator tearing down the subprocess and spinning up a fresh one. This eliminates dirty Twisted reactor state.

## What did not change?
- `feed_ok=True` is still accurately reported based on data freshness.
- No risk gates were weakened.
- No strategy thresholds were changed.
- No order placement logic was altered (`read_only=true`, `is_order_action=false`, `broker_api_called=false`).

## What tests prove it?
- `tests/test_kite_depth_restart.py`
- `tests/test_kite_auth_consistency.py`

## What could still fail?
- Extended network outages might exhaust the maximum allowed reconnects per hour.
