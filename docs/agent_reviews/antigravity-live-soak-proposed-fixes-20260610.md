# AntiGravity Live Soak Proposed Fixes - 2026-06-10

For every issue identified during the soak test, the minimal proposed fixes and testing plans are outlined below.

---

### Issue 1: twisted.internet.error.ReactorNotRestartable during WebSocket Reconnection

* **Issue**: The WebSocket feed cannot recover from any network drop in-process because the Twisted reactor cannot be restarted.
* **Evidence**:
  - `twisted.internet.error.ReactorNotRestartable` tracebacks raised in threads 5, 7, 9, 11, and 13.
  - Reconnect storm incident: `{"incident_id": "inc-1781080385-HARD_HALT", "context": {"reason": "feed_restart_storm", "details": {"count": 6}}}`.
* **Impact**: Critical. Any brief network hiccup permanently halts the feed and locks the system into a risk halt.
* **Likely root cause**: The `restart_depth_ws` flow calls `stop_depth_ws` (which stops the running global reactor instance via `.close()`) and then attempts to start a new ticker instance calling `.connect(threaded=True)` (which tries to run the stopped global reactor again).
* **Files likely involved**:
  - [core/kite_depth_ws.py](file:///Users/madhuram/tradebot/core/kite_depth_ws.py)
  - [core/feed_recovery_coordinator.py](file:///Users/madhuram/tradebot/core/feed_recovery_coordinator.py)
* **Minimal proposed fix**:
  - Avoid creating a new `KiteTicker` instance on reconnection. Instead, configure `auto_reconnect=True` on `KiteTicker` so that Twisted's internal reconnect logic reconnects the existing WebSocket without stopping the running reactor.
  - If a full client reset is necessary, delegate the WebSocket feed ticker to a separate background subprocess (e.g., `depth_ws_worker.py`) that communicates with the main process via IPC/sockets. When the feed drops, the worker process can be cleanly terminated and restarted as a new process, bypassing the Twisted reactor limitation.
* **Tests to add before fix**:
  - A mock connection test in [tests/test_kite_depth_ws_stability.py](file:///Users/madhuram/tradebot/tests/test_kite_depth_ws_stability.py) that triggers a connection drop and asserts that the connection is re-established using the same reactor state.
* **Risk of fix**: High (requires careful separation of the feed process from the execution/orchestrator process).
* **Recommended PR size**: Medium/Large.
* **Do not fix now / safe to fix now**: Safe to fix now (design phase only).

---

### Issue 2: High Startup Latency triggering Latency SLO breaches

* **Issue**: The first cycle execution takes 18.6s, causing the latency guard to immediately degrade the execution mode to `DEGRADE_EXIT_ONLY`.
* **Evidence**:
  - Task log: `LATENCY_BREACH` incident with total loop duration breach.
  - Incidents log: `inc-1781080188-LATENCY_BREACH` degrading cycle mode.
* **Impact**: High. The system starts up in a degraded state, preventing normal trading entry right from cycle 2.
* **Likely root cause**: Heavy initialization checks, indicators generation, or retraining routines are executed synchronously within the critical path of the first loop cycle.
* **Files likely involved**:
  - [core/orchestrator.py](file:///Users/madhuram/tradebot/core/orchestrator.py)
  - [core/latency_guard.py](file:///Users/madhuram/tradebot/core/latency_guard.py)
* **Minimal proposed fix**:
  - Refactor initialization to run before entering the cycle loop, or run retraining and complex indicator pre-calculation in a background thread to prevent blocking the main cycle thread.
* **Tests to add before fix**:
  - Integration test measuring the duration of the first cycle on an empty database.
* **Risk of fix**: Low.
* **Recommended PR size**: Small.
* **Do not fix now / safe to fix now**: Safe to fix now.

---

### Issue 3: Persistent LTP_STALE on SENSEX Index

* **Issue**: Frequent `LTP_STALE` incidents are logged for SENSEX, triggering rejection alerts.
* **Evidence**:
  - `incidents.jsonl` contains `LTP_STALE` warnings specifically for symbol `SENSEX`.
  - Reject reasons log contains `LTP_STALE` block reasons for SENSEX candidates.
* **Impact**: Medium. Valid SENSEX candidates are rejected due to false positive stale detections.
* **Likely root cause**: SENSEX tick volume is lower off-hours or the index tick stale threshold (e.g. 1.5s) is too aggressive compared to NIFTY.
* **Files likely involved**:
  - [core/kite_depth_ws.py](file:///Users/madhuram/tradebot/core/kite_depth_ws.py)
  - [config/config.py](file:///Users/madhuram/tradebot/config/config.py)
* **Minimal proposed fix**:
  - Calibrate the stale index threshold for SENSEX from 1.5s to 3.0s or use alternative LTP sources.
* **Tests to add before fix**:
  - Feed sanity tests validating SENSEX age boundaries.
* **Risk of fix**: Low.
* **Recommended PR size**: Small.
* **Do not fix now / safe to fix now**: Safe to fix now.
