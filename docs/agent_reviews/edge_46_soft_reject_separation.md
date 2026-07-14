# Agent Review Evidence — EDGE-46 Soft Reject Separation

mode: PAPER
candidate_id: EDGE-46-SOFT-REJECT-SEPARATION
decision: ADD_READ_ONLY_CANDIDATE_STATE_CONTRACT
reason: Separate candidate lifecycle states so unsafe, soft-rejected, advisory, debug, rankable, and executable rows cannot be treated as the same state.
timestamp: 2026-05-24T06:40:43Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
source: docs/EDGE_46_SOFT_REJECT_SEPARATION.md and tests/test_edge46_candidate_state_contract.py

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

- in_scope_list: candidate state classifier, focused tests, docs, agent evidence
- out_of_scope_list: dashboard migration, strategy tuning, broker adapters, order behavior, runtime mutation
- files_changed_list: core/candidate_state_contract.py, tests/test_edge46_candidate_state_contract.py, docs/EDGE_46_SOFT_REJECT_SEPARATION.md, docs/agent_reviews/edge_46_soft_reject_separation.md
- files_not_touched_list: execution engine, broker clients, dashboard app, strategy modules, runtime startup
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- dashboard_changed: false
- strategy_changed: false
- thresholds_changed: false

## QA / Safety Review

- The classifier is pure and deterministic.
- Hard-reject markers take precedence over executable and rankable markers.
- Advisory and debug-only rows are not considered executable.
- Unclassified rows fail closed to soft reject.
- Tests cover negative and precedence paths.

## Runtime Proof Required After Merge

- Confirm future runtime evidence can emit the canonical `candidate_state` field.
- Confirm logs/UI consumers read the canonical state instead of inferring from mixed raw strings.
- Confirm no broker or live-order path is affected by this read-only contract.

## What This PR Does Not Prove

- It does not prove dashboard rendering is corrected.
- It does not prove EDGE-47 feasibility wording cleanup.
- It does not prove strategy quality or profitability.
- It does not prove paper trading acceptance.

## Human Approval

Approved for PR scope: EDGE-46 only, read-only candidate state separation, no broker/runtime/dashboard behavior change.

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_edge46_candidate_state_contract.py
```

Expected: all EDGE-46 candidate-state contract tests pass.

## High-Risk Path Review

N/A
