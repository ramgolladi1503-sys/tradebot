# Fix WS Recovery Blocked Lifecycle No Silent Dead State

mode: REVIEW
candidate_id: PR-FIX-WS-RECOVERY-BLOCKED-LIFECYCLE-NO-SILENT-DEAD-STATE
decision: add_read_only_ws_lifecycle_evidence
reason: Live audits showed WS lifecycle faults could leave the bot in a mixed or silent-dead state after disconnects and reactor-terminal failures. This PR keeps recovery evidence explicit, preserves fail-closed behavior, and ensures restart attempts, blocked states, and recovery metadata remain observable and consistent.
timestamp: 2026-06-04T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/fix-ws-recovery-blocked-lifecycle-no-silent-dead-state.md

Status: DRAFT (do not merge without explicit human approval)

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (WS lifecycle evidence + deterministic recovery-state tests)
title: Fix WS recovery blocked lifecycle no silent dead state
scope: make WS disconnect, restart attempt, and recovery-blocked evidence explicit and consistent without changing strategy, ranking, broker, or UI behavior
requested_paths:
  - core/kite_depth_ws.py
  - tests/test_kite_depth_restart.py
  - tests/test_kite_depth_ws_stability.py
  - tests/test_feed_runtime_states.py
  - docs/agent_reviews/fix-ws-recovery-blocked-lifecycle-no-silent-dead-state.md
allowed_paths:
  - core/kite_depth_ws.py
  - tests/test_kite_depth_restart.py
  - tests/test_kite_depth_ws_stability.py
  - tests/test_feed_runtime_states.py
  - docs/agent_reviews/*
forbidden_paths:
  - core/broker*
  - core/order*
  - core/execution*
  - core/risk*
  - strategies/*
  - config/*
  - dashboard/*
  - run_live.sh
expected_tests:
  - WS restart/recovery unit tests
  - feed runtime state tests
  - runtime execution truth tests
  - agent review evidence validator
  - unified CE gates
acceptance_proof:
  - reactor-terminal recovery remains fail-closed and explicit
  - ordinary WS error handling can still schedule recovery without silently hiding the disconnect
  - runtime snapshots preserve disconnect and restart evidence
  - flags: read_only=true, append=false, is_order_action=false, broker_api_called=false, live_order_allowed=false
```

## Purpose

Live audits exposed a mismatch between websocket error handling and the emitted runtime evidence: ordinary disconnects, reactor-terminal failures, and follow-up snapshots could lose the disconnect/restart context or imply a clean session when one did not exist. This PR keeps recovery behavior observable and avoids silent dead states.

## Files Changed

- `/Users/madhuram/tradebot/core/kite_depth_ws.py`
  - Distinguishes ordinary disconnect/restart paths from reactor-terminal blocked paths.
  - Preserves disconnect metadata across later runtime snapshots.
  - Ensures blocked vs restartable lifecycle states stay explicit in evidence.
- `/Users/madhuram/tradebot/tests/test_kite_depth_restart.py`
  - Verifies restart scheduling, reactor-terminal blocking, and snapshot preservation.
- `/Users/madhuram/tradebot/tests/test_kite_depth_ws_stability.py`
  - Verifies 1006/close/error handling, restart evidence, and non-terminal restart paths.
- `/Users/madhuram/tradebot/tests/test_feed_runtime_states.py`
  - Verifies runtime feed snapshots keep the recovery-blocked evidence contract.
- `/Users/madhuram/tradebot/docs/agent_reviews/fix-ws-recovery-blocked-lifecycle-no-silent-dead-state.md`
  - Documents the narrow scope and the acceptance proof.

## High-Risk Path Review

High-risk file changed: `/Users/madhuram/tradebot/core/kite_depth_ws.py`.

Review outcome:
- The change is limited to websocket lifecycle handling and evidence persistence.
- It does not touch broker/order execution, strategy logic, ranking math, Phase2, or UI.
- It preserves fail-closed behavior for reactor-terminal recovery blocking.
- It keeps disconnect/restart metadata observable rather than silently dropping it.

Residual risk:
- Websocket lifecycle code remains high-risk because external reconnect behavior is inherently timing-sensitive.
- If the runtime emits additional later snapshots during recovery, the preserved disconnect context must remain consistent with the latest session state.

## Scope Guard

### In Scope

- Ordinary WS disconnect handling
- Reactor-terminal recovery blocking
- Restart attempt evidence
- Runtime snapshot preservation
- Deterministic tests for lifecycle and evidence behavior

### Out of Scope

- Broker/order code
- Strategy formulas and thresholds
- Ranking and Phase2 behavior
- Dashboard/UI work
- Live-order behavior

### Boundary Verification

- [x] No broker calls added
- [x] No order actions added
- [x] No gate bypass added
- [x] No candidate counts are faked
- [x] No strategy behavior changed
- [x] No threshold changes

## Grill Me Review

### Risks Addressed

- Reactor-terminal recovery remains explicit and blocked.
- Ordinary WS disconnects can still be retried without losing evidence.
- Later snapshots preserve disconnect and restart context instead of silently resetting it.

### Verdict

PASS — narrow lifecycle/evidence fix with explicit fail-closed state handling.

## Hermes Review

### Contract / Architecture Check

- [x] Evidence schema is explicit and observable.
- [x] Runtime snapshots preserve disconnect/restart metadata.
- [x] Reactor-terminal blocked state remains explicit.
- [x] Failure path is fail-closed.

### Verdict

PASS

## GSD Review

### Delivery Check

- [x] Tests prove restartable disconnects, terminal block states, and preserved evidence.
- [x] No runtime behavior outside websocket lifecycle handling changed.

### Verdict

PASS

## QA / Safety Review

Non-negotiables reaffirmed:
- No broker/order code touched.
- No live-order behavior changed.
- No feed, indicator, regime, or strategy predicate gate bypass added.
- No strategy formula or threshold changed.
- No ranking or Phase2 behavior changed.

Evidence/runtime safety flags preserved:
- `read_only=true`
- `append=false`
- `is_order_action=false`
- `broker_api_called=false`
- `live_order_allowed=false`

## Acceptance Proof

### Evidence Contract

The artifacts include:
- disconnect code/reason fields
- restart attempt fields
- recovery-blocked fields
- reactor-terminal block fields
- non-silent follow-up snapshot preservation

### Commands Run

```bash
PYTHONPATH=. python -m pytest -q tests/test_kite_depth_restart.py tests/test_kite_depth_ws_stability.py tests/test_feed_runtime_states.py tests/test_runtime_execution_truth_evidence.py
python scripts/validate_agent_review_evidence.py
git diff --check
PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/ws_recovery_lifecycle_changed_paths.txt
```

## Runtime Proof Required After Merge

Required next live validation:
- run an observation-only live session
- confirm ordinary disconnects either recover or fail explicitly without silent dead states
- confirm reactor-terminal failures remain blocked and observable
- confirm later runtime snapshots still preserve the disconnect/restart context

## What This PR Does Not Prove

- This PR does not change strategy logic, ranking math, Phase2 selection, broker/order behavior, or UI.
- This PR does not prove improved trading performance.
- This PR does not authorize live trading or any order action.

## Human Approval

This PR remains draft-only until a human explicitly approves the websocket lifecycle change and confirms the live-audit evidence is acceptable for merge.
