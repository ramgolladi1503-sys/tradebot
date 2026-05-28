# TEST-STAB-04A WebSocket Fixture Compatibility Agent Review

mode: REVIEW
candidate_id: test_stab_04a_websocket_fixture_compatibility
candidate_id: TEST-STAB-04A-WEBSOCKET-FIXTURE-COMPATIBILITY
decision: review_pending
reason: websocket_test_fixture_alignment_with_active_kite_client_contract
timestamp: 2026-05-28T07:12:00Z
source: docs/agent_reviews/TEST_STAB_04A_WEBSOCKET_FIXTURE_COMPATIBILITY.md
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

Issue: #364
Parent: #361
Blocked roadmap: #319 / EDGE-98
PR: #370

## Agent Work Contract

This review covers TEST-STAB-04A only.

The PR restores a websocket test fixture so it represents the current `kite_client` credential contract used by `start_depth_ws(...)`. It must not change production broker behavior, weaken authentication checks, place orders, alter strategies, or hide failing tests.

## Scope Guard

Allowed:

- Align the on-connect websocket test fixture with current active `kite_client` state.
- Preserve focused websocket test intent.
- Keep the PR limited to #364 stabilization.

Not allowed:

- Broker calls.
- Order actions.
- Auth weakening.
- Runtime wiring.
- Strategy/ranking changes.
- Dashboard/UI changes.
- Test skip/xfail.
- Broad cleanup.

## Baseline Failure Under Review

`tests/test_on_connect_forces_subscribe.py` patched `ws.resolve_access_token`, but current `core.kite_depth_ws` no longer exposes that patch point. `start_depth_ws(...)` resolves the REST client through `kite_client.ensure()` and then reads `_active_api_key` / `_active_access_token` from `kite_client`.

## Change Review

The fixture now:

- returns a dummy REST client from `ws.kite_client.ensure()`
- returns the same dummy REST client from `ws.kite_client._ensure()` for compatibility
- sets `ws.kite_client._active_api_key`
- sets `ws.kite_client._active_access_token`
- removes the stale `ws.resolve_access_token` patch

## High-Risk Path Review

This PR touches a websocket-related test, not production websocket code.

Risk assessment:

- A fixture-only change can accidentally mask a real production auth regression.
- The updated fixture must mirror current production behavior rather than bypass it.

Containment:

- The dummy client still has only local methods.
- No external broker call is possible.
- The test continues to assert forced subscribe and full-mode token application after connect.

## Grill Me Review

Question: Does this PR place, modify, cancel, or route an order?

Answer: No.

Question: Does this PR bypass authentication in production?

Answer: No. It changes only the test fixture and sets deterministic local active credential fields.

Question: Does this PR weaken the assertion?

Answer: No. The test still asserts subscribed tokens and mode tokens exactly.

Question: Does this complete all of #364?

Answer: Not by itself. Remaining websocket stability failures around restart payload compatibility must still be addressed before #364 can close.

## Hermes Review

Contract under review:

- `start_depth_ws(...)` uses `kite_client.ensure()` and active client credential fields.
- `on_connect(...)` must force resubscribe and set full mode for cached tokens.

This PR updates the fixture to match that contract.

## GSD Review

Smallest safe change:

- one focused test fixture update
- no production runtime behavior
- no unrelated test edits

## QA / Safety Review

Focused command:

```bash
PYTHONPATH=. pytest tests/test_on_connect_forces_subscribe.py -q
```

Additional #364 focused command:

```bash
PYTHONPATH=. pytest tests/test_kite_depth_ws_stability.py::test_fatal_on_error_schedules_async_forced_full_restart tests/test_kite_depth_ws_stability.py::test_fatal_on_close_schedules_async_forced_full_restart tests/test_kite_depth_ws_stability.py::test_network_error_restarts_without_auth_required tests/test_kite_depth_ws_stability.py::test_network_error_forces_full_restart_when_enabled -q
```

## Acceptance Proof

Evidence auditor fields:

- mode: REVIEW
- candidate_id: TEST-STAB-04A-WEBSOCKET-FIXTURE-COMPATIBILITY
- decision: review_pending
- reason: websocket_test_fixture_alignment_with_active_kite_client_contract
- timestamp: 2026-05-28T07:12:00Z
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- source: docs/agent_reviews/TEST_STAB_04A_WEBSOCKET_FIXTURE_COMPATIBILITY.md

## Runtime Proof Required After Merge

No live runtime proof is required because this PR changes a deterministic test fixture only.

## What This PR Does Not Prove

This PR does not prove feed quality, runtime websocket liveness, strategy edge, candidate ranking quality, execution readiness, or EDGE-98 historical dataset behavior.

## Human Approval

User approved proceeding without repeated confirmation in chat. Merge still requires appropriate CI evidence.

## Next Action

Finish remaining #364 websocket stability regressions, then continue through the other TEST-STAB child issues under #361.
