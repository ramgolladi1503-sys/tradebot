# PR-FEED-18 WebSocket Lifecycle Shell Agent Review

mode: REVIEW
candidate_id: pr_feed_18_ws_lifecycle_shell
decision: review_ready
reason: ws_lifecycle_shell_tests_docs
timestamp: 2026-05-27T19:46:00Z
source: pr_feed_18_agent_review
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

This review covers PR-FEED-18 only.

The PR adds pure, deterministic lifecycle shell helpers for feed websocket handling. It must not wire runtime callbacks, execute trades, place or modify orders, call broker APIs, or change dashboard/UI surfaces.

## Scope Guard

Allowed:

- Add pure lifecycle shell helper functions.
- Add focused unit tests.
- Add documentation and agent-review evidence.
- Shrink `docs/EDGE_TODO.md` for the completed PR.

Not allowed:

- Broker calls.
- Order actions.
- Runtime wiring.
- Dashboard/UI work.
- Subscription behavior changes.
- Reconnect policy changes.
- Callback rewiring.
- Filesystem writes from the helper module.
- Hidden config or time calls inside the helper module.

## Grill Me Review

Question: Can this PR place, modify, cancel, or route an order?

Answer: No. The changed helper module has no broker imports, no execution imports, and no order-facing functions.

Question: Can this PR change runtime websocket behavior?

Answer: No. `core/kite_depth_ws.py` is not rewired in this PR. The helper surface is created first for deterministic testing.

Question: Can this PR hide lifecycle timing behind wall-clock calls?

Answer: No. The helpers receive lifecycle observations and policy intent as explicit inputs. They do not call time APIs.

Question: Can auth-required or stop-requested states accidentally start connection/subscription work?

Answer: No. Auth-required and stop-requested paths return blocking or stopping transitions with no connect or subscribe flags.

Question: Can evidence payloads accidentally be treated as order actions?

Answer: No. Transition and evidence payloads explicitly set `is_order_action=false` and `broker_api_called=false`.

## Hermes Review

The public helper contract is intentionally narrow:

- `WsLifecycleState`
- `WsLifecycleTransition`
- `normalize_phase(...)`
- `normalize_event(...)`
- `normalize_action(...)`
- `positive_count(...)`
- `normalize_token_sample(...)`
- `is_terminal_stop_phase(...)`
- `is_active_phase(...)`
- `build_lifecycle_state(...)`
- `derive_phase_from_runtime(...)`
- `transition_for_connect_request(...)`
- `transition_for_connected(...)`
- `transition_for_subscribe_request(...)`
- `transition_for_subscribed(...)`
- `transition_for_disconnect(...)`
- `transition_for_error(...)`
- `transition_for_stop_request(...)`
- `apply_transition(...)`
- `build_lifecycle_evidence(...)`

These helpers are pure value transforms. Callers must pass observations explicitly.

## GSD Review

The implementation stays deterministic and local:

- No hidden global state.
- No network calls.
- No broker imports.
- No filesystem writes.
- No logging side effects.
- No callback mutation.
- Invalid optional values normalize to deterministic defaults.

## QA / Safety Review

Focused test coverage includes:

- phase/event/action normalization
- identifier sample normalization
- terminal and active phase classification
- auth-required phase derivation
- stop-requested phase derivation
- market-closed phase derivation
- subscribed phase derivation
- connect-request auth/stop/market blocking
- connect-request allowed transition
- connected marking transition
- subscribe-request disconnected/no-token blocking
- subscribe-request allowed transition
- subscription confirmation transition
- disconnect restart transition
- disconnect soft-refresh transition
- disconnect plain mark transition
- error auth block
- error restart decision
- error record-only decision
- transition application
- lifecycle evidence safety flags

## Acceptance Proof

Run:

```bash
pytest tests/test_pr_feed_18_ws_lifecycle_shell.py
```

CI must pass before merge.

## Runtime Proof Required After Merge

A later PR may wire these helpers into `core/kite_depth_ws.py` only if explicitly scoped. That later PR must prove:

- existing callback behavior remains backward-compatible
- auth-required paths remain fail-closed
- stop-requested paths do not reconnect
- subscribe paths require a connected feed and non-empty identifiers
- restart and soft-refresh flags map to existing behavior
- no broker/order side effects are introduced

## What This PR Does Not Prove

This PR does not prove runtime recovery, broker connectivity, subscription correctness, runtime snapshot correctness, execution quality, or profitability. It only proves a deterministic lifecycle shell surface for future feed callback refactors.

## Human Approval

Ready for maintainer review after CI is green.

## Next Action

After this PR is merged, continue with PR-FEED-19 only from the latest merged main commit.


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
