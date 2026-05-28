# EDGE-96 — Live-Pilot Risk Throttle

## Purpose

EDGE-96 adds a deterministic read-only throttle that consumes EDGE-95 paper-only gate evidence and determines whether paper-eligible candidates can enter live-pilot review.

This is not live execution. It is a non-action review eligibility proof.

## Scope

This PR adds:

- `core/live_pilot_risk_throttle.py`
- `tests/test_live_pilot_risk_throttle.py`
- this documentation
- agent-review evidence
- TODO sequencing update

## Inputs

The throttle consumes EDGE-95 paper-only gate evidence from `build_paper_only_edge_gate_report(...)` or a compatible payload.

Optional throttle controls:

- `max_candidates`
- `max_per_strategy`
- `allowed_symbols`
- `blocked_symbols`

## Required conditions

A candidate can enter live-pilot review only when:

- EDGE-95 paper gate evidence exists
- EDGE-95 status is `PAPER_EDGE_GATE_PASSED`
- EDGE-95 mode is `PAPER`
- candidate is paper-allowed
- candidate stays within max-candidate throttle
- candidate stays within per-strategy throttle
- symbol filters permit the candidate
- boundary flags remain non-action and non-broker

## Fail-closed behavior

The throttle blocks when:

- paper gate evidence is absent
- paper gate status is blocked
- mode is not PAPER
- no paper-allowed candidate exists
- candidate is not paper-allowed
- max candidate limit is exceeded
- max per-strategy limit is exceeded
- symbol is not allowed
- symbol is blocked
- throttle limits are invalid
- boundary flags are present

## Output contract

The throttle emits:

- top-level throttle status
- candidate count
- review allowed/blocked counts
- top-level reasons
- per-candidate live-pilot review decisions

Payloads preserve read-only/non-action fields:

- `read_only=True`
- `append=False`
- `is_order_action=False`
- `broker_api_called=False`
- `live_order_action=False`
- `broker_order_action=False`

## Boundaries

EDGE-96 does not:

- call brokers
- create live actions
- rank candidates
- generate candidates
- change strategies
- change execution behavior
- wire runtime loops
- write runtime artifacts
- wire dashboard/UI
- start EDGE-97

## Acceptance proof

Run:

```bash
pytest tests/test_live_pilot_risk_throttle.py -q
```

Recommended regression:

```bash
pytest tests/test_paper_only_edge_gate.py tests/test_live_pilot_risk_throttle.py -q
```

Focused coverage includes:

- paper gate pass allows one candidate for review
- absent paper gate evidence blocks
- non-PAPER mode blocks
- blocked paper gate evidence blocks
- non-paper candidate blocks
- max-candidate throttle blocks overflow
- max-per-strategy throttle blocks overflow
- symbol filters block unsafe scope
- invalid throttle limits block
- boundary-flag evidence blocks without introducing broker behavior

## Follow-up

After EDGE-96 is merged green, continue to PR #322 — EDGE-97 Final Edge Readiness Report.
