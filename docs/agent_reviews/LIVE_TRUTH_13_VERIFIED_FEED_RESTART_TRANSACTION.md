# Agent Review — LIVE-TRUTH-13 Verified Feed Restart Transaction

## Evidence Contract Fields
- mode: LIVE-TRUTH
- candidate_id: LIVE-TRUTH-13-VERIFIED-FEED-RESTART
- source: docs/agent_reviews/LIVE_TRUTH_13_VERIFIED_FEED_RESTART_TRANSACTION.md
- reason: verified feed restart transaction prevents false restart success after websocket 1006
- timestamp: 2026-05-29T07:25:00Z
- decision: APPROVED_FOR_CI
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false

## Agent Work Contract
- PR: #433 / LIVE-TRUTH-13
- Issue: #431
- Scope: make feed restart after WebSocket 1006 transactional and evidence-backed.
- Allowed files: core/kite_depth_ws.py, tests/test_kite_depth_restart.py, docs/LIVE_TRUTH_13_VERIFIED_FEED_RESTART_TRANSACTION.md, docs/agent_reviews/LIVE_TRUTH_13_VERIFIED_FEED_RESTART_TRANSACTION.md
- Forbidden behavior: no broker calls, no order behavior, no candidate generation changes, no ranking changes, no strategy changes, no dashboard/UI changes, no latency threshold tuning.

## Scope Guard
Verdict: PASS
This PR only changes feed restart lifecycle handling and restart evidence. It does not touch candidate generation, ranking, strategies, execution, or dashboard behavior.

## Grill Me Review
Verdict: PASS
Could this hide restart failure? No. Failed replacement start returns false, writes RESTART_FAILED evidence, and does not emit FEED_FULL_RESTART_OK.
Could this place or modify orders? No. The patch only touches feed lifecycle and tests.

## Hermes Review
Verdict: PASS
start_depth_ws now returns an explicit boolean handoff result.
restart_depth_ws treats full restart as a transaction.
_STOP_REQUESTED is cleared before replacement start.
_RESTART_LOCK uses RLock because restart evidence can safely query restart count while restart logic owns the lock.

## GSD Review
Verdict: PASS
Added deterministic tests for failed start after stop.
Added deterministic tests for successful handoff evidence.
Local focused test passed: tests/test_kite_depth_restart.py.

## QA / Safety Review
Test command: python -m py_compile core/kite_depth_ws.py && PYTHONPATH=. python -m pytest -q tests/test_kite_depth_restart.py
Observed local result: 21 passed in 34.02s.
Safety result: no broker calls, no order behavior, no live order action, feed failure remains fail-closed.

## High-Risk Path Review
Verdict: PASS
Required because core/kite_depth_ws.py is a feed/WebSocket runtime path.
Risks checked: false restart success, stale _STOP_REQUESTED manual-stop latch, restart evidence deadlock.
Mitigation: failed start returns false and writes RESTART_FAILED; false FEED_FULL_RESTART_OK is blocked; _STOP_REQUESTED is cleared; _RESTART_LOCK is re-entrant.

## Acceptance Proof
1. restart_depth_ws does not return true when replacement start fails.
2. RESTARTING evidence is written before stopping old feed.
3. RESTART_FAILED evidence is written when start fails after stop.
4. FEED_FULL_RESTART_OK is not emitted for failed replacement start.
5. _STOP_REQUESTED is cleared before replacement start.
6. Focused restart tests pass.

## Runtime Proof Required After Merge
Next live proof: grep FEED_FULL_RESTART, RESTARTING, RESTART_FAILED, and restart_depth_ws in depth WebSocket logs after any future WebSocket 1006.
Expected proof: either replacement feed reaches start requested / connected / ticks, or restart failure is explicit as RESTART_FAILED. No silent process-alive/feed-dead false success.

## What This PR Does Not Prove
1. It does not prove Kite will not disconnect again.
2. It does not prove candidate quality or ranking edge.
3. It does not prove terminal runtime-health stale evidence is fixed; that is #432.
4. It does not prove live market profitability.
5. It does not change broker/order behavior.

## Human Approval
Approved by: Ram after CI passes.
Human merge condition: Agent Review Evidence Gate green, Code Excellence Gates green, tests/ci green, and no untracked runtime artifacts committed.
