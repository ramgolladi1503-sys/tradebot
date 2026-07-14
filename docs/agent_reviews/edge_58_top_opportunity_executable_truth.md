# EDGE-58 — Agent Review Evidence

mode: PAPER
candidate_id: EDGE-58-TOP-OPPORTUNITY-EXECUTABLE-TRUTH
source: docs/agent_reviews/edge_58_top_opportunity_executable_truth.md
decision: ADD_TOP_OPPORTUNITY_EXECUTABLE_TRUTH_CONTRACT
reason: Top executable opportunity lists must require canonical execution-entry truth and must demote display-only or fallback rows.
timestamp: 2026-05-24T13:32:33Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
append: false

## Agent Work Contract

- PR: EDGE-58 — Top Opportunity Executable Truth Contract
- Scope: normalize top executable/advisory opportunity lists using canonical execution-entry truth
- Out of scope: broker calls, order placement, strategy tuning, score-weight changes, threshold loosening, dashboard rewrite, runtime mutation

## Grill Me Review

Concern: A row can claim executable via stale legacy fields while only having display/fallback evidence.

Response: `classify_top_opportunity_row(...)` requires positive `execution_entry`, `execution_entry_status=executable`, and execution-grade source. Fallback/display-only rows are demoted.

## Hermes Review

The contract emits explicit evidence:

- source executable count
- source advisory count
- top executable count
- top advisory count
- demoted count
- per-row truth reason
- non-action metadata

## GSD Review

This PR does not wire the contract into the large Streamlit runtime. It creates the deterministic seam first so EDGE-59 can safely wire it into the writer/reader.

## Scope Guard

- `is_order_action=false`
- `broker_api_called=false`
- `live_order_action=false`
- `broker_order_action=false`
- `append=false`
- no broker imports
- no live/order behavior
- no strategy/scoring changes

## QA / Safety Review

The targeted tests prove both safe and unsafe paths:

- canonical execution-entry rows stay top executable
- display-only legacy executable claims are demoted
- fallback and recovered-fallback rows are demoted
- advisory-source rows are not promoted into executable
- mixed payloads preserve true executable rows while demoting false executable rows

## Acceptance Proof

Targeted test command:

```bash
PYTHONPATH=. python -m pytest tests/test_edge58_top_opportunity_executable_truth.py
```

Expected proof: all EDGE-58 targeted tests pass and the contract report emits explicit non-action fields.

## Runtime Proof Required After Merge

EDGE-58 is contract-only. After merge, EDGE-59 must wire `normalize_top_opportunity_payload(...)` into the top-opportunities snapshot writer or dashboard reader and verify the UI no longer shows display-only/fallback rows in the top executable section.

## What This PR Does Not Prove

- It does not prove live profitability.
- It does not tune score weights.
- It does not wire the contract into the Streamlit runtime page.
- It does not change broker/order behavior.
- It does not prove candidate generation diversity.

## Human Approval

Approved for PR as a read-only executable-truth contract for top opportunity lists.


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
