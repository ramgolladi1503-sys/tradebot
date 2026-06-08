# FEED-STAB-01 — Real Feed Recovery Timeout & Storm Guard

source_agent: Codex
action: generate_patch
title: FEED-STAB-01 — Real Feed Recovery Timeout & Storm Guard
scope: Harden websocket feed recovery with real time, timeout, storm-guard, and fail-closed auth handling.
requested_paths:
- `config/config.py`
- `core/feed_recovery_coordinator.py`
- `core/kite_depth_ws.py`
- `tests/test_feed_recovery_coordinator.py`
- `tests/test_kite_depth_ws_stability.py`
- `docs/agent_reviews/feed-stab-01-recovery-timeout-storm-guard.md`
allowed_paths:
- `config/config.py`
- `core/feed_recovery_coordinator.py`
- `core/kite_depth_ws.py`
- `tests/test_feed_recovery_coordinator.py`
- `tests/test_kite_depth_ws_stability.py`
- `docs/agent_reviews/feed-stab-01-recovery-timeout-storm-guard.md`
forbidden_paths:
- `strategies/`
- `core/order*`
- `core/broker*`
- `dashboard/`
- `credentials.py`
- `.env`
expected_tests:
- `python -m pytest tests/test_feed_recovery_coordinator.py tests/test_kite_depth_ws_stability.py -q`
acceptance_proof:
- `WS1006` starts soft recovery with a real timestamp.
- Recovery clears when option verification succeeds.
- Recovery times out after the configured window.
- Three recoveries inside the configured window block further recovery.
- Auth failures fail closed and do not enter a reconnect loop.
- Terminal reactor failures remain restart-required.

## Scope

This PR makes websocket feed recovery time-aware, bounded, and fail-closed.

It adds explicit recovery outcomes for soft reconnect, timeout, blocked, auth-required, and terminal restart-required cases.

## Files Changed

- `core/feed_recovery_coordinator.py`
- `core/kite_depth_ws.py`
- `config/config.py`
- `tests/test_feed_recovery_coordinator.py`
- `tests/test_kite_depth_ws_stability.py`

## Safety Guarantees

- Recovery timestamps come from a real clock or an injected deterministic clock in tests.
- Recovery loops time out instead of staying open indefinitely.
- Excess recovery attempts within the configured window are blocked.
- Auth failures fail closed and do not enter reconnect loops.
- Terminal reactor failures stay restart-required.
- Candidate gating remains blocked whenever recovery is active, timed out, blocked, auth-required, or restart-required.

## Tests Run

- `python -m pytest tests/test_feed_recovery_coordinator.py tests/test_kite_depth_ws_stability.py -q`

## Intentionally Not Touched

- `strategies/`
- ranking or scoring logic
- broker order placement
- dashboard/UI code

## Residual Risks

- The websocket module still has several intertwined runtime states, so any later recovery PRs must keep the fail-closed contract intact.
- This PR only covers the first recovery stabilization slice; later PRs still need the broader feed-stability roadmap.

## Acceptance Result

Pending until the targeted tests and validation commands complete cleanly.
