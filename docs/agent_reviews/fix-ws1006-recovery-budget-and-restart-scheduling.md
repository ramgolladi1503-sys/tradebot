# Agent Review: WS1006 Recovery Budget and Scheduling

**Branch:** `fix/ws1006-recovery-budget-and-restart-scheduling`
**Author:** Tradebot Autonomous Agent (GSD)

- mode: PAPER
- candidate_id: PR-4-ws1006-budget
- decision: ACCEPT
- reason: Improved recovery from WS 1006 disconnects via configuration and guarded restarts.
- timestamp: 2026-06-11
- is_order_action: false
- broker_api_called: false
- source: gsd_agent

## Agent Work Contract
This PR addresses PR 4 of the Feed Stability Roadmap. It ensures WS1006 disconnections are correctly budgeted and automatically schedule a guarded full restart when soft resubscribe fails, rather than leaving the system silently degraded.

## Scope Guard
- `config/config.py`: Explicitly set `DEPTH_WS_WS1006_RECOVERABLE_MAX_ATTEMPTS_PER_SESSION` to 3.
- `core/kite_depth_ws.py`: Updated fallback from 2 to 3. Added `_schedule_restart_depth_ws` call when `soft_ok` is false during `_ws1006_recoverable`.
- `tests/test_kite_depth_restart.py`: Modified mock assertions to expect scheduling attempts on soft resubscribe failures.
- NO changes to order placement, strategy risk boundaries, or feed gates.
- `ALLOW_LIVE_ORDERS` and `MANUAL_APPROVAL_REQUIRED` remain intact.

## High-Risk Path Review
The `core/kite_depth_ws.py` logic changes the automatic recovery path for disconnected WebSockets. Escalating from a soft-reconnect failure directly to a guarded full restart is a state change, but relies entirely on existing `_schedule_restart_depth_ws` which respects the rate limits and reactor locks.

## Grill Me Review
No new systemic risk introduced. A failed soft resubscribe now correctly alerts the restart coordinator rather than looping or sleeping. The configuration bump gives standard market noise a slightly higher tolerance without hiding true failures.

## Hermes Review
Architectural boundaries were respected. No changes to the orchestrator layer. Only feed health and configuration were touched.

## GSD Review
I implemented the restart scheduling explicitly as directed, routing through the existing guarded methods. Local tests were updated to verify the correct number of scheduling requests occur during mock disconnections.

## QA / Safety Review
* Feed gates remain active.
* Restart cooldowns, velocity limits, and reactor locks are respected.

## Acceptance Proof
`test_kite_depth_restart.py` passes completely with the updated assertions proving `_schedule_restart_depth_ws` is called appropriately when the soft reconnect returns false.

## Runtime Proof Required After Merge
The production logs must demonstrate a graceful restart attempt when `FEED_WS_1006_RECOVERY_SOFT_RECONNECT_FAILED` is logged, and the feed successfully recovers within the cooldown/velocity boundaries.

## What This PR Does Not Prove
It does not prove that Kite WS disconnects (1006) are fully resolved or prevented.

## Human Approval
Requires explicit human review before merge, per standard project protocol.
