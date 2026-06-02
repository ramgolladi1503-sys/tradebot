# Fix Feed ReactorNotRestartable Recovery

Status: DRAFT (do not merge without explicit human approval)

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (narrow feed recovery reliability fix + tests)
title: Fix feed ReactorNotRestartable recovery
scope: stop unsafe in-process websocket restart after Twisted reactor shutdown, preserve fail-closed stale-feed behavior, and harden evidence/runtime path handling
requested_paths:
  - core/kite_depth_ws.py
  - core/feed_debug.py
  - core/orchestrator.py
  - core/runtime_health.py
  - core/paths.py
  - tests/test_kite_depth_restart.py
  - tests/test_feed_runtime_states.py
  - tests/test_feed_debug_runtime_store.py
  - tests/test_orchestrator_reports_finally.py
allowed_paths:
  - core/kite_depth_ws.py
  - core/feed_debug.py
  - core/orchestrator.py
  - core/runtime_health.py
  - core/paths.py
  - tests/test_kite_depth_restart.py
  - tests/test_feed_runtime_states.py
  - tests/test_feed_debug_runtime_store.py
  - tests/test_orchestrator_reports_finally.py
  - docs/agent_reviews/*
forbidden_paths:
  - core/broker*
  - core/order*
  - core/execution*
  - strategies/*
  - config/*
  - dashboard/*
  - run_live.sh
expected_tests:
  - pytest feed/websocket/runtime-store/runtime-health/live-workload group
  - pytest candidate/notrade/live-workload group
  - full pytest suite
acceptance_proof:
  - ReactorNotRestartable becomes explicit blocked-recovery evidence instead of silent retry looping
  - stale feed remains fail-closed
  - feed runtime evidence carries reconnect_blocked_reason
  - live workload evidence no longer crashes on missing feature_timing
  - runtime-store path collisions fail deterministically
```

### Purpose

Fix the live-session recovery failure proven by live evidence in `.runtime/live_audit/live_stale_indicator_blocker_fix_20260602_102245`: after a websocket timeout/close, the process attempted an in-process full restart and hit `twisted.internet.error.ReactorNotRestartable`, leaving the feed stale for the rest of the session.

## Files Changed

- `/Users/madhuram/tradebot/core/kite_depth_ws.py`
  - Detect `ReactorNotRestartable`, convert it into explicit `RECOVERY_BLOCKED` runtime evidence, and block further in-process restart attempts in the same process.
- `/Users/madhuram/tradebot/core/feed_debug.py`
  - Surface `reconnect_blocked_reason` into feed-debug/runtime-health consumers.
- `/Users/madhuram/tradebot/core/orchestrator.py`
  - Initialize `feature_timing` before early-cycle branches so workload evidence writing cannot hit an unbound local.
- `/Users/madhuram/tradebot/core/runtime_health.py`
  - Include `RECOVERY_BLOCKED` runtime state and reconnect-blocked markers in health blockers.
- `/Users/madhuram/tradebot/core/paths.py`
  - Make directory-boundary creation fail deterministically when a required directory path already exists as a file.
- `/Users/madhuram/tradebot/tests/test_kite_depth_restart.py`
  - Add deterministic recovery-blocked proofs and reset process-global feed runtime state between tests.
- `/Users/madhuram/tradebot/tests/test_feed_runtime_states.py`
  - Add explicit reconnect-blocked runtime evidence proof and reset process-global feed runtime state between tests.
- `/Users/madhuram/tradebot/tests/test_feed_debug_runtime_store.py`
  - Add deterministic path-collision proof for runtime DB path resolution.
- `/Users/madhuram/tradebot/tests/test_orchestrator_reports_finally.py`
  - Retain finalizer coverage while leaving workload timing omission proof to workload-evidence tests.

## High-Risk Path Review

High-risk file changed: `/Users/madhuram/tradebot/core/kite_depth_ws.py`.

Review outcome:
- The change is confined to feed recovery/error classification and runtime evidence.
- No broker/order execution path was modified.
- No freshness gate was weakened.
- The system still fails closed when the feed is stale or recovery is blocked.

Residual risk:
- This PR does not make the feed self-heal after Twisted shutdown; it makes the failure explicit and non-looping until the process is restarted, which is the safer behavior for this architecture.

## Scope Guard

### In Scope

- Prevent repeated unsafe in-process restart attempts after reactor shutdown.
- Emit explicit feed recovery blocked evidence.
- Keep workload/runtime evidence robust on blocked cycles.
- Harden deterministic runtime DB parent-path handling.

### Out of Scope

- Broker/order code
- Live order behavior
- Strategy formulas
- Ranking/scoring
- Phase2 behavior
- Threshold tuning
- Dashboard/UI
- `run_live.sh`

### Boundary Verification

- [x] No broker calls added
- [x] No order actions added
- [x] No feed freshness gate bypass added
- [x] No strategy behavior changed
- [x] No threshold changes

## Grill Me Review

### Challenge

- Are we hiding a real reconnect bug instead of fixing it?
- Are we accidentally marking the feed healthy when it is still stale?
- Are we adding a latch that can suppress legitimate recovery?

### Findings

- The current process model launches the websocket feed as a long-lived child process, but the runtime code also attempts in-process full restart via `restart_depth_ws()`.
- Once Twisted has stopped, that in-process restart path is unsafe; retrying it is not recovery, it is repeated failure.
- The correct fail-closed behavior is to mark recovery as blocked and require process-level restart evidence.
- Feed freshness remains unhealthy; no fake recovery is emitted.

### Verdict

PASS — explicit blocked recovery is safer than repeated in-process restart attempts.

## Hermes Review

### Contract / Architecture Check

- [x] Recovery failure is explicit and observable
- [x] Process-level recovery need is recorded in evidence
- [x] No hidden fallback added
- [x] Fail-closed behavior preserved

### Verdict

PASS

## GSD Review

### Delivery Check

- [x] Runtime fix is narrow
- [x] Tests prove behavior, not only shape
- [x] Full suite passes locally
- [x] Evidence doc added for repo gates

### Verdict

PASS

## QA / Safety Review

Non-negotiables reaffirmed:
- No broker/order code touched
- No live-order behavior changed
- No feed freshness bypass added
- No strategy formulas changed
- No ranking or Phase2 behavior changed

Evidence/runtime safety flags preserved:
- `read_only=true`
- `append=false`
- `is_order_action=false`
- `broker_api_called=false`

## Acceptance Proof

### Root Cause

`core/kite_depth_ws.py` performed full restart in-process by calling `stop_depth_ws()` and then `start_depth_ws()` again in the same Python process. When a websocket close/error had already driven Twisted into a stopped reactor state, the next `kws.connect(threaded=True)` attempt failed with `ReactorNotRestartable`. The code then kept re-entering restart paths from error/close/watchdog handlers, leaving the bot permanently feed-stale.

### Exact Fix

- Detect `ReactorNotRestartable` at feed start/connect time.
- Convert that condition into explicit `RECOVERY_BLOCKED` runtime evidence with `reconnect_blocked_reason=reactor_not_restartable`.
- Block subsequent in-process restart attempts in the same process, and emit recovery-required evidence instead of silently looping.
- Preserve stale-feed fail-closed behavior.
- Initialize `feature_timing` before early cycle branches so workload evidence writing cannot crash on blocked/error paths.
- Make directory creation fail deterministically with `NotADirectoryError` when a required directory path already exists as a file.

### Commands Run

```bash
PYTHONPATH=. python -m pytest -q tests/test_kite_depth_restart.py tests/test_feed_runtime_states.py tests/test_orchestrator_reports_finally.py tests/test_feed_debug_runtime_store.py
PYTHONPATH=. python -m pytest -q tests -k "feed or websocket or runtime_store or runtime_health or live_workload"
PYTHONPATH=. python -m pytest -q tests -k "candidate_flow or notrade_reason_truth or live_workload"
PYTHONPATH=. python -m pytest -q tests
python scripts/validate_agent_review_evidence.py
PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file <generated-file>
```

## Runtime Proof Required After Merge

Required next live validation:
- run observation-only live session during market hours
- inspect:
  - `logs/feed_runtime_latest.json`
  - `logs/runtime_health_latest.json`
  - `logs/live_workload_latest.json`
  - live console output
- confirm:
  - `reconnect_blocked_reason=reactor_not_restartable` is present when the reactor path fails
  - feed remains unhealthy/fail-closed
  - no repeated in-process restart loop continues after the blocked state is entered
  - workload evidence still writes on blocked cycles

## What This PR Does Not Prove

- Does not prove websocket stability under all network failures
- Does not restart the feed from a supervisor automatically
- Does not make stale feed executable
- Does not authorize any live trading action

## Human Approval

Required before merge:
- confirm process-level restart is the intended safety posture after Twisted reactor shutdown
- confirm blocked-recovery evidence is acceptable for live operations
- confirm post-merge live validation is reviewed by a human

## Evidence (CE-10 Contract Fields)

- mode: LIVE_AUDIT
- candidate_id: feed_reactor_not_restartable_recovery
- decision: FEED_RECOVERY_BLOCKED_EXPLICITLY
- reason: In-process Twisted restart after reactor shutdown is unsafe and now fails closed with explicit evidence
- timestamp: 2026-06-02
- is_order_action: false
- broker_api_called: false
- source: docs/agent_reviews/fix-feed-reactor-not-restartable-recovery.md
