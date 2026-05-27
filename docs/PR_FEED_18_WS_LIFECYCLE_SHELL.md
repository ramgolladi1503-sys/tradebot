# PR-FEED-18 — Extract WebSocket Lifecycle Shell

## Scope

This PR adds a pure websocket lifecycle shell module for feed handling.

The module centralizes deterministic lifecycle decisions for:

- lifecycle phase normalization
- runtime phase derivation from explicit observations
- connect-request decisions
- connected-state marking decisions
- subscribe-request decisions
- subscribed-state marking decisions
- disconnect decisions
- error decisions
- stop-request decisions
- transition application to a read-only state object
- lifecycle evidence payload construction

## Files

- `core/feed/ws_lifecycle_shell.py`
- `tests/test_pr_feed_18_ws_lifecycle_shell.py`

## Design

The helper module is deliberately pure:

- no broker client imports
- no websocket object access
- no config access
- no filesystem writes
- no logging
- no runtime state mutation outside returned dataclasses
- no order or execution behavior

Callers pass policy and runtime observations explicitly, including market-open state, stop flags, auth state, connection state, requested identifier lists, and restart/soft-refresh intent.

## Safety

This PR does not rewire `core/kite_depth_ws.py`.

That is intentional. The existing websocket file contains sensitive callback behavior. This PR creates the deterministic lifecycle shell first so future feed-refactor PRs can consume it through a controlled diff with regression coverage.

## Test command

```bash
python -m pytest tests/test_pr_feed_18_ws_lifecycle_shell.py -q
```

## Out of scope

- No broker calls
- No order behavior
- No runtime wiring
- No dashboard/UI work
- No websocket callback behavior change
- No reconnect policy change
- No subscription behavior change
- No runtime snapshot changes
