# PR-FEED-08 — Extract Pure Tick Utility Helpers

## Scope

This PR adds a small pure helper module for tick parsing, price extraction, depth-shape validation, and tick freshness timestamp normalization.

## Files

- `core/feed/tick_utils.py`
- `tests/test_pr_feed_08_tick_utils.py`

## Design

The helper module is deliberately pure:

- no broker client imports
- no config access
- no filesystem writes
- no logging
- no runtime state mutation
- no order or execution behavior

Callers pass policy inputs explicitly, including market-open state, payload-lag threshold, option receipt-time policy, and previous epoch values.

## Safety

This PR does not change live websocket wiring. The extraction target is isolated first so behavior can be covered by deterministic tests before future callback refactors consume it.

## Test command

```bash
python -m pytest tests/test_pr_feed_08_tick_utils.py -q
```

## Out of scope

- No broker calls
- No order behavior
- No runtime wiring
- No dashboard/UI work
- No reconnect policy changes
- No subscription-budget changes
