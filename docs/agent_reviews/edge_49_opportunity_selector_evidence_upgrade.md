# Agent Review Evidence — EDGE-49 Opportunity Selector Evidence Upgrade

mode: PAPER
candidate_id: EDGE-49-OPPORTUNITY-SELECTOR-EVIDENCE-UPGRADE
decision: ADD_READ_ONLY_SELECTOR_EVIDENCE_CONTRACT
reason: Explain selected and non-selected ranked candidates so survived rows are not mistaken for true opportunities.
timestamp: 2026-05-24T09:42:18Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
source: docs/EDGE_49_OPPORTUNITY_SELECTOR_EVIDENCE_UPGRADE.md and tests/test_edge49_opportunity_selector_evidence.py

## Agent Work Contract

Scope: add a pure selector evidence contract for EDGE-49.

Allowed:

- add read-only selector evidence
- consume existing candidate ranking records
- add focused tests
- add documentation and evidence

Not allowed:

- runtime selector wiring
- dashboard migration
- broker integration changes
- live runtime behavior changes
- strategy tuning
- score-weight changes
- threshold loosening

## Grill Me Review

Risk: a UI/report may show survived rows without explaining which rows are actual top opportunities.

Decision: selector evidence emits selected and non-selected records with explicit selector reasons. Covered by the selected/blocked/advisory test.

Risk: a no-selection day may look like a broken product instead of a valid safety outcome.

Decision: selector evidence emits `no_selection_reason` values such as `no_ranked_candidates`, `no_score_eligible_candidates`, and `no_executable_candidates`. Covered by no-selection tests.

Risk: lower-ranked rows may be hidden without explaining whether they were unsafe or merely outside the top limit.

Decision: selection-limit behavior is explicitly reported. Covered by selection-limit tests.

## Hermes Review

No external APIs, broker adapters, runtime mutation, live action behavior, or dashboard changes are introduced.

The new module is pure and consumes ranking records only.

## GSD Review

This PR solves one narrow roadmap bug: selection evidence must explain ranked candidates. It does not migrate dashboard rendering, change strategy quality, tune score weights, or alter runtime selection behavior.

## Scope Guard

- in_scope_list: selector evidence contract, focused tests, docs, agent evidence
- out_of_scope_list: runtime selector wiring, dashboard migration, broker adapters, live action behavior, strategy tuning, score-weight changes, threshold changes
- files_changed_list: core/opportunity_selector_evidence.py, tests/test_edge49_opportunity_selector_evidence.py, docs/EDGE_49_OPPORTUNITY_SELECTOR_EVIDENCE_UPGRADE.md, docs/agent_reviews/edge_49_opportunity_selector_evidence_upgrade.md
- files_not_touched_list: execution engine, broker clients, dashboard app, strategy modules, runtime startup
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- dashboard_changed: false
- strategy_changed: false
- thresholds_changed: false

## QA / Safety Review

- The contract is deterministic and read-only.
- Selected rows must be score eligible, executable, and unblocked.
- Non-selected rows retain explicit reasons.
- No-selection outcomes are explicit.
- Selection-limit outcomes are explicit.
- Tests cover negative and edge paths.

## Runtime Proof Required After Merge

- Confirm future runtime evidence can emit selector evidence reports.
- Confirm future UI/reporting shows top opportunities separately from all candidate diagnostics.
- Confirm no broker or live runtime action path is affected by this read-only contract.

## What This PR Does Not Prove

- It does not prove runtime selector wiring has migrated.
- It does not prove dashboard rendering has migrated.
- It does not prove strategy quality or profitability.
- It does not prove paper trading acceptance.

## Human Approval

Approved for PR scope: EDGE-49 only, read-only selector evidence upgrade, no external integration/runtime/dashboard behavior change.

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_edge49_opportunity_selector_evidence.py
```

Expected: all EDGE-49 selector evidence tests pass.


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
