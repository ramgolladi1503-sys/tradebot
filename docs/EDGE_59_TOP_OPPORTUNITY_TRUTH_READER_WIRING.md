# EDGE-59 — Top Opportunity Truth Reader Wiring

## Purpose

Wire the EDGE-58 executable-truth contract into the dashboard snapshot reader so consumers of `top_opportunities_latest.json` receive hardened executable/advisory lists.

EDGE-58 created the pure contract. EDGE-59 applies it at the reader boundary before runtime/UI code sees the payload.

## Problem

The top opportunities snapshot can contain rows under `top_executable_opportunities` that are only display/advisory evidence. If the reader passes those through unchanged, the UI can still present false executable quality.

## Implementation

Updated `dashboard/readers/snapshot_reader.py`:

- detects payloads containing `top_executable_opportunities` or `top_advisory_opportunities`
- calls `normalize_top_opportunity_payload(...)`
- returns normalized executable/advisory lists
- attaches `top_opportunity_truth_report` to the payload
- leaves unrelated snapshot payloads unchanged

## Scope Guard

This PR is reader-only.

Out of scope:

- external API integration
- runtime behavior changes outside the reader
- strategy tuning
- scoring-weight changes
- threshold loosening
- large runtime page rewrite
- snapshot writer mutation

## Tests

```bash
PYTHONPATH=. python -m pytest tests/test_edge59_top_opportunity_truth_reader_wiring.py
```

## Acceptance

A display-only or fallback row appearing in `top_executable_opportunities` is demoted to `top_advisory_opportunities` before the dashboard consumes the payload.

Unrelated snapshot payloads remain unchanged.
