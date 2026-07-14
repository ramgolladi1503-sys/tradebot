# PR4 - Selector Fallback Contract

mode: PAPER
candidate_id: pr4-selector-fallback-contract
signal_id: pr4-selector-fallback-contract
strategy_id: selector_fallback_contract
decision: REVIEW_ONLY
reason: align_runtime_top_selector_fallback_classification_with_offline_expectancy_selector_truth
timestamp: 2026-06-15T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr4-selector-fallback-contract.md

## Agent Work Contract

This PR hardens the runtime top-opportunity selector so fallback-derived candidates cannot appear executable in `core.opportunity_engine` when the offline expectancy selector would already reject them.

Source contract:

```text
source_agent: Codex (GPT-5)
action: GENERATE_PATCH
title: Unify fallback truth for top opportunity selectors
scope: update runtime selector fallback classification and add focused truth-guard tests; do not change broker, order, execution routing, strategy thresholds, or live mode
requested_paths:
  - core/opportunity_engine.py
  - tests/test_opportunity_engine_truth_guard.py
  - docs/agent_reviews/pr4-selector-fallback-contract.md
allowed_paths:
  - core/opportunity_engine.py
  - tests/test_opportunity_engine_truth_guard.py
  - docs/agent_reviews/*
forbidden_paths:
  - core/broker*
  - core/order*
  - core/execution*
  - core/risk*
  - core/feed*
  - strategies/*
  - config/*
  - dashboard/*
  - run_live.sh
expected_tests:
  - tests/test_opportunity_engine_truth_guard.py
  - tests/test_edge41_fallback_execution_firewall.py
  - tests/test_opportunity_engine.py
  - agent review evidence validator
acceptance_proof:
  - REST_FALLBACK, SYNTHETIC_OFFHOURS, SUBSCRIPTION_FAILED, softrej rows, and fallback-tagged rows classify as fallback in the runtime selector
  - those rows cannot surface in top executable opportunities
  - clean executable rows remain executable
```

## Scope Guard

In scope:

- Harden runtime selector fallback classification in `core.opportunity_engine`.
- Add focused regression tests for quote-source and trade-id fallback markers.

Out of scope:

- No broker code.
- No order code.
- No execution router changes.
- No strategy generation changes.
- No dashboard changes.
- No threshold changes.

Boundary verification:

- [x] No broker code touched
- [x] No execution router touched
- [x] No strategy file touched
- [x] No risk gate weakened
- [x] No threshold changed

## Grill Me Review

The defect is wiring drift, not model quality. The repo had two selector surfaces with different fallback contracts. That is dangerous because offline evidence can reject a candidate while the runtime selector still considers it executable.

The fix is conservative. It does not invent new executable paths. It only expands runtime fallback detection to match already-established failure markers like fallback quote sources and `softrej_*` identifiers.

Verdict: PASS. Narrow, safety-positive, and overdue.

## Hermes Review

Architecture is improved because runtime and offline selector paths now share the same fallback truth markers at the classification boundary.

Changed files:

- `core/opportunity_engine.py`
- `tests/test_opportunity_engine_truth_guard.py`
- `docs/agent_reviews/pr4-selector-fallback-contract.md`

No runtime action path is widened. The change is still read-only classification for selection visibility.

Verdict: PASS.

## GSD Review

Delivery stayed scoped:

- one runtime selector classification patch
- focused truth-guard regression coverage
- no unrelated refactor

This is the correct next PR because it removes a selector-contract inconsistency instead of adding another layer of heuristics.

Verdict: PASS.

## QA / Safety Review

Safety properties preserved:

- `is_order_action=false`
- `broker_api_called=false`
- no broker imports
- no live-mode change
- no execution promotion added

Test proof targets:

- fallback quote sources classify as fallback
- `softrej_*` rows classify as fallback
- fallback rows cannot appear in `top_executable_opportunities`
- clean executable rows still pass existing selector tests

## Acceptance Proof

Commands run:

```bash
python -m pytest -q tests/test_opportunity_engine_truth_guard.py tests/test_edge41_fallback_execution_firewall.py tests/test_opportunity_engine.py
python scripts/validate_agent_review_evidence.py
```

Observed result before merge:

- focused selector truth suite passed locally: `41 passed`

Acceptance expectations:

- runtime selector no longer treats fallback-derived rows as executable because the prior `candidate_class` inference omitted those fallback markers
- advisory visibility remains intact for fallback rows
- clean rows are unaffected

## Runtime Proof Required After Merge

No live runtime proof is required for this PR because the change is a selector classification hardening pass only.

If a later PR rewires selector outputs into a broader runtime decision boundary, that later PR must prove the end-to-end contract again.

## What This PR Does Not Prove

This PR does not prove trading edge.

It does not prove the ranking model is correct.

It does not fix orchestrator recovery or execution realism.

It only proves the runtime selector no longer disagrees with the offline selector about obvious fallback truth.

## Human Approval

Human approval is required before merge.

Reviewers should verify that the fallback markers are intentionally conservative and do not suppress clean live candidates.


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
