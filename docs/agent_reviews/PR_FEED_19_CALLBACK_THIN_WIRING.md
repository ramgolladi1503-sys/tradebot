# PR-FEED-19 Callback Thin-Wiring Agent Review

mode: REVIEW
candidate_id: pr_feed_19_callback_thin_wiring
decision: review_ready
reason: callback_thin_wiring_adapter_tests_docs
timestamp: 2026-05-27T20:20:00Z
source: pr_feed_19_agent_review
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

This review covers PR-FEED-19 only.

The PR adds a pure callback adapter that maps websocket callback facts into the PR-FEED-18 lifecycle shell. It must not execute runtime callbacks, place or modify orders, call broker APIs, or change dashboard/UI surfaces.

## Scope Guard

Allowed:

- Add pure callback lifecycle adapter functions.
- Add focused unit tests.
- Add documentation and agent-review evidence.
- Shrink `docs/EDGE_TODO.md` for the completed PR.

Not allowed:

- Broker calls.
- Order actions.
- Dashboard/UI work.
- Runtime callback body rewiring in this PR.
- Subscription behavior changes.
- Reconnect behavior changes.
- Runtime file-write changes.
- Filesystem writes from the adapter module.
- Hidden config or time calls inside the adapter module.

## Grill Me Review

Question: Can this PR place, modify, cancel, or route an order?

Answer: No. The adapter has no broker imports, no execution imports, and no order-facing functions.

Question: Can this PR change live websocket callback behavior?

Answer: No. `core/kite_depth_ws.py` callback bodies are not rewired in this PR. The adapter seam is created first for deterministic testing.

Question: Can auth-required paths accidentally look runnable?

Answer: No. Auth error handling maps to `AUTH_BLOCKED`, snapshot connected false, and explicit runtime state `AUTH_BLOCKED`.

Question: Can stop-requested close paths accidentally reconnect?

Answer: No. Stop-requested close handling maps to `STOPPED` and does not emit restart or soft-resubscribe intent.

Question: Can evidence payloads accidentally be treated as order actions?

Answer: No. Result payloads and nested lifecycle evidence explicitly set `is_order_action=false` and `broker_api_called=false`.

## Hermes Review

The public helper contract is intentionally narrow:

- `WsCallbackLifecycleResult`
- `callback_state_from_runtime(...)`
- `handle_connected_callback(...)`
- `handle_subscribe_callback(...)`
- `handle_error_callback(...)`
- `handle_close_callback(...)`

These helpers are pure value transforms. Callers must pass callback observations explicitly.

## GSD Review

The implementation stays deterministic and local:

- No hidden global state.
- No network calls.
- No broker imports.
- No filesystem writes.
- No logging side effects.
- No callback mutation.
- Invalid optional values normalize to deterministic defaults through the lifecycle shell.

## QA / Safety Review

Focused test coverage includes:

- callback runtime-state normalization
- connected callback mapping
- subscribe callback disconnected blocking
- subscribe callback allowed path
- error callback auth blocking
- error callback restart mapping
- error callback record-only mapping
- close callback stop mapping
- close callback restart mapping
- close callback soft-refresh mapping
- close callback plain-disconnect mapping
- explicit non-action evidence flags

## Acceptance Proof

Run:

```bash
pytest tests/test_pr_feed_19_ws_callback_thin_wiring.py
```

CI must pass before merge.

## Runtime Proof Required After Merge

A later PR may consume these adapter helpers from `core/kite_depth_ws.py` only if explicitly scoped. That later PR must prove:

- existing callback side effects remain backward-compatible
- auth-required paths remain fail-closed
- stop-requested paths do not reconnect
- subscribe paths preserve existing token behavior
- restart and soft-refresh decisions remain compatible with existing reconnect policy
- no broker/order side effects are introduced

## What This PR Does Not Prove

This PR does not prove live websocket recovery, broker connectivity, subscription correctness, runtime snapshot correctness, execution quality, or profitability. It only proves a deterministic callback-adapter seam for future feed callback refactors.

## Human Approval

Ready for maintainer review after CI is green.

## Next Action

After this PR is merged, continue with EDGE-91 only from the latest merged main commit.
