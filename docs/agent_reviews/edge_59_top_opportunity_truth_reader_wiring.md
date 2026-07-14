# EDGE-59 — Agent Review Evidence

mode: PAPER
candidate_id: EDGE-59-TOP-OPPORTUNITY-TRUTH-READER-WIRING
source: docs/EDGE_59_TOP_OPPORTUNITY_TRUTH_READER_WIRING.md
decision: WIRE_TOP_OPPORTUNITY_TRUTH_INTO_DASHBOARD_READER
reason: The dashboard reader should normalize top opportunity lists before UI/runtime consumers see false executable quality.
timestamp: 2026-05-24T13:58:32Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
append: false

## Agent Work Contract

- PR: EDGE-59 — Top Opportunity Truth Reader Wiring
- Scope: apply the EDGE-58 truth contract inside `dashboard/readers/snapshot_reader.py`
- Out of scope: strategy tuning, scoring-weight changes, threshold loosening, snapshot writer mutation, broad runtime page rewrite

## Grill Me Review

Concern: A contract that is not wired into a reader can still leave UI consumers exposed to false top-executable rows.

Response: `read_snapshot_payload(...)` now detects top-opportunity payloads, applies `normalize_top_opportunity_payload(...)`, and returns `top_opportunity_truth_report` evidence.

## Hermes Review

This PR is reader-only and non-actionable. It does not mutate snapshot artifacts.

Required fields:

- `is_order_action=false`
- `broker_api_called=false`
- `live_order_action=false`
- `broker_order_action=false`
- `append=false`

## GSD Review

EDGE-59 is the smallest safe wiring step after EDGE-58. It avoids a large runtime page rewrite while ensuring dashboard snapshot consumers receive normalized top-opportunity lists.

## Scope Guard

- `in_scope_list`: dashboard snapshot reader normalization, reader-boundary tests, docs, evidence
- `out_of_scope_list`: strategy tuning, scoring changes, threshold loosening, snapshot writer mutation, broad runtime page rewrite
- `files_changed_list`: dashboard/readers/snapshot_reader.py, tests/test_edge59_top_opportunity_truth_reader_wiring.py, docs/EDGE_59_TOP_OPPORTUNITY_TRUTH_READER_WIRING.md, docs/agent_reviews/edge_59_top_opportunity_truth_reader_wiring.md
- `files_not_touched_list`: strategy modules, scoring modules, runtime snapshot writer, Streamlit runtime layout

## QA / Safety Review

The targeted tests prove:

- display-only rows under `top_executable_opportunities` are demoted at the reader boundary
- fallback rows under `top_executable_opportunities` are demoted at the reader boundary
- canonical rows remain under `top_executable_opportunities`
- unrelated snapshot payloads are unchanged
- normalized reports carry explicit non-action fields

## Acceptance Proof

Targeted command:

```bash
PYTHONPATH=. python -m pytest tests/test_edge59_top_opportunity_truth_reader_wiring.py
```

Expected proof: reader-boundary normalization passes and unrelated snapshot payloads are preserved.

## Runtime Proof Required After Merge

After merge, open the dashboard against a `top_opportunities_latest.json` payload containing one display-only or fallback row under `top_executable_opportunities`. The row should appear under advisory output after reader normalization, and `top_opportunity_truth_report.demoted_count` should be greater than zero.

## What This PR Does Not Prove

- It does not prove profitability.
- It does not tune score weights.
- It does not mutate snapshot artifacts.
- It does not rewrite the dashboard runtime page.
- It does not change candidate generation.

## Human Approval

Approved for PR as a reader-boundary wiring change for EDGE-58 top opportunity truth.


## High-Risk Path Review

N/A
