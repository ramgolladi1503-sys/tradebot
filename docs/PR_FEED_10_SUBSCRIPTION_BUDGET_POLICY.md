# PR-FEED-10 — Extract Subscription Budget Policy

## Scope

This PR adds a pure subscription budget policy module for feed token selection.

The module centralizes deterministic budget decisions for:

- positive token normalization
- preserve-token merging
- option-rank normalization
- candidate rank ordering
- max-token budget enforcement
- preserved-token overflow handling
- dropped/kept evidence payloads

## Files

- `core/feed/subscription_budget_policy.py`
- `tests/test_pr_feed_10_subscription_budget_policy.py`

## Design

The helper module is deliberately pure:

- no broker client imports
- no websocket object access
- no config access
- no filesystem writes
- no logging
- no runtime state mutation
- no order or execution behavior

Callers pass desired tokens, budget, option rank evidence, and preserve-token groups explicitly.

## Safety

This PR does not rewire `core/kite_depth_ws.py`.

That is intentional. The existing websocket file contains sensitive runtime subscription behavior. This PR creates the deterministic budget decision surface first so future feed-refactor PRs can consume it through a controlled diff with regression coverage.

## Test command

```bash
python -m pytest tests/test_pr_feed_10_subscription_budget_policy.py -q
```

## Out of scope

- No broker calls
- No order behavior
- No runtime wiring
- No dashboard/UI work
- No live websocket subscription behavior change
- No reconnect-policy changes
- No feed runtime snapshot changes
