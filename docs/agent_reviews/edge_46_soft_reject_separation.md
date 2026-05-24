# Agent Review Evidence — EDGE-46 Soft Reject Separation

## Agent Work Contract

Scope: add a pure candidate state separation contract for EDGE-46.

Allowed:

- add a small read-only classifier
- add focused tests
- add documentation and evidence

Not allowed:

- broker calls
- live order behavior
- dashboard changes
- strategy tuning
- threshold loosening
- changes to execution runtime

## Grill Me Review

Risk: a candidate might contain both unsafe and executable/rankable markers.

Decision: hard reject must win over executable and rankable markers. Covered by test `test_hard_reject_wins_over_executable_and_rankable_markers`.

Risk: soft rejects like `no_signal` could be confused with hard safety blocks.

Decision: soft reject is a separate canonical state. Covered by no-signal and no-candidates-survived tests.

Risk: advisory/debug rows could become rankable or executable due to mixed flags.

Decision: advisory and debug-only are canonical states with higher precedence than executable/rankable. Covered by advisory and debug tests.

## Hermes Review

The implementation uses stable constants and a dataclass payload so future evidence/dashboard code can consume one contract instead of interpreting raw status strings.

No external APIs, broker adapters, runtime mutation, or order operations are introduced.

## GSD Review

This PR solves one narrow roadmap bug: state vocabulary separation. It does not attempt EDGE-47 candidate-status cleanup or UI migration.

## Scope Guard

- is_order_action: false
- broker_api_called: false
- live_order_action: false
- dashboard_changed: false
- strategy_changed: false
- thresholds_changed: false

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_edge46_candidate_state_contract.py
```

Expected: all EDGE-46 candidate-state contract tests pass.
