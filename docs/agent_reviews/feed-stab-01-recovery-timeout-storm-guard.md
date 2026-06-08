# FEED-STAB-01 — Real Feed Recovery Timeout & Storm Guard

## Agent Work Contract

### Source Agent

```text
source_agent: Codex
action: GENERATE_PATCH (feed recovery timing, timeout, storm-guard, and fail-closed auth handling)
title: FEED-STAB-01 — Real Feed Recovery Timeout & Storm Guard
scope: Harden websocket feed recovery with real time, timeout, storm-guard, and fail-closed auth handling.
requested_paths:
  - config/config.py
  - core/feed_recovery_coordinator.py
  - core/kite_depth_ws.py
  - tests/test_feed_recovery_coordinator.py
  - tests/test_kite_depth_ws_stability.py
  - docs/agent_reviews/feed-stab-01-recovery-timeout-storm-guard.md
allowed_paths:
  - config/config.py
  - core/feed_recovery_coordinator.py
  - core/kite_depth_ws.py
  - tests/test_feed_recovery_coordinator.py
  - tests/test_kite_depth_ws_stability.py
  - docs/agent_reviews/feed-stab-01-recovery-timeout-storm-guard.md
forbidden_paths:
  - strategies/*
  - core/order*
  - core/broker*
  - dashboard/*
  - credentials.py
  - .env
expected_tests:
  - python -m pytest tests/test_feed_recovery_coordinator.py tests/test_kite_depth_ws_stability.py -q
acceptance_proof:
  - WS1006 starts soft recovery with a real timestamp.
  - Recovery clears when option verification succeeds.
  - Recovery times out after the configured window.
  - Three recoveries inside the configured window block further recovery.
  - Auth failures fail closed and do not enter a reconnect loop.
  - Terminal reactor failures remain restart-required.
```

## High-Risk Path Review

This PR touches high-risk feed and config paths, so the review stays narrow and explicit.

- `config/config.py`: added conservative recovery defaults only.
- `core/feed_recovery_coordinator.py`: added explicit recovery timing and blocking state.
- `core/kite_depth_ws.py`: translated coordinator outcomes into fail-closed runtime evidence.

No broker, order, strategy, ranking, or dashboard code was modified.

## Scope Guard

This PR is intentionally narrow and only changes feed recovery timing and fail-closed handling.

### In Scope

- Make feed recovery use a real clock or injected test clock.
- Add timeout and storm-guard state to the recovery coordinator.
- Fail closed on auth-required and terminal restart-required faults.
- Wire the websocket handler to respect the new recovery outcomes.
- Add focused recovery tests.

### Out of Scope

- No strategy changes.
- No ranking or scoring changes.
- No broker order changes.
- No dashboard/UI changes.
- No live-mode changes.
- No credential changes.

## Grill Me Review

The main risk is loosening recovery gating while trying to make it more observable. This PR avoids that by blocking on timeout, auth-required, and recovery-storm conditions instead of retrying indefinitely.

The second risk is silently changing existing feed behavior. The new outcomes are explicit, and the tests pin the fail-closed paths rather than relaxing them.

The third risk is broadening into strategy or broker logic. This PR does not touch those paths.

## Hermes Review

The architecture stays constrained to the recovery coordinator and websocket callback integration.

The coordinator now owns the timing state and recovery-window logic, while `core/kite_depth_ws.py` only translates those outcomes into runtime snapshots and logs.

## GSD Review

This PR turns recovery from a static or best-effort loop into an explicit state machine with time-bound outcomes.

That makes recovery behavior observable, reproducible in tests, and safe to gate future candidate generation on.

## QA / Safety Review

Safety properties covered:

- Recovery timestamps come from the injected or real clock.
- Recovery loops cannot run forever without timing out.
- Recovery storms are blocked inside the configured window.
- Auth-required faults fail closed and do not reconnect.
- Terminal reactor faults remain restart-required.
- Candidate generation stays blocked whenever recovery is active, timed out, blocked, auth-required, or restart-required.

## Acceptance Proof

Focused commands:

```bash
python -m pytest tests/test_feed_recovery_coordinator.py tests/test_kite_depth_ws_stability.py -q
```

Expected proof:

- WS1006 enters soft recovery with a non-fake timestamp.
- Successful recovery clears the state.
- Timeouts flip recovery into a blocked state.
- Three recovery failures in the configured window block further recovery.
- Auth failures emit auth-required evidence and do not loop reconnects.
- Terminal reactor failures remain restart-required.

## Runtime Proof Required After Merge

No runtime proof is required to validate broker/order behavior because this PR does not touch broker APIs, orders, or strategy execution.

Runtime proof is still required for the websocket feed path after merge:

- confirm recovery timeout evidence appears in runtime snapshots
- confirm recovery-blocked evidence prevents candidate generation
- confirm auth-required latching suppresses reconnect loops

## What This PR Does Not Prove

This PR does not prove feed quality or trading edge.

It does not prove ranking quality.

It does not prove candidate profitability.

It does not prove strategy correctness.

It only proves feed recovery timing and blocking behavior are explicit, bounded, and fail closed.

## Human Approval

Human approval is required before merge.

Do not merge this PR only because the tests are green. Review that the recovery state machine stayed narrow and that no strategy, ranking, or broker behavior changed.

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
