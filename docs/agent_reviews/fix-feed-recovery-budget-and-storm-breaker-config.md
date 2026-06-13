# Agent Review: Feed Recovery Budget and Storm Breaker Configuration

**Branch:** `fix/feed-recovery-budget-3`
**Author:** Tradebot Autonomous Agent (GSD)

- mode: PAPER
- candidate_id: PR-MOD2-MOD3-config
- decision: ACCEPT
- reason: Implemented correct default configurations for feed recovery and storm breakers as identified in the feed stability RCA.
- timestamp: 2026-06-11
- is_order_action: false
- broker_api_called: false
- source: gsd_agent

## Agent Work Contract
This PR addresses the configuration gaps for MOD-2 and MOD-3 of the Feed Stability Roadmap. It adjusts `config/config.py` default settings so the codebase properly limits high-frequency restart storms (4 restarts within 5 minutes) independently from the 1-hour cap limit (12), and sets sensible fallback defaults for WS 1006 reconnect escalation.

## Scope Guard
- `config/config.py`: Updated `FEED_FULL_RESTART_COOLDOWN_SEC` to `30.0`, `FEED_MAX_FULL_RESTARTS_PER_HOUR` to `12`, `DEPTH_WS_RECOVERY_WINDOW_SEC` to `3600.0`, `DEPTH_WS_WS1006_RECOVERABLE_MAX_ATTEMPTS_PER_SESSION` to `10`, and added `DEPTH_WS_WS1006_RECOVERABLE_RETRY_COOLDOWN_SEC` as `5.0`.
- NO order, broker, or strategy changes.
- NO feed gates weakened; fallback executable remains false.

## High-Risk Path Review
Modifying default environment variables in `config/config.py` is high risk because it dictates the bounds for process restarts and reconnect attempts during market hours. The bounds (4/5m, 12/1h) are well within Kite API limits and safely protect against tight restart loops, while giving the websocket more budget to naturally reconnect without forcing full restarts under mild load.

## Grill Me Review
No new systemic risk introduced. By properly parameterizing the defaults, we prevent the system from getting permanently blocked (DEGRADED) on early morning 1006 disconnects. The explicit velocity window guarantees we still fail-closed quickly if a spin-loop develops.

## Hermes Review
Architectural boundaries were respected. No changes to the orchestrator layer. Only feed configuration defaults were touched. The underlying logic in `core/kite_depth_ws.py` was previously established to respect these constants.

## GSD Review
I implemented the exact configuration changes specified in the RCA roadmap. I also verified that local tests execute cleanly and `run_unified_ce_gates.py` passes the CI evidence gate.

## QA / Safety Review
* Feed gates remain active.
* Restart limits remain correctly scoped to their respective sliding windows.
* The test suite successfully passes against these new defaults via pytest.

## Acceptance Proof
- `pytest -q tests/test_kite_depth_ws_stability.py` passes cleanly.
- `pytest -q tests/test_feed_recovery_runtime.py tests/test_feed_runtime_states.py tests/test_runtime_health.py` passes safely.
- No regression in logic bounds.

## Runtime Proof Required After Merge
The production logs must demonstrate successful execution with normal daily reconnects utilizing the larger WS1006 retry budget without hitting the storm breaker incorrectly.

## What This PR Does Not Prove
It does not prove that Kite WS disconnects (1006) are fully resolved or that a new class of websocket faults won't appear. It only tunes the system's resilience to expected instability.

## Human Approval
Requires explicit human review before merge, per standard project protocol.
