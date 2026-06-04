# WS1006 Reactor Terminal State Guard

## Agent Work Contract
source_agent: Codex
action: fix
title: WS1006 reactor terminal state guard and ranked runtime evidence
scope: Normalize terminal reactor-restart state to fail closed, preserve ranked pipeline runtime evidence, and keep live-state snapshots consistent.
requested_paths:
- core/kite_depth_ws.py
- core/feed/runtime_store.py
- core/orchestrator.py
- tests/test_kite_depth_restart.py
- tests/test_feed_runtime_states.py
- tests/test_kite_depth_ws_stability.py
allowed_paths:
- core/kite_depth_ws.py
- core/feed/runtime_store.py
- core/orchestrator.py
- tests/test_kite_depth_restart.py
- tests/test_feed_runtime_states.py
- tests/test_kite_depth_ws_stability.py
forbidden_paths:
- core/broker*
- core/order*
- strategies/
- dashboard/
- run_live.sh
- config/
expected_tests:
- PYTHONPATH=. pytest -q tests/test_kite_depth_restart.py tests/test_feed_runtime_states.py tests/test_kite_depth_ws_stability.py tests/test_ranked_pipeline_runtime_evidence_wiring.py
- PYTHONPATH=. pytest -q tests
- python scripts/validate_agent_review_evidence.py
- git diff --check
- PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/ws1006_terminal_guard_changed_paths.txt
acceptance_proof:
- Terminal reactor-not-restartable state is written as RECOVERY_BLOCKED.
- Restart scheduling paths do not spawn new in-process reactor threads once terminal blocking is active.
- Ranked pipeline runtime evidence still emits during live cycles.

## Scope Guard

### In Scope
- Terminal websocket recovery state normalization.
- Runtime evidence normalization for reactor-not-restartable handling.
- Test coverage for restart blocking and feed snapshot persistence.
- Ranked pipeline runtime evidence emission.

### Out of Scope
- Strategy logic.
- Ranking math.
- Phase2 candidate selection.
- Broker/order behavior.
- UI changes.
- Threshold tuning.

### Boundary Verification
- [x] No broker calls.
- [x] No live runtime execution.
- [x] No auto-fix.
- [x] No auto-PR.
- [x] No external agent automation.

## Grill Me Review

### Challenge
Could the terminal reactor flag accidentally suppress legitimate recovery after a clean process restart?

### Weaknesses Found
- The guard is intentionally fail-closed and requires an explicit process/session reset to clear terminal reactor state.
- Test fixtures must reset the new reactor-terminal boolean or they will leak state between tests.

### Verdict
PASS

## Hermes Review

### Scope Check
- [x] No unrelated behavior changed.
- [x] No broker calls introduced.
- [x] No live behavior introduced.
- [x] No dashboard behavior introduced.
- [x] No target runtime execution.
- [x] `UNKNOWN` is not treated as safe.

### Verdict
PASS

## GSD Review

### Delivery Check
- [x] Purpose is clear.
- [x] Scope is narrow.
- [x] Evidence exists.
- [x] Tests exist.
- [x] Report output exists for the ranked pipeline writer.
- [x] Next action is clear.

### Verdict
PASS

## High-Risk Path Review

High-risk file changed: `/Users/madhuram/tradebot/core/kite_depth_ws.py`.

Review outcome:
- Change is narrowly scoped to terminal WS1006 recovery handling.
- No broker/order/execution/risk/strategy modules were modified.
- The fix keeps fail-closed behavior and only suppresses in-process restart storms once the terminal reactor state is observed.

Residual risk:
- Any runtime-state normalization can affect live evidence. That is intentional here and is covered by focused restart/feed/state tests plus the full suite.

## QA / Safety Review

Non-negotiables reaffirmed:
- No broker/order code touched.
- No live-order behavior changed.
- No gate threshold weakened.
- No fake candidates created.
- No candidate gate bypass added.

Evidence/runtime safety flags preserved:
- `read_only=true`
- `append=false`
- `is_order_action=false`
- `broker_api_called=false`

## Acceptance Proof

### Root Cause

The reactor-terminal flag was not being reset in test fixtures, and live snapshots could still be written with a mixed in-process state unless the reactor terminal path was normalized to a single blocked terminal state.

### Exact Fix

- In `/Users/madhuram/tradebot/core/kite_depth_ws.py`, terminal reactor-not-restartable state now normalizes to a single blocked lifecycle reason and suppresses further in-process restart scheduling.
- In `/Users/madhuram/tradebot/core/feed/runtime_store.py`, terminal reactor recovery snapshots are canonicalized to `RECOVERY_BLOCKED` with explicit restart-required metadata.
- In the tests, the reactor-terminal flag is reset between cases so unrelated restart paths are not poisoned.

### Commands Run

```bash
PYTHONPATH=. pytest -q tests/test_kite_depth_restart.py::test_start_depth_ws_marks_reactor_not_restartable_as_recovery_blocked tests/test_kite_depth_restart.py::test_schedule_restart_depth_ws_suppresses_when_reactor_blocked tests/test_kite_depth_restart.py::test_recovery_blocked_snapshot_contains_process_restart_required tests/test_kite_depth_restart.py::test_restart_depth_ws_stops_retrying_when_reactor_recovery_is_blocked tests/test_kite_depth_restart.py::test_reactor_terminal_state_blocks_followup_start_restart_and_schedule tests/test_feed_runtime_states.py::test_write_feed_runtime_snapshot_includes_reconnect_blocked_reason tests/test_feed_runtime_states.py::test_persist_runtime_snapshot_row_normalizes_ws1006_recovery_blocked_state
PYTHONPATH=. pytest -q tests/test_kite_depth_restart.py tests/test_feed_runtime_states.py tests/test_kite_depth_ws_stability.py tests/test_ranked_pipeline_runtime_evidence_wiring.py
PYTHONPATH=. pytest -q tests
python scripts/validate_agent_review_evidence.py
git diff --check
PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/ws1006_terminal_guard_changed_paths.txt
```

### Reports / Files Produced
- `logs/feed_runtime_latest.json`
- `logs/ranked_pipeline_runtime_latest.json`
- `logs/ranked_pipeline_runtime_2026-06-04.jsonl`

## Runtime Proof Required After Merge

- Live audit should show `runtime_state=RECOVERY_BLOCKED` for terminal reactor states.
- Live audit should show `reactor_not_restartable_detected=true` and `recovery_action=process_restart_required`.
- Live audit should continue writing ranked pipeline runtime evidence during candidate cycles.

## What This PR Does Not Prove

- It does not prove the exchange feed itself is healthy.
- It does not prove strategy quality or ranking quality.
- It does not prove Phase2 candidate sufficiency.
- It does not prove broker or order execution safety beyond read-only evidence paths.

## Human Approval

Required before merge:
- confirm the blocker normalization is correct
- confirm the fix does not hide real reactor failures
- confirm post-merge live validation is reviewed by a human

## Evidence

mode: LIVE_AUDIT
candidate_id: ws1006_reactor_terminal_state_guard
decision: RECOVERY_BLOCKED_NORMALIZED
reason: Terminal reactor-not-restartable state is normalized to a single blocked lifecycle state and suppresses in-process restart storms.
timestamp: 2026-06-04
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/ws1006_reactor_terminal_state_guard.md
