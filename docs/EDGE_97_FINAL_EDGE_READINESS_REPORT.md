# EDGE-97 — Final Edge Readiness Report

## Purpose

EDGE-97 adds the final deterministic read-only report for the EDGE chain. It consumes EDGE-96 live-pilot risk throttle evidence and summarizes whether candidates are ready for controlled review.

This is not execution wiring. It is a final evidence report only.

## Scope

This PR adds:

- `core/final_edge_readiness_report.py`
- `tests/test_final_edge_readiness_report.py`
- this documentation
- agent-review evidence
- TODO sequencing update

## Inputs

The report consumes EDGE-96 live-pilot risk throttle evidence from `build_live_pilot_risk_throttle_report(...)` or a compatible payload.

## Required conditions

A candidate is marked ready only when:

- EDGE-96 throttle evidence exists
- EDGE-96 status is `LIVE_PILOT_THROTTLE_PASSED`
- candidate review allowance is true
- boundary fields remain non-action and non-broker

## Fail-closed behavior

The report blocks when:

- throttle evidence is absent
- throttle status is blocked
- no review-allowed candidate exists
- candidate review allowance is false
- boundary fields are present

## Output contract

The report emits:

- top-level readiness status
- candidate count
- ready/blocked candidate counts
- top-level reasons
- per-candidate readiness decisions

Payloads preserve read-only boundary fields:

- `read_only=True`
- `append=False`
- `is_order_action=False`
- `broker_api_called=False`
- `live_order_action=False`
- `broker_order_action=False`

## Boundaries

EDGE-97 does not:

- call brokers
- alter order lifecycle paths
- rank candidates
- generate candidates
- change strategies
- change execution behavior
- wire runtime loops
- write runtime artifacts
- wire dashboard/UI
- start another roadmap item

## Acceptance proof

Run:

```bash
pytest tests/test_final_edge_readiness_report.py -q
```

Recommended regression:

```bash
pytest tests/test_live_pilot_risk_throttle.py tests/test_final_edge_readiness_report.py -q
```

Focused coverage includes:

- clean EDGE-96 evidence passes final readiness
- absent throttle evidence blocks
- blocked throttle evidence blocks
- non-review candidate blocks
- deterministic candidate ordering
- payloads keep read-only boundary fields explicit

## Follow-up

EDGE-97 completes the current EDGE readiness roadmap block. Do not start new roadmap work after this PR unless explicitly requested.
