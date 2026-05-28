# EDGE-94 — End-to-End Edge Acceptance Suite

## Purpose

EDGE-94 adds a deterministic, read-only End-to-End Edge Acceptance Suite that proves the edge proof chain can accept a good candidate and reject unsafe or weak candidates without changing runtime, ranking, strategies, execution, brokers, or dashboard behavior.

This is not a live-trading gate. It is a proof suite.

## Scope

This PR adds:

- `core/end_to_end_edge_acceptance_suite.py`
- `tests/test_end_to_end_edge_acceptance_suite.py`
- this documentation
- agent-review evidence
- TODO sequencing update

## Existing evidence chain reused

The suite consumes already-built evidence payloads/reports for:

- candidate intent / candidate pool contracts
- strategy candidate generator evidence
- option-chain confirmation evidence
- exit model evidence
- conflict / consensus evidence
- NoTradeOracle evidence
- final executable trade quality gate evidence
- EDGE-93 strategy replay proof pack evidence

EDGE-94 does not create a new strategy model, replay model, ranking model, broker adapter, execution model, dashboard model, or runtime loop.

## Acceptance behavior

A candidate is accepted only when all required proof checks pass:

- candidate intent evidence is present and passing
- candidate pool evidence is present and passing
- strategy generator evidence is present and passing
- option-chain confirmation evidence is present and passing
- exit model evidence is present and passing
- conflict / consensus evidence is present and passing
- NoTradeOracle evidence is present and not blocking
- final executable trade quality gate evidence is present and passing
- replay proof-pack evidence is present and passing

A candidate is rejected when any required proof check is missing, invalid, blocked, rejected, failed, unsafe, or not executable.

## Output contract

The suite emits:

- top-level suite status
- candidate count
- accepted/rejected candidate counts
- suite-level reasons
- per-candidate acceptance evidence
- deterministic stage summaries

Payloads preserve read-only/non-action flags:

- `read_only=True`
- `append=False`
- `is_order_action=False`
- `broker_api_called=False`
- `live_order_action=False`
- `broker_order_action=False`

## Boundaries

EDGE-94 does not:

- rank candidates
- generate candidates
- change candidate generation
- change strategies
- change option-chain confirmation
- change exit models
- change conflict/consensus logic
- change NoTradeOracle logic
- change final executable gate logic
- call brokers
- place, modify, cancel, or exit orders
- wire runtime loops
- write runtime artifacts
- wire dashboard/UI
- start EDGE-95

## Acceptance proof

Run:

```bash
pytest tests/test_end_to_end_edge_acceptance_suite.py -q
```

Recommended replay/proof regression:

```bash
pytest tests/test_strategy_replay_proof_pack.py tests/test_end_to_end_edge_acceptance_suite.py -q
```

Focused coverage includes:

- all-stage pass accepts a candidate
- missing required stage fails closed
- NoTradeOracle block rejects the candidate
- final quality gate rejection rejects the candidate
- replay proof-pack block rejects the candidate
- multi-candidate reports stay deterministic
- read-only/non-action payload flags remain false for order/broker actions

## Follow-up

After EDGE-94 is merged green, continue to PR #320 — EDGE-95 Paper-Only Edge Gate.
