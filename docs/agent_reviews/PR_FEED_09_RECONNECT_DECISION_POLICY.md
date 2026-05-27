# PR-FEED-09 Reconnect Decision Policy Agent Review

mode: REVIEW
candidate_id: pr_feed_09_reconnect_decision_policy
decision: review_ready
reason: reconnect_decision_policy_tests_docs
timestamp: 2026-05-27T18:05:00Z
source: pr_feed_09_agent_review
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

This review covers PR-FEED-09 only.

The PR adds pure, deterministic reconnect decision helpers for feed websocket handling. It must not wire live websocket runtime behavior, change subscription budget policy, execute trades, place or modify orders, call broker APIs, or change dashboard/UI surfaces.

## Scope Guard

Allowed:

- Add pure reconnect decision helper functions.
- Add focused unit tests.
- Add documentation and agent-review evidence.
- Shrink `docs/EDGE_TODO.md` for the completed PR.

Not allowed:

- Broker calls.
- Order actions.
- Runtime wiring.
- Dashboard/UI work.
- Subscription-budget changes.
- Live websocket callback rewiring.
- Filesystem writes from the helper module.
- Hidden time calls inside the helper module.

## Grill Me Review

Question: Can this PR place, modify, cancel, or route an order?

Answer: No. The changed helper module has no broker imports, no execution imports, and no order-facing functions.

Question: Can this PR change live websocket behavior?

Answer: No. `core/kite_depth_ws.py` is not rewired in this PR. The helper surface is created first for deterministic testing.

Question: Can this PR hide reconnect timing behind wall-clock calls?

Answer: No. The helpers receive `now_epoch`, tick ages, market-open state, stop flags, and policy thresholds as explicit inputs. They do not call time APIs.

Question: Can auth failures accidentally restart the feed?

Answer: No. Auth-error decisions emit `AUTH_BLOCKED` and suppress restart.

Question: Can stop-requested close/error paths accidentally restart the feed?

Answer: No. Stop-requested and watchdog-stop states return non-restart decisions.

## Hermes Review

The public helper contract is intentionally narrow:

- `normalize_ws_code(...)`
- `is_fatal_ws_fault(...)`
- `is_opening_handshake_error(...)`
- `should_ignore_restart_cooldown_for_ws_fault(...)`
- `evaluate_soft_resubscribe_policy(...)`
- `evaluate_watchdog_stale_tick_policy(...)`
- `evaluate_ws_error_reconnect_policy(...)`
- `evaluate_ws_close_reconnect_policy(...)`
- `ReconnectDecision.to_payload()`

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

- websocket code normalization
- fatal websocket code classification
- reason-text fatal close classification
- opening-handshake classification
- restart-cooldown bypass classification
- soft resubscribe hard marker blocking
- disconnected websocket soft-resubscribe blocking
- missing/stale/fresh tick soft-resubscribe outcomes
- watchdog market-closed reset
- watchdog fresh websocket recovery reset
- watchdog stale-strike increment
- watchdog restart threshold decision
- auth-error restart suppression
- first handshake soft reset
- repeated handshake restart suppression
- stop-requested restart suppression
- internal fatal websocket full-restart scheduling
- external fatal websocket restart decision
- close-path auth/stop suppression
- close-path soft resubscribe vs full restart

## Acceptance Proof

Run:

```bash
pytest tests/test_pr_feed_09_reconnect_policy.py
```

CI must pass before merge.

## Runtime Proof Required After Merge

A later PR may wire these helpers into `core/kite_depth_ws.py` only if explicitly scoped. That later PR must prove:

- reconnect behavior remains backward-compatible
- auth errors remain fail-closed and do not restart
- stop-requested paths do not restart
- fatal websocket faults still trigger the intended restart mode
- non-fatal internal close paths still prefer soft resubscribe
- no broker/order side effects are introduced

## What This PR Does Not Prove

This PR does not prove live websocket recovery, broker connectivity, subscription correctness, runtime snapshot correctness, execution quality, or profitability. It only proves a deterministic reconnect decision surface for future feed callback refactors.

## Human Approval

Ready for maintainer review after CI is green.

## Next Action

After this PR is merged, continue with `PR-FEED-10 — Extract Subscription Budget Policy` only from the latest merged main commit.
