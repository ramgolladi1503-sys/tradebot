# EDGE-61 — Capital Allocation / Selection Policy Contract

## Purpose

EDGE-61 adds a read-only capital allocation and selection policy contract. It explains which ranked/top opportunity rows may be selected, capped, skipped, or blocked.

This PR does not allocate real capital in runtime, place orders, optimize aggressively, call brokers, add ML, or tune strategies.

## Why this exists

The UI problem was not just ranking bias. The product also listed trades without a clear explanation of:

- how many candidates may be selected
- how much capital each candidate may receive
- why a candidate is skipped
- why fallback/advisory candidates must receive zero allocation
- whether symbol/family caps were applied

Without this contract, the system can look organized while still leaving capital decisions manual, hidden, or unsafe.

## Added module

`core/capital_selection_policy.py`

Primary API:

```python
from core.capital_selection_policy import CapitalSelectionPolicy, explain_capital_selection_policy

policy = CapitalSelectionPolicy(
    total_capital=1000.0,
    max_selected=2,
    max_allocation_per_candidate=400.0,
    default_allocation_per_candidate=250.0,
    max_per_symbol=1,
    max_per_family=1,
)

report = explain_capital_selection_policy(payload_or_rows, policy=policy)
```

Accepted input:

- `top_executable_opportunities`
- `ranked_opportunities`
- `selected_candidates`
- `candidates`
- `rows`
- `items`
- `top_advisory_opportunities`
- flat iterables of candidate rows

## What it proves

- No selected candidate can exceed `max_allocation_per_candidate`.
- Non-executable/advisory/fallback candidates receive zero allocation.
- Selection limit is enforced.
- Symbol caps are explainable.
- Family caps are explainable.
- Budget exhaustion is explainable.
- Eligible skipped candidates do not get empty `NO_SELECTION` style reasons.

## Report output

The report includes:

- normalized policy
- selected count
- capped count
- skipped count
- blocked count
- total assigned allocation
- remaining capital
- per-candidate selection records
- warnings
- explicit non-action metadata

Every record includes:

- candidate ID
- rank
- symbol
- family
- source list
- status: `SELECTED`, `CAPPED`, `SKIPPED`, or `BLOCKED`
- requested allocation
- assigned allocation
- reason
- executable eligibility
- non-action evidence

## Fail-closed behavior

Rows with unknown execution eligibility are treated as non-executable and receive zero allocation with:

```text
not_execution_eligible
```

Fallback/stale rows receive:

```text
fallback_or_stale_data_advisory_only
```

Advisory/display-only rows receive:

```text
advisory_or_display_only_candidate
```

## Non-action safety metadata

Every report includes:

```json
{
  "read_only": true,
  "is_order_action": false,
  "broker_api_called": false,
  "live_order_action": false,
  "broker_order_action": false,
  "append": false
}
```

## Scope boundaries

This PR does not:

- change existing `core/capital_allocator.py`
- change strategy logic
- change ranking score weights
- loosen thresholds
- wire runtime allocation
- place orders
- submit, modify, cancel, or exit orders
- add broker imports
- call broker APIs
- rewrite the dashboard

## Test evidence

Target command:

```bash
PYTHONPATH=. python -m pytest tests/test_edge61_capital_selection_policy_contract.py
```

Acceptance coverage:

- Candidate allocation never exceeds configured maximum.
- Advisory/fallback candidates receive zero allocation.
- Selection limit is enforced.
- Symbol cap is enforced.
- Family cap is enforced.
- Capital budget is enforced.
- Unknown/non-executable candidates fail closed to zero allocation.
- Eligible skipped candidates always have explainable reasons.
- Report output is deterministic except `generated_epoch`.
- Explicit non-action metadata is present.

## Next

EDGE-62 should reconcile the implemented EDGE truth contracts, remaining FEED work, remaining strategy work, and old roadmap items into canonical docs.
