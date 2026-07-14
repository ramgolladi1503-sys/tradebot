# PR-FEED-10 Subscription Budget Policy Agent Review

mode: REVIEW
candidate_id: pr_feed_10_subscription_budget_policy
decision: review_ready
reason: subscription_budget_policy_tests_docs
timestamp: 2026-05-27T18:22:00Z
source: pr_feed_10_agent_review
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

This review covers PR-FEED-10 only.

The PR adds pure, deterministic subscription budget policy helpers for feed token selection. It must not wire live websocket runtime behavior, execute trades, place or modify orders, call broker APIs, or change dashboard/UI surfaces.

## Scope Guard

Allowed:

- Add pure subscription budget helper functions.
- Add focused unit tests.
- Add documentation and agent-review evidence.
- Shrink `docs/EDGE_TODO.md` for the completed PR.

Not allowed:

- Broker calls.
- Order actions.
- Runtime wiring.
- Dashboard/UI work.
- Reconnect policy changes.
- Live websocket subscription callback rewiring.
- Filesystem writes from the helper module.
- Hidden config or time calls inside the helper module.

## Grill Me Review

Question: Can this PR place, modify, cancel, or route an order?

Answer: No. The changed helper module has no broker imports, no execution imports, and no order-facing functions.

Question: Can this PR change live websocket subscription behavior?

Answer: No. `core/kite_depth_ws.py` is not rewired in this PR. The helper surface is created first for deterministic testing.

Question: Can preserved trade/underlying tokens be accidentally dropped when the budget is exceeded?

Answer: No. Preserved tokens are always kept. If preserved tokens exceed the budget, the decision marks `preserve_exceeded=true` and drops only non-preserved candidates.

Question: Can invalid token input crash the policy path?

Answer: No. Token normalization filters invalid, zero, negative, duplicate, and non-integer values deterministically.

## Hermes Review

The public helper contract is intentionally narrow:

- `normalize_positive_tokens(...)`
- `normalize_token_set(...)`
- `merge_preserve_tokens(...)`
- `normalize_rank_tuple(...)`
- `rank_key_for_token(...)`
- `enforce_subscription_budget(...)`
- `SubscriptionBudgetDecision.to_payload()`

These helpers are pure value transforms. Callers must pass budget, desired tokens, rank evidence, and preserve-token groups explicitly.

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

- token normalization order preservation
- invalid token filtering
- preserve-token union across underlying/sticky/active groups
- rank tuple normalization
- default rank fallback
- disabled budget behavior
- under-budget no-op behavior
- preserved-token retention
- best-ranked candidate retention
- dropped-token evidence
- preserved-token overflow handling
- unknown candidate rank ordering

## Acceptance Proof

Run:

```bash
pytest tests/test_pr_feed_10_subscription_budget_policy.py
```

CI must pass before merge.

## Runtime Proof Required After Merge

A later PR may wire these helpers into `core/kite_depth_ws.py` only if explicitly scoped. That later PR must prove:

- budget behavior remains backward-compatible
- underlying tokens remain preserved
- sticky/active trade tokens remain preserved
- candidate rank ordering remains deterministic
- no broker/order side effects are introduced
- existing feed subscription evidence remains compatible

## What This PR Does Not Prove

This PR does not prove live subscription correctness, broker connectivity, websocket recovery, runtime snapshot correctness, execution quality, or profitability. It only proves a deterministic subscription budget decision surface for future feed callback refactors.

## Human Approval

Ready for maintainer review after CI is green.

## Next Action

After this PR is merged, continue with `PR-FEED-11 — Extract Runtime Snapshot Builder` only from the latest merged main commit.


## High-Risk Path Review

N/A

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false
