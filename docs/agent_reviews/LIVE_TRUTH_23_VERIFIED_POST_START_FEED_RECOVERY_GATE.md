# Agent Review Evidence — LIVE-TRUTH-23 Verified Post-Start Feed Recovery Gate

mode: REVIEW
candidate_id: live_truth_23_verified_post_start_feed_recovery_gate
decision: verified_post_start_feed_recovery_gate
reason: prevent_process_alive_feed_dead_after_restart
timestamp: 2026-05-29T00:00:00Z
source: docs/agent_reviews/LIVE_TRUTH_23_VERIFIED_POST_START_FEED_RECOVERY_GATE.md
read_only: true
append: false
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false

## Agent Work Contract

source_agent: GSD
action: GENERATE_PATCH
title: LIVE-TRUTH-23 — Verified Post-Start Feed Recovery Gate
scope: Enforce a post-start restart verification gate for depth WebSocket restarts so a restart is only considered recovered after connect + subscribe + fresh option tick proof.
requested_paths:
  - core/kite_depth_ws.py
  - tests/test_kite_depth_restart.py
  - docs/agent_reviews/LIVE_TRUTH_23_VERIFIED_POST_START_FEED_RECOVERY_GATE.md
allowed_paths:
  - core/kite_depth_ws.py
  - tests/test_kite_depth_restart.py
  - docs/agent_reviews/LIVE_TRUTH_23_VERIFIED_POST_START_FEED_RECOVERY_GATE.md
forbidden_paths:
  - .env
  - "*.env"
  - credentials.py
  - main.py
  - run_live.sh
  - config/
  - core/broker*
  - core/order*
  - core/execution*
  - core/risk*
  - strategies/
expected_tests:
  - python -m py_compile core/kite_depth_ws.py
  - PYTHONPATH=. python -m pytest -q tests/test_kite_depth_restart.py
  - PYTHONPATH=. python -m pytest -q tests/test_kite_depth_ws_stability.py
acceptance_proof: Verified recovery must only emit FEED_RESTART_VERIFIED_OK after connect observed post-epoch, subscribe applied post-epoch, and option tick proof is satisfied; otherwise runtime is fail-closed as RESTART_VERIFY_PENDING/FAILED.

## High-Risk Path Review

This PR changes `core/kite_depth_ws.py` (feed/WebSocket lifecycle), which is high-risk for LIVE safety.

Risk control:
- Fail-closed overlay: while restart verification is PENDING or FAILED, feed runtime snapshot reports `runtime_state=RESTART_VERIFY_PENDING` or `runtime_state=RESTART_VERIFY_FAILED`, which blocks downstream execution via existing feed truth gates.
- No broker calls: no new broker adapters, order actions, or execution wiring. Tests explicitly assert no broker client calls are made by the verification code path.
- Observability: restart verification emits explicit events (`FEED_RESTART_VERIFY_*`, `FEED_RESTART_VERIFIED_OK`, `FEED_RESTART_VERIFY_FAILED`) and writes a `restart_verification` payload into `logs/feed_runtime_latest.json`.
- Reversibility: verification is gated by config flags; disabling verification makes behavior revert to pre-LIVE-TRUTH-23 semantics without partial silent fallbacks.

## Grill Me Review

The prior gap was a false-positive recovery signal: `kws.connect(threaded=True)` returning without throwing is not market-data proof. If the socket never connects/subscribes or ticks do not arrive post-restart, the bot must not claim feed recovery.

Negative expectations:
- Start handoff success alone must not produce `FEED_RESTART_VERIFIED_OK`.
- Verification timeout must be visible and must fail closed.

## Hermes Review

Design: separate restart start-handoff (`FEED_FULL_RESTART_OK`) from restart recovery truth (`FEED_RESTART_VERIFIED_OK` / `FEED_RESTART_VERIFY_FAILED`) via a small verification state machine.

Recovery truth requires, post-restart epoch:
- connect observed
- subscribe/set_mode applied
- option subscriptions present when required
- per-symbol option ticks meet minimum thresholds
- feed blockers are clear for required symbols where possible

## GSD Review

Implementation is narrowly scoped:
- Only adds an internal verification state machine and snapshot overlay in `core/kite_depth_ws.py`.
- Adds deterministic tests in `tests/test_kite_depth_restart.py` for pending/verified/timeout and broker non-calls.
- Does not alter candidate ranking, strategy thresholds, or any broker/order behavior.

## QA / Safety Review

Safety assertions proven by tests:
- A start-handoff that "succeeds" without connect/ticks remains blocked (`runtime_state=RESTART_VERIFY_PENDING`) and does not emit `FEED_RESTART_VERIFIED_OK`.
- When connect + subscribe + fresh option tick proof exists, `FEED_RESTART_VERIFIED_OK` is emitted and runtime state is not blocked.
- Timeout emits `FEED_RESTART_VERIFY_FAILED` and blocks (`runtime_state=RESTART_VERIFY_FAILED`).
- Broker client is not called (`broker_api_called=false` enforced by a hard failing mock).

## Scope Guard

Confirmed not touched:
- Candidate ranking and selection logic.
- Broker adapters, order placement, or execution wiring.
- Strategy thresholds or strategy modules.
- Credentials and environment files.
- UI/dashboard code.

## Acceptance Proof

Run:

```bash
python -m py_compile core/kite_depth_ws.py
PYTHONPATH=. python -m pytest -q tests/test_kite_depth_restart.py
PYTHONPATH=. python -m pytest -q tests/test_kite_depth_ws_stability.py
```

Expected:
- Pending verification state blocks and is visible in `logs/feed_runtime_latest.json`.
- Verified recovery emits `FEED_RESTART_VERIFIED_OK` only after proof.
- Timeout emits `FEED_RESTART_VERIFY_FAILED` and blocks fail-closed.

## Runtime Proof Required After Merge

In a controlled PAPER/LIVE staging run (no orders):
- Force a 1006-style restart (or simulated restart path), then confirm:
  - `FEED_FULL_RESTART_OK` is logged for start handoff,
  - `FEED_RESTART_VERIFY_BEGIN` then `FEED_RESTART_VERIFY_WAITING_*` stages are logged,
  - `FEED_RESTART_VERIFIED_OK` appears only after post-restart option ticks are observed,
  - `logs/feed_runtime_latest.json` includes `restart_verification` fields and does not report RUNNING before verified OK.

## What This PR Does Not Prove

- It does not prove broker/execution correctness.
- It does not prove strategy profitability or ranking quality.
- It does not prove all symbols/options are tradable; it proves the minimal post-restart feed recovery evidence contract.
- It does not replace the existing stale-feed guard; it complements it for restart recovery truth.

## Human Approval

Approve only if:
- CI is fully green.
- The diff remains limited to the declared allowed paths.
- The verification gate remains fail-closed by default (no silent bypass).

