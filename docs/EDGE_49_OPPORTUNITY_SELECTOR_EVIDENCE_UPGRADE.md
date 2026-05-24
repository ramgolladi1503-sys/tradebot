# EDGE-49 — Opportunity Selector Evidence Upgrade

## Purpose

Add read-only evidence explaining what the selector would choose from ranked candidates and why every non-selected row was not chosen.

This addresses the product gap where the UI/report can show survived rows without explaining whether they are true opportunities, blocked candidates, advisory/debug rows, or simply below the selection limit.

## Implementation

Added `core/opportunity_selector_evidence.py`.

The contract exposes:

- `OpportunitySelectionEvidenceRecord`
- `OpportunitySelectorEvidenceReport`
- `build_opportunity_selector_evidence(ranking_report, selection_limit=3)`

## Evidence Captured

The report includes:

- source rank count
- selected count
- not-selected count
- executable source count
- score-eligible source count
- blocked source count
- no-selection reason
- selected strategy IDs
- per-rank selector decision and selector reason
- rejection reasons
- warnings
- safety flags

## Safety Rules

A candidate is selected only when it is:

- score eligible
- executable candidate
- unblocked
- inside the selection limit

All other rows remain visible in evidence with reasons.

## Scope Guard

Out of scope:

- no runtime selector wiring
- no dashboard migration
- no broker integration changes
- no live runtime behavior changes
- no strategy tuning
- no score-weight changes
- no threshold loosening

## Tests

```bash
PYTHONPATH=. python -m pytest tests/test_edge49_opportunity_selector_evidence.py
```

The tests prove:

- only score-eligible executable unblocked rows are selected
- blocked/advisory rows get explicit reasons
- no ranked candidates produces a clear reason
- no score-eligible candidates produces a clear reason
- no executable candidates produces a clear reason
- selection-limit behavior is explained
- report remains read-only and non-action
