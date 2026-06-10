# Agent Review: Restart Storm Breaker Velocity Window

**Branch:** `fix/feed-restart-storm-velocity-window`
**Author:** Tradebot Autonomous Agent (GSD)

- mode: PAPER
- candidate_id: PR-3-storm-breaker
- decision: ACCEPT
- reason: Implemented velocity window for restart storm trip
- timestamp: 2026-06-11
- is_order_action: false
- broker_api_called: false
- source: gsd_agent

## Agent Work Contract
This PR addresses PR 3 of the Feed Stability Roadmap. It refactors the restart storm breaker to use a true velocity window (4 restarts within 5 minutes) rather than sharing the 1-hour cap counter, preventing permanently tripped breakers under normal load while still failing closed on tight spin-loops.

## Scope Guard
- `config/config.py`: Added `FEED_RESTART_STORM_WINDOW_SEC` with default `300.0` and updated `FEED_RESTART_STORM_TRIP` to `4`.
- `core/kite_depth_ws.py`: Filtered `_FULL_RESTARTS` array for storm trip logic down to `FEED_RESTART_STORM_WINDOW_SEC`.
- `tests/test_kite_depth_restart.py`: Added explicit velocity window and rate limit test cases.
- NO order, broker, or strategy changes.
- NO feed gates weakened; fallback executable remains false.

## High-Risk Path Review
The `core/kite_depth_ws.py` logic is critical to feed health. Modifying the restart array filtering is technically high risk, but tests confirm we accurately bounded it using the explicit velocity window. Configuration changes have a safe fallback default.

## Grill Me Review
The breaker logic was separated successfully. No hidden risk is introduced. If a feed loop occurs quickly, it still fails closed correctly after 4 rapid restarts. The hourly rate limit was also explicitly preserved.

## Hermes Review
Architectural boundaries were respected. No changes to the orchestrator layer. Only feed health and configuration were touched.

## GSD Review
I updated the exact code lines and appended the explicitly requested tests. Local tests prove that the hourly cap and the new 5-minute velocity window operate independently and safely.

## QA / Safety Review
* Feed gates remain active.
* Hourly limits are preserved.
* Test suite validates exactly the 6-in-an-hour and 4-in-5-minutes boundaries.

## Acceptance Proof
`test_kite_depth_restart.py` passes the new `test_storm_breaker_trips_on_velocity`, `test_storm_breaker_allows_restarts_over_long_window`, and `test_hourly_cap_rate_limits_safely` confirming exact behavior.

## Runtime Proof Required After Merge
The production logs must demonstrate successful execution with normal daily reconnects not tripping the storm breaker, up to the maximum hourly limit.

## What This PR Does Not Prove
It does not prove that Kite WS disconnects (1006) are fully resolved. It just prevents the system from permanently breaking early under normal reconnect volume.

## Human Approval
Requires explicit human review before merge, per standard project protocol.
