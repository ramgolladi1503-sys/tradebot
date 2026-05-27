# PR-FEED-09 — Extract Reconnect Decision Policy

## Scope

This PR adds a pure reconnect decision policy module for feed websocket handling.

The module centralizes deterministic reconnect decisions for:

- websocket fault classification
- restart-cooldown bypass classification
- soft resubscribe eligibility
- watchdog stale-tick restart thresholds
- websocket error reconnect decisions
- websocket close reconnect decisions

## Files

- `core/feed/reconnect_policy.py`
- `tests/test_pr_feed_09_reconnect_policy.py`

## Design

The helper module is deliberately pure:

- no broker client imports
- no websocket object access
- no config access
- no filesystem writes
- no logging
- no runtime state mutation
- no order or execution behavior

Callers pass policy inputs explicitly, including market-open state, stop flags, reconnect mode, stale strike counts, tick ages, websocket codes, and reason text.

## Safety

This PR does not rewire `core/kite_depth_ws.py`.

That is intentional. The existing websocket file contains sensitive runtime callback behavior. This PR creates the deterministic decision surface first so future feed refactor PRs can consume it through a controlled diff with regression coverage.

## Test command

```bash
python -m pytest tests/test_pr_feed_09_reconnect_policy.py -q
```

## Out of scope

- No broker calls
- No order behavior
- No runtime wiring
- No dashboard/UI work
- No live websocket callback behavior change
- No subscription-budget changes
- No feed runtime snapshot changes
