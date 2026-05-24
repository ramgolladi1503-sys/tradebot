# EDGE-58 — Top Opportunity Executable Truth Contract

## Purpose

The UI issue showed a dangerous product gap: top opportunity lists can look like an opportunity engine while still showing display-only or fallback-based rows as if they are executable opportunities.

EDGE-58 adds a read-only contract that separates canonical top executable opportunities from advisory/display-only rows.

## Problem

A row must not appear in `top_executable_opportunities` only because legacy fields say:

- `is_executable=true`
- `execution_status=executable`
- `readiness=READY`
- `permission=EXECUTE`

Those fields can be stale or misleading when the row has no canonical execution entry truth.

## Contract

A row remains in `top_executable_opportunities` only when it has all of the following:

1. Positive `execution_entry`
2. `execution_entry_status=executable`
3. Execution-grade `execution_entry_source` such as `ask`, `bid`, or trusted `last`
4. No fallback quote/display source such as `rest_fallback`, `recovered_fallback`, or `fallback_estimated`

Rows that fail the executable truth contract are demoted to `top_advisory_opportunities` with `top_opportunity_truth_reason`.

## Implementation

Added `core/top_opportunity_executable_truth.py`:

- `classify_top_opportunity_row(...)`
- `normalize_top_opportunity_payload(...)`
- `TopOpportunityTruthRecord`
- `TopOpportunityTruthReport`

This PR is contract-only. It does not rewrite the Streamlit runtime page.

## Safety Scope

No broker imports. No broker calls. No order placement. No submit/modify/cancel/exit behavior. No strategy tuning. No score-weight changes. No threshold loosening. No runtime mutation. No dashboard layout rewrite.

## Tests

```bash
PYTHONPATH=. python -m pytest tests/test_edge58_top_opportunity_executable_truth.py
```

## Follow-up

EDGE-59 should wire `normalize_top_opportunity_payload(...)` into the top-opportunities snapshot writer or dashboard reader so the UI consumes normalized executable/advisory lists.
