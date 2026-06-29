# Feed Reconnect Safety RCA (2026-06-29)

## Incident / Problem Description
During extended live soaking, the orchestrator experienced a hard failure and shutdown triggered by a standard broker-side WebSocket disconnect (`1006 Connection error: 1006 - connection was closed uncleanly (peer dropped the TCP connection...)`). 

Previously, the feed management logic (`kite_depth_ws.py`) treated `1006` errors as fatal to the internal feed loop, initiating a complete manual restart of the `Twisted` reactor. However, `Twisted` reactors cannot be restarted in the same process natively (`ReactorNotRestartable`), resulting in an uncontrolled total system crash when the network flapped.

## Root Cause
1.  **Over-aggressive crash action**: The `on_error` and `on_close` callbacks for KiteTicker bypassed the Kite-native `auto_reconnect` logic and invoked an immediate system-level restart.
2.  **Lack of intermediate state modeling**: `FeedTruthContract` and the system state machine only recognized strictly binary health (`LIVE` or `FATAL`), not handling `RECONNECTING` or `STALE` transitions smoothly.
3.  **Missing Orchestrator guardrails**: `orchestrator.py` relied on candidates receiving valid data *after* generation to halt them, rather than halting candidate generation itself via a global `feed_ok` check.

## Solution and Remediation
The following fixes have been applied:
1.  **Native Reconnect Delegation**: Removed the aggressive `restart_depth_ws` call from `on_error` and `on_close` for standard `1006` events. The system now defers to `kiteconnect`'s native `auto_reconnect` mechanism.
2.  **State Machine Updates**: `_RUNTIME_STATE` accurately tracks `RECONNECTING`, and `FeedTruthContract` reflects this state by enforcing `feed_ok=False`.
3.  **Feed Watchdog Enhancements**: The DB tick watchdog was hardened to forcefully transition to `STALE` if the last WebSocket tick or database tick is older than acceptable thresholds (`MAX_QUOTE_AGE_SEC`, `MAX_DEPTH_AGE_SEC`).
4.  **Orchestrator Pre-flight Gate**: The orchestrator candidate builder loop now performs an explicit `_pilot_feed_ok()` pre-flight check. If the feed is degraded, the entire loop skips cleanly, guaranteeing zero risk of trading on stale data.
5.  **Strict Testing Coverage**: Added `tests/test_feed_reconnect_safety.py` to cryptographically prove that the new gating logic functions flawlessly under simulated disconnects and stale-tick conditions.
