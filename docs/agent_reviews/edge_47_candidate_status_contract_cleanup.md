# Agent Review Evidence — EDGE-47 Candidate Status Contract Cleanup

mode: PAPER
candidate_id: EDGE-47-CANDIDATE-STATUS-CONTRACT-CLEANUP
decision: ADD_READ_ONLY_CANDIDATE_STATUS_CONTRACT
reason: Separate price feasibility from execution permission so legacy executable wording cannot be confused with runtime action permission.
timestamp: 2026-05-24T06:55:01Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
source: docs/EDGE_47_CANDIDATE_STATUS_CONTRACT_CLEANUP.md and tests/test_edge47_candidate_status_contract.py

## Agent Work Contract

Scope: add a pure candidate status contract for EDGE-47.

Allowed:

- add a read-only classifier
- add focused tests
- add documentation and agent-review evidence

Not allowed:

- broker integration calls
- live runtime action behavior
- dashboard migration
- strategy tuning
- threshold loosening
- runtime behavior changes

## Grill Me Review

Risk: `execution_entry_status=executable` may be interpreted as runtime action permission.

Decision: the contract emits separate `price_feasibility_status` and `execution_permission_status` fields. Covered by the legacy executable entry status test.

Risk: advisory-only rows may still look executable because the entry can be priced.

Decision: advisory-only blocks execution permission while preserving price feasibility. Covered by advisory-only test.

Risk: stale quote or other blockers may be hidden by a legacy executable marker.

Decision: stale quote makes price not feasible and execution blocked even when explicit execution_allowed is true. Covered by stale quote test.

## Hermes Review

No external APIs, broker adapters, runtime mutation, live action behavior, or dashboard changes are introduced.

The new module is pure and consumes candidate dictionaries/objects only.

## GSD Review

This PR solves one narrow roadmap bug: status contract wording cleanup. It does not migrate dashboards or runtime evidence producers to the new contract.

## Scope Guard

- in_scope_list: candidate status contract, focused tests, docs, agent evidence
- out_of_scope_list: dashboard migration, runtime wiring, broker adapters, live action behavior, strategy tuning
- files_changed_list: core/candidate_status_contract.py, tests/test_edge47_candidate_status_contract.py, docs/EDGE_47_CANDIDATE_STATUS_CONTRACT_CLEANUP.md, docs/agent_reviews/edge_47_candidate_status_contract_cleanup.md
- files_not_touched_list: execution engine, broker clients, dashboard app, strategy modules, runtime startup
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- dashboard_changed: false
- strategy_changed: false
- thresholds_changed: false

## QA / Safety Review

- The classifier is deterministic and read-only.
- Price feasibility and execution permission are separate outputs.
- Execution remains blocked when advisory, stale, fallback, risk, signal, or safety blockers are present.
- Tests cover negative and precedence paths.

## Runtime Proof Required After Merge

- Confirm future runtime evidence can emit both `price_feasibility_status` and `execution_permission_status`.
- Confirm future UI/reporting reads permission status for execution safety and price feasibility only for entry-pricing diagnostics.
- Confirm no broker or live runtime action path is affected by this read-only contract.

## What This PR Does Not Prove

- It does not prove dashboard rendering is migrated.
- It does not prove selector evidence explains no-rankable counts.
- It does not prove strategy quality or profitability.
- It does not prove paper trading acceptance.

## Human Approval

Approved for PR scope: EDGE-47 only, read-only candidate wording cleanup, no external integration/runtime/dashboard behavior change.

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_edge47_candidate_status_contract.py
```

Expected: all EDGE-47 candidate-status contract tests pass.

## High-Risk Path Review

N/A
