# Agent Review — EDGE-93 Strategy Replay Proof Pack

## Agent Work Contract

Build EDGE-93 as a narrow, deterministic strategy replay proof-pack PR after EDGE-92. The work must remain read-only and must not start EDGE-94.

## Scope Guard

In scope: `core/strategy_replay_proof_pack.py`, focused tests, docs, this review file, and TODO sequencing.

Out of scope: UI changes, runtime wiring, strategy changes, ranking changes, allocation changes, broker behavior, execution behavior, and EDGE-94 acceptance suite work.

Files changed: `core/strategy_replay_proof_pack.py`, `tests/test_strategy_replay_proof_pack.py`, `docs/EDGE_93_STRATEGY_REPLAY_PROOF_PACK.md`, `docs/agent_reviews/EDGE_93_STRATEGY_REPLAY_PROOF_PACK.md`, and `docs/EDGE_TODO.md`.

Files not touched: runtime entrypoints, dashboard files, strategy providers, ranking modules, execution modules, broker modules, and websocket lifecycle code.

## Grill Me Review

Assumption under review: a strategy replay proof pack could become fake precision if it invents new replay semantics.

Mitigation: EDGE-93 reuses existing replay builders instead of creating a parallel regime, session-path, feed-health, ranking, or execution model.

Failure mode: an empty proof pack could be reported as success.

Mitigation: empty strategy replay inputs fail closed with `NO_STRATEGY_REPLAY_INPUTS`.

Deferred proof: this PR does not prove final edge, profitability, execution readiness, or paper/live readiness. It only aggregates existing replay evidence by strategy.

Verdict: proceed as read-only proof-pack evidence only.

## Hermes Review

Scope pass/fail: PASS.

Boundary violations: none expected.

The new module avoids runtime, dashboard, strategy provider, ranking mutation, execution, broker, and websocket lifecycle imports.

Public contracts:

- `StrategyReplayProofSummary`
- `StrategyReplayProofPack`
- `build_strategy_replay_proof_pack(...)`

Verdict: PASS if CI confirms changed-path scope and tests.

## GSD Review

Purpose: add deterministic strategy replay proof-pack summaries after EDGE-92.

Scope: replay evidence aggregation only.

Files changed: listed in Scope Guard.

Tests required: focused tests are included.

Evidence command: `pytest tests/test_strategy_replay_proof_pack.py -q`.

Regression command: `pytest tests/test_edge_91_regime_replay_scenarios.py tests/test_replay_session_path.py tests/test_feed_fault_replay_scenarios.py tests/test_strategy_replay_proof_pack.py -q`.

Risks: future PRs may misuse this proof pack as ranking or final readiness. EDGE-93 explicitly does not rank, select, execute, or wire runtime.

Next PR: EDGE-94 End-to-End Edge Acceptance Suite only after EDGE-93 is merged green.

## QA / Safety Review

Focused tests cover successful aggregation across all three replay layers, feed-fault block propagation, invalid session-path fail-closed behavior, deterministic grouping across multiple strategies, empty input fail-closed behavior, and read-only payload fields.

Required non-action proof: `is_order_action=false`, `broker_api_called=false`, `live_order_action=false`, `broker_order_action=false`.

## Acceptance Proof

Run:

```bash
pytest tests/test_strategy_replay_proof_pack.py -q
pytest tests/test_edge_91_regime_replay_scenarios.py tests/test_replay_session_path.py tests/test_feed_fault_replay_scenarios.py tests/test_strategy_replay_proof_pack.py -q
```

Expected: all focused and replay regression tests pass.

Evidence auditor fields:

- mode: PAPER
- candidate_id: EDGE-93-STRATEGY-REPLAY-PROOF-PACK
- decision: STRATEGY_REPLAY_PROOF_PACK_EVIDENCE_ONLY
- reason: READ_ONLY_STRATEGY_REPLAY_PROOF_PACK
- timestamp: 2026-05-28T04:45:00Z
- is_order_action: false
- broker_api_called: false
- source: docs/agent_reviews/EDGE_93_STRATEGY_REPLAY_PROOF_PACK.md

## Runtime Proof Required After Merge

No runtime proof is required because EDGE-93 is not wired into runtime behavior.

Future consumers must provide separate integration proof before consuming the proof pack in runtime, dashboard, ranking, paper, or live readiness gates.

## What This PR Does Not Prove

This PR does not prove strategy edge, profitability, final ranking quality, execution readiness, feed recovery, dashboard behavior, or paper/live readiness.

It only proves deterministic aggregation of existing replay evidence into strategy-level proof summaries.

## Human Approval

Human review is required before merge because EDGE-93 sits directly before the EDGE-94 end-to-end acceptance suite.

## High-Risk Path Review

high-risk path review: this PR touches `core/`. The new core file is read-only replay evidence aggregation and avoids runtime, dashboard, strategy provider, ranking mutation, execution, broker, and websocket lifecycle imports.
