# PR-FEED-08 Pure Tick Utility Helpers Agent Review

mode: REVIEW
candidate_id: pr_feed_08_pure_tick_utility_helpers
decision: review_ready
reason: pure_tick_utility_helpers_tests_docs
timestamp: 2026-05-27T17:45:00Z
source: pr_feed_08_agent_review
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

This review covers PR-FEED-08 only.

The PR adds pure, deterministic tick utility helpers for feed ingestion. It must not wire live websocket runtime behavior, change reconnect policy, change subscription budget policy, execute trades, place or modify orders, call broker APIs, or change dashboard/UI surfaces.

## Scope Guard

Allowed:

- Add pure tick parsing and freshness helper functions.
- Add focused unit tests.
- Add documentation and agent-review evidence.
- Shrink `docs/EDGE_TODO.md` for the completed PR.

Not allowed:

- Broker calls.
- Order actions.
- Runtime wiring.
- Dashboard/UI work.
- Reconnect policy changes.
- Subscription-budget changes.
- Live websocket callback rewiring.
- Filesystem writes from the helper module.

## Grill Me Review

Question: Can this PR place, modify, cancel, or route an order?

Answer: No. The changed helper module has no broker imports, no execution imports, and no order-facing functions.

Question: Can this PR change live websocket behavior?

Answer: No. `core/kite_depth_ws.py` is not rewired in this PR. The helper surface is created first for deterministic testing.

Question: Can this PR hide stale tick timestamps behind wall-clock calls?

Answer: No. `normalized_tick_epoch(...)` receives `receipt_epoch`, previous epoch values, market-open state, and policy flags as explicit inputs. It does not call time APIs.

Question: Can invalid numeric values crash the helper path?

Answer: No. Invalid epoch and price values fail closed to `None` or deterministic fallback output.

## Hermes Review

The public helper contract is intentionally narrow:

- `coerce_epoch(...)`
- `safe_float(...)`
- `tick_epoch(...)`
- `best_price(...)`
- `depth_has_bid_ask(...)`
- `initial_freshness_epoch(...)`
- `normalized_tick_epoch(...)`

These helpers are pure value transforms. Callers must pass policy and runtime inputs explicitly.

## GSD Review

The implementation stays deterministic and local:

- No hidden global state.
- No network calls.
- No broker imports.
- No filesystem writes.
- No logging side effects.
- No runtime mutation.
- Invalid inputs fail closed.

## QA / Safety Review

Focused test coverage includes:

- second and millisecond epoch normalization
- datetime timestamp extraction
- Kite timestamp precedence
- missing timestamp fallback
- safe float coercion
- missing and invalid depth book handling
- positive bid/ask depth validation
- option receipt-time freshness policy
- underlying payload-time freshness policy
- payload-lag replacement during market-open policy
- monotonic previous-epoch clamp
- invalid receipt epoch deterministic fallback

## Acceptance Proof

Run:

```bash
pytest tests/test_pr_feed_08_tick_utils.py
```

CI must pass before merge.

## Runtime Proof Required After Merge

A later PR may wire these helpers into `core/kite_depth_ws.py` only if explicitly scoped. That later PR must prove:

- websocket behavior remains backward-compatible
- feed freshness decisions remain monotonic
- stale/invalid payload data still fails closed
- no broker/order side effects are introduced
- existing feed runtime evidence contracts remain compatible

## What This PR Does Not Prove

This PR does not prove live feed recovery, reconnect behavior, subscription budget behavior, runtime snapshot correctness, broker safety, execution quality, or profitability. It only proves a deterministic helper surface for future feed callback refactors.

## Human Approval

Ready for maintainer review after CI is green.

## Next Action

After this PR is merged, continue with `PR-FEED-09 — Extract Reconnect Decision Policy` only from the latest merged main commit.


## High-Risk Path Review

N/A
