# Agent Review Evidence — LIVE-TRUTH-27 Kill Fallback Execution in LIVE

## Agent Work Contract

### Goal

Make fallback-driven candidates impossible to execute in LIVE. Fallback candidates may remain visible for debug/watchlist/advisory use, but must never become `ENTER`/executable in LIVE.

### Files changed

- `core/_engine_phase2_adapter_base.py`
- `core/runtime_safety_boot_guard.py`
- `tests/test_phase2_live_fallback_disabled.py`
- `docs/agent_reviews/live_truth_27_kill_fallback_execution_in_live.md`

### Evidence Contract Fields

mode: LIVE
candidate_id: LIVE_TRUTH_27_KILL_FALLBACK_EXECUTION_IN_LIVE
message_decision: PHASE2_LIVE_FALLBACK_EXECUTION_DISABLED
decision: PHASE2_LIVE_FALLBACK_EXECUTION_DISABLED
reason: LIVE startup is now blocked when Phase2 forced fallback execution flags are enabled, and Phase2 is prevented from selecting fallback-driven candidates as executable in LIVE.
timestamp: 2026-05-29T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/live_truth_27_kill_fallback_execution_in_live.md

### Non-goals

- No broker calls.
- No live orders.
- No ranking/scoring weight changes.
- No dashboard/UI changes.

## Grill Me Review

### Pushback

Forced fallback execution is a high-risk escape hatch. In LIVE, this is indistinguishable from “trade degraded/synthetic data”, which is unacceptable.

### Required proof

- LIVE mode cannot start with forced fallback flags enabled.
- LIVE candidates marked synthetic/fallback/unknown quote source cannot become `ENTER`/executable even when scoring above enter threshold.
- PAPER/SIM behavior remains configurable.

## Hermes Review

### Contract clarity

LIVE is a strict execution mode boundary: any candidate requiring Phase2 forced fallback is downgraded to WATCHLIST/non-executable, and unsafe config switches fail closed at startup.

### Safety boundary

The implementation only affects Phase2 decisioning output state and the runtime boot guard. It does not place/modify/cancel orders or call broker APIs.

## GSD Review

### Minimality

- Adds a narrow live-only fallback detection in `run_engine_phase2(...)` so `ENTER` is blocked for fallback-driven candidates in LIVE.
- Extends `core/runtime_safety_boot_guard.py` to treat Phase2 forced fallback flags as fatal in LIVE.
- Adds deterministic tests for both behaviors.

### Determinism

All checks are pure/deterministic over config + candidate payload.

## QA / Safety Review

Tests assert:

- `EXECUTION_MODE=LIVE` with either `PHASE2_FORCE_FALLBACK_EXECUTION_ENABLE` or `PHASE2_FORCE_FALLBACK_ALLOW_LIVE` enabled => boot safety decision is not allowed.
- LIVE candidate marked `synthetic_candidate=True` cannot produce `ENTER` even with high score.

## High-Risk Path Review

High-risk modules touched:

- `core/runtime_safety_boot_guard.py` (startup safety boundary)
- `core/_engine_phase2_adapter_base.py` (Phase2 decision path)

Safety review notes:

- LIVE mode behavior is tightened only (fail-closed).
- PAPER/SIM behavior is unchanged unless `EXECUTION_MODE` is LIVE/REAL.

## Scope Guard

Confirmed not touched:

- Broker adapters.
- Order execution paths.
- Strategy generation.
- Ranking weights / scoring configuration defaults.
- UI/dashboard.

## Acceptance Proof

Run:

```bash
python -m py_compile core/_engine_phase2_adapter_base.py core/runtime_safety_boot_guard.py
PYTHONPATH=. python -m pytest -q tests/test_phase2_live_fallback_disabled.py
PYTHONPATH=. python -m pytest -q tests/test_engine_phase2_adapter.py
```

Expected:

- Boot safety fails closed in LIVE when forced fallback flags are enabled.
- Phase2 does not return `ENTER` for fallback-driven candidates in LIVE.

## Runtime Proof Required After Merge

Before any live session:

- Run with `EXECUTION_MODE=LIVE` and confirm startup fails if either `PHASE2_FORCE_FALLBACK_EXECUTION_ENABLE=true` or `PHASE2_FORCE_FALLBACK_ALLOW_LIVE=true` is set.

During a live observation window:

- Confirm candidates with fallback/synthetic/unknown quote source appear only as WATCHLIST/ADVISORY/QUEUE_ONLY and never as `ENTER`/executable.

## What This PR Does Not Prove

- It does not prove quote correctness, feed correctness, or indicator readiness.
- It does not prove end-to-end order safety (explicitly out of scope).

## Human Approval

Merge only if:

- CI is green.
- Review confirms LIVE behavior is strictly more conservative (no new executable paths).
