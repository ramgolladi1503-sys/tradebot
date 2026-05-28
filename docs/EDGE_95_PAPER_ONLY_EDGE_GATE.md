# EDGE-95 — Paper-Only Edge Gate

## Purpose

EDGE-95 adds a deterministic paper-only gate that consumes EDGE-94 end-to-end acceptance evidence and blocks anything that is not explicitly PAPER-safe.

This is not a live-trading gate. It is a read-only paper eligibility proof.

## Scope

This PR adds:

- `core/paper_only_edge_gate.py`
- `tests/test_paper_only_edge_gate.py`
- this documentation
- agent-review evidence
- TODO sequencing update

## Inputs

The gate consumes EDGE-94 acceptance evidence from `build_end_to_end_edge_acceptance_report(...)` or a compatible payload.

Required conditions for a candidate to be paper-allowed:

- mode is explicitly `PAPER`
- EDGE-94 report status is `EDGE_ACCEPTANCE_SUITE_PASSED`
- candidate status is accepted
- candidate accepted flag is true
- no action/broker boundary flags are present

## Fail-closed behavior

The gate blocks when:

- EDGE-94 evidence is missing
- mode is absent, blank, SIM, LIVE, or anything other than PAPER
- EDGE-94 status is blocked
- candidate is not accepted
- no accepted candidate exists
- evidence contains action or broker boundary flags

## Output contract

The gate emits:

- top-level paper gate status
- normalized mode
- candidate count
- paper allowed/blocked counts
- top-level reasons
- per-candidate paper decisions

Payloads preserve read-only/non-action fields:

- `read_only=True`
- `append=False`
- `is_order_action=False`
- `broker_api_called=False`
- `live_order_action=False`
- `broker_order_action=False`

## Boundaries

EDGE-95 does not:

- call brokers
- create live actions
- rank candidates
- generate candidates
- change strategies
- change execution behavior
- wire runtime loops
- write runtime artifacts
- wire dashboard/UI
- start EDGE-96

## Acceptance proof

Run:

```bash
pytest tests/test_paper_only_edge_gate.py -q
```

Recommended regression:

```bash
pytest tests/test_end_to_end_edge_acceptance_suite.py tests/test_paper_only_edge_gate.py -q
```

Focused coverage includes:

- explicit PAPER + accepted EDGE-94 evidence passes
- missing EDGE-94 evidence blocks
- SIM mode blocks
- blocked EDGE-94 evidence blocks
- rejected candidate blocks
- deterministic candidate ordering
- boundary-flag evidence blocks without introducing broker behavior

## Follow-up

After EDGE-95 is merged green, continue to PR #321 — EDGE-96 Live-Pilot Risk Throttle.
