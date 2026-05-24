# EDGE-58 — Agent Review Evidence

## Agent Work Contract

- PR: EDGE-58 — Top Opportunity Executable Truth Contract
- Mode: PAPER / read-only contract
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

## Evidence

Targeted test command:

```bash
PYTHONPATH=. python -m pytest tests/test_edge58_top_opportunity_executable_truth.py
```

## Approval

Approved for PR as a read-only executable-truth contract for top opportunity lists.
