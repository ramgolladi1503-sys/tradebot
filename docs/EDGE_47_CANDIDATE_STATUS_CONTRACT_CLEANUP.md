# EDGE-47 — Candidate Status Contract Cleanup

## Purpose

Separate price feasibility from execution permission.

The bug being fixed is that legacy fields such as `execution_feasibility.status=executable` or `execution_entry_status=executable` can be misunderstood as `execution_allowed=true`.

EDGE-47 introduces an explicit read-only contract with two different outputs:

- `price_feasibility_status`
- `execution_permission_status`

## Implementation

Added `core/candidate_status_contract.py`.

The contract exposes:

- `CandidateStatusContractDecision`
- `classify_candidate_status_contract(candidate)`
- explicit price feasibility statuses:
  - `price_feasible`
  - `price_not_feasible`
  - `price_unknown`
- explicit execution permission statuses:
  - `execution_allowed`
  - `execution_blocked`
  - `execution_permission_unknown`

## Safety Rule

A candidate can be price-feasible while still blocked from execution.

Examples:

- `execution_entry_status=executable` and `execution_allowed=false`
- `execution_entry_status=executable` and `advisory_only=true`
- `entry_price` present but stale quote/fallback/risk blockers present

## Scope Guard

Out of scope:

- no broker calls
- no live order behavior
- no order placement
- no modify/cancel/exit behavior
- no dashboard migration
- no strategy tuning
- no threshold loosening
- no runtime behavior change

## Tests

```bash
PYTHONPATH=. python -m pytest tests/test_edge47_candidate_status_contract.py
```

The tests prove:

- legacy executable entry status only means price feasibility
- advisory-only feasible rows remain execution-blocked
- explicit execution permission is separate from price feasibility
- stale quote makes price not feasible and execution blocked
- unknown price/permission fails closed to not allowed
- source flags are supported without mutation
