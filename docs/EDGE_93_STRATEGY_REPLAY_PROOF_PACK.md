# EDGE-93 — Strategy Replay Proof Pack

## Purpose

EDGE-93 adds a deterministic, read-only Strategy Replay Proof Pack that combines the replay evidence layers built in:

- EDGE-91 — Regime Replay Scenarios
- EDGE-91A — Session Path Replay Analytics
- EDGE-92 — Feed Fault Replay Scenarios

The goal is to produce strategy-level proof summaries from existing replay evidence without changing ranking, strategies, execution, broker behavior, runtime behavior, or dashboard behavior.

## Scope

This PR adds:

- `core/strategy_replay_proof_pack.py`
- `tests/test_strategy_replay_proof_pack.py`
- this documentation
- agent-review evidence
- TODO sequencing update

## Design

`build_strategy_replay_proof_pack(...)` is a thin aggregation layer.

It reuses existing builders:

- `build_regime_replay_report(...)`
- `build_session_path_replay_report(...)`
- `build_feed_fault_replay_report(...)`

It does not create a parallel regime model, session-path model, feed-health model, ranking model, or execution model.

## Output contract

The proof pack emits:

- top-level proof-pack status
- strategy count
- passed/blocked strategy counts
- candidate counts
- valid/invalid candidate counts
- feed-blocked count
- combined reasons
- raw component reports
- deterministic strategy summaries

All payloads preserve read-only/non-action flags:

- `read_only=True`
- `append=False`
- `is_order_action=False`
- `broker_api_called=False`
- `live_order_action=False`
- `broker_order_action=False`

## Strategy summary behavior

Strategy summaries are grouped by `strategy` metadata from session-path and feed-fault evidence.

A strategy is blocked when any of these are true:

- regime replay is not passed
- session-path replay is not passed
- feed-fault replay is not passed
- any session evidence row is invalid
- any feed-fault evidence row is invalid
- any feed-fault evidence says the scenario should block

The pack fails closed when no strategy replay inputs are provided.

## Boundaries

EDGE-93 does not:

- rank candidates
- select strategies
- change strategy behavior
- change execution behavior
- call brokers
- place, modify, cancel, or exit orders
- wire runtime loops
- write runtime artifacts
- wire dashboard/UI
- start EDGE-94

## Acceptance proof

Run:

```bash
pytest tests/test_strategy_replay_proof_pack.py -q
pytest tests/test_edge_91_regime_replay_scenarios.py tests/test_replay_session_path.py tests/test_feed_fault_replay_scenarios.py tests/test_strategy_replay_proof_pack.py -q
```

Focused coverage includes:

- successful proof-pack aggregation across all three replay layers
- feed-fault blocking without hiding actual fault type
- invalid session-path fail-closed behavior
- deterministic multi-strategy grouping
- empty-input fail-closed behavior
- read-only/non-action payload flags

## Follow-up

After EDGE-93 is merged green, continue to PR #319 — EDGE-94 End-to-End Edge Acceptance Suite.
