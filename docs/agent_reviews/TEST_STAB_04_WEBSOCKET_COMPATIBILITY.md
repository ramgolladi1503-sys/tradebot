# TEST-STAB-04 Agent Review Evidence

mode: REVIEW
candidate_id: test_stab_04_websocket_compatibility
candidate_id: TEST-STAB-04-WEBSOCKET-COMPATIBILITY
decision: review_pending
reason: websocket_restart_compatibility_regression_triage
timestamp: 2026-05-28T06:45:00Z
source: docs/agent_reviews/TEST_STAB_04_WEBSOCKET_COMPATIBILITY.md
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

Issue: #364
Parent: #361
Blocked roadmap: #319 / EDGE-98

## Agent Work Contract

This review covers TEST-STAB-04 only.

The PR restores websocket restart compatibility regressions before EDGE-98 work resumes. It must not change broker authentication policy, place orders, alter strategy selection, wire new runtime behavior, or weaken tests.

## Scope Guard

Allowed:

- Fix websocket restart callback compatibility.
- Preserve non-action restart evidence semantics.
- Restore legacy patch points required by focused tests when safe.
- Add focused evidence for #364.

Not allowed:

- Broker calls.
- Order actions.
- Auth weakening.
- Strategy changes.
- Ranking changes.
- Dashboard/UI changes.
- Broad feed lifecycle refactor.
- Test skipping, xfail, or assertion weakening.

## Baseline Failures

- `tests/test_kite_depth_ws_stability.py::test_fatal_on_error_schedules_async_forced_full_restart`
- `tests/test_kite_depth_ws_stability.py::test_fatal_on_close_schedules_async_forced_full_restart`
- `tests/test_kite_depth_ws_stability.py::test_network_error_restarts_without_auth_required`
- `tests/test_kite_depth_ws_stability.py::test_network_error_forces_full_restart_when_enabled`
- `tests/test_on_connect_forces_subscribe.py::test_on_connect_forces_subscribe`

## High-Risk Path Review

This PR touches websocket lifecycle behavior, so the risk is explicit.

Risk assessment:

- Restart compatibility can accidentally hide a real websocket fault.
- Auth patch compatibility can accidentally bypass auth checks.
- Any fix must preserve fail-closed behavior for auth errors.

Containment:

- Keep the change scoped to compatibility restoration.
- Do not change order/execution modules.
- Do not introduce network calls in tests.
- Do not weaken auth-required classification.

## Grill Me Review

Question: Can this PR place, modify, cancel, or route an order?

Answer: No. The scope is websocket restart compatibility only.

Question: Can this PR bypass broker authentication?

Answer: No. Auth errors must still mark auth-required state and block startup.

Question: Can this PR hide websocket faults?

Answer: No. Fatal websocket close/error paths must still schedule or trigger restart according to configured reconnect mode.

Question: Can this PR start EDGE-98 work?

Answer: No. EDGE-98 remains blocked by #361 until the suite is green.

## Hermes Review

The public behavior under review is narrow:

- fatal websocket error restart behavior
- fatal websocket close restart behavior
- network error restart path with internal reconnect disabled
- on-connect forced subscribe compatibility

No candidate scoring, paper journal, replay, dashboard, broker, or execution contract is part of this PR.

## GSD Review

The implementation must be small and boring:

- repair signature compatibility
- preserve existing restart intent
- retain non-action evidence fields
- keep tests deterministic

## QA / Safety Review

Focused validation required before ready:

```bash
PYTHONPATH=. pytest tests/test_kite_depth_ws_stability.py::test_fatal_on_error_schedules_async_forced_full_restart tests/test_kite_depth_ws_stability.py::test_fatal_on_close_schedules_async_forced_full_restart tests/test_kite_depth_ws_stability.py::test_network_error_restarts_without_auth_required tests/test_kite_depth_ws_stability.py::test_network_error_forces_full_restart_when_enabled tests/test_on_connect_forces_subscribe.py::test_on_connect_forces_subscribe -q
```

Compile validation required:

```bash
python -m compileall core strategies dashboard scripts
```

## Acceptance Proof

Evidence auditor fields:

- mode: REVIEW
- candidate_id: TEST-STAB-04-WEBSOCKET-COMPATIBILITY
- decision: review_pending
- reason: websocket_restart_compatibility_regression_triage
- timestamp: 2026-05-28T06:45:00Z
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- source: docs/agent_reviews/TEST_STAB_04_WEBSOCKET_COMPATIBILITY.md

## Runtime Proof Required After Merge

No live runtime proof is required for the evidence-only stage. If code changes affect websocket lifecycle, focused tests and CI must prove restart behavior before merge.

## What This PR Does Not Prove

This PR does not prove feed quality, strategy edge, candidate ranking quality, execution readiness, or EDGE-98 historical dataset behavior.

## Human Approval

User approval to proceed without repeated confirmation was given in chat. Merge still requires green CI.

## Next Action

Fix #364 first. Then continue remaining TEST-STAB child issues under #361.
