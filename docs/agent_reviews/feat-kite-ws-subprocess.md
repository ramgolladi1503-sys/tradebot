# PR Review: Feed Subprocess Isolation (MOD-1)

## 1. What changed?
Migrated the `kite_depth_ws` connection lifecycle out of the main orchestrator thread and into a dedicated `multiprocessing.Process` supervised by a new module `core/kite_ws_subprocess.py`.

*   **Subprocess Spawning:** `core/kite_ws_subprocess.py` encapsulates `start_depth_ws` in a child process, with the main `Orchestrator` calling `start_depth_ws_subprocess()`.
*   **Health Monitoring:** The `Orchestrator.live_monitoring` loop invokes `monitor_depth_ws_subprocess()`, which monitors the `feed_runtime_latest.json` written by the subprocess.
*   **Graceful Recovery via Process Death:** Replaced the in-process stop-and-start cycle inside `restart_depth_ws` with an `os._exit(1)`. When the child process exits or writes `process_restart_required=True`, the orchestrator immediately respawns a clean subprocess.

## 2. Why does this move safety/stability/readiness forward?
This solves **RC-1 (`ReactorNotRestartable`)** and **RC-9 (Permanent Fatal State)** entirely.
Because `KiteTicker` relies on the Twisted reactor (which cannot be restarted in the same Python process), previous in-process restarts of the WebSocket caused a permanent fatal error during market hours. By completely isolating the WebSocket connection in its own process, every restart gets a fresh Twisted reactor, allowing infinite, stable recoveries from 1006 connection drops or stale feeds. 

## 3. What did not change?
*   **NO BROKER EXECUTION:** The child process only reads ticks and maintains the WebSocket. It does not load or evaluate the Phase2 execution engine.
*   `ALLOW_LIVE_ORDERS` and `MANUAL_APPROVAL_REQUIRED` gates remain untouched.
*   The SQLite schema and tick writing mechanism is untouched. The child process writes ticks identically to how the background thread did.
*   `feed_ok` and downstream feed health truth gates remain fully intact.

## 4. What tests prove it?
*   All tests in `tests/test_kite_depth_ws_stability.py` pass cleanly.
*   Existing unit tests targeting `restart_depth_ws` now accurately verify that the `process_restart_required` flag is set and that `os._exit()` triggers correctly, allowing the parent supervisor to catch it.

## 5. What could still fail?
*   If the system runs out of file descriptors or memory, `multiprocessing.Process` spawning could fail.
*   If Kite's API goes down completely, the subprocess will continuously spawn and exit, which is rate-limited to once every 15 seconds by the supervisor cooldown.
