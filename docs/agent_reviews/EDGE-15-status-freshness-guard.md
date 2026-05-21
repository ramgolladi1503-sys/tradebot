# EDGE-15 — Status Freshness Guard

## Evidence Contract

mode: PAPER
candidate_id: EDGE-15-status-freshness-guard
decision: ADD_STATUS_FRESHNESS_GUARD
reason: fresh runtime status must not inherit old auth-required WebSocket failure after newer live auth health proves OK
timestamp: 2026-05-21T07:25:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/EDGE-15-status-freshness-guard.md

## Scope

Allowed:

- add pure runtime auth freshness resolver
- make runtime auth snapshot prefer newer live auth health OK over older persisted auth-required state
- preserve fresh auth-required state when it is newer than auth health
- add unit tests
- add agent review evidence

Not included:

- strategy changes
- scoring changes
- ranking changes
- threshold changes
- credential handling changes
- reconnect behavior changes
- broker behavior changes
- live order behavior changes
- dashboard changes

## Tests

python -m pytest tests/test_runtime_auth_freshness.py

## Acceptance Proof

- older auth-required WebSocket failure is superseded by newer live auth health OK
- newer auth-required state is not incorrectly ignored
- missing auth state does not create fake auth failure
- no runtime trading behavior is changed
