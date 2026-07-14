# Agent Review Evidence — EDGE-48 Scoring Truth Hardening

mode: PAPER
candidate_id: EDGE-48-SCORING-TRUTH-HARDENING
decision: ADD_READ_ONLY_SCORING_TRUTH_CONTRACT
reason: Prevent high numeric scores from overriding candidate state, price feasibility, and execution permission truth.
timestamp: 2026-05-24T08:48:38Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
source: docs/EDGE_48_SCORING_TRUTH_HARDENING.md and tests/test_edge48_scoring_truth_contract.py

## Agent Work Contract

Scope: add a pure scoring truth contract for EDGE-48.

Allowed:

- add a read-only scoring truth classifier
- consume EDGE-46 candidate state and EDGE-47 candidate status contracts
- add focused negative tests
- add documentation and evidence

Not allowed:

- strategy tuning
- scoring-weight changes
- threshold loosening
- dashboard migration
- runtime wiring
- broker integration changes
- live runtime behavior changes

## Grill Me Review

Risk: a hard-rejected row may carry a high numeric score and create false confidence.

Decision: hard rejects are capped to zero. Covered by `test_hard_reject_zeroes_high_score`.

Risk: advisory or debug rows may look competitive in ranking because their raw score is high.

Decision: debug-only rows are capped to zero, and advisory rows are capped below rankable range. Covered by debug and advisory tests.

Risk: a rankable row without proven price feasibility may still look eligible.

Decision: missing price truth caps the score to soft-reject range and disables ranking eligibility. Covered by rankable-without-price test.

## Hermes Review

No external APIs, broker adapters, runtime mutation, live action behavior, or dashboard changes are introduced.

The new module is pure and consumes candidate and score payloads only.

## GSD Review

This PR solves one narrow roadmap bug: score truth must follow candidate truth. It does not change strategy quality, score weights, runtime selectors, or dashboard rendering.

## Scope Guard

- in_scope_list: scoring truth contract, focused tests, docs, agent evidence
- out_of_scope_list: strategy tuning, score-weight changes, dashboard migration, runtime wiring, broker adapters, live action behavior
- files_changed_list: core/scoring_truth_contract.py, tests/test_edge48_scoring_truth_contract.py, docs/EDGE_48_SCORING_TRUTH_HARDENING.md, docs/agent_reviews/edge_48_scoring_truth_hardening.md
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
- Hard reject and debug-only rows cannot retain high truth scores.
- Advisory rows stay below rankable score range.
- Missing price feasibility prevents ranking eligibility.
- Execution permission controls execution eligibility separately from ranking.
- Tests cover negative and precedence paths.

## Runtime Proof Required After Merge

- Confirm future runtime evidence can emit `truth_score`, `score_cap`, and eligibility flags.
- Confirm future selectors consume truth score and eligibility, not raw score alone.
- Confirm no broker or live runtime action path is affected by this read-only contract.

## What This PR Does Not Prove

- It does not prove selector wiring has migrated.
- It does not prove dashboard rendering has migrated.
- It does not prove strategy quality or profitability.
- It does not prove paper trading acceptance.

## Human Approval

Approved for PR scope: EDGE-48 only, read-only scoring truth hardening, no external integration/runtime/dashboard behavior change.

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_edge48_scoring_truth_contract.py
```

Expected: all EDGE-48 scoring-truth contract tests pass.


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
