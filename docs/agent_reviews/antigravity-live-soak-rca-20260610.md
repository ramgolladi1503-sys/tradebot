# AntiGravity Live Soak RCA - 2026-06-10

## Failure Event Timeline (IST)

1. **13:58:44**: `main.py` is started as a background process.
2. **13:59:02**: First cycle executes. Warmup is pending for indicators. High latency (critical path takes 18.6s) immediately triggers a `LATENCY_BREACH`, placing the latency guard into `COOLDOWN` and `DEGRADE_EXIT_ONLY` modes.
3. **14:01:20**: The client starts the WebSocket connection factory for `KiteTicker`.
4. **14:01:44**: The connection to the peer is aborted uncleanly due to `WebSocket closing handshake timeout`.
5. **14:02:08**: The client watchdog detects the connection drop and triggers `restart_depth_ws` (full restart path). This shuts down the old `KiteTicker` instance and spawns a new thread to run `kws.connect(threaded=True)`.
6. **14:02:08 - 14:02:59**: Each reconnection attempt raises a fatal `twisted.internet.error.ReactorNotRestartable` exception because the global Twisted reactor cannot be restarted in the same process once stopped.
7. **14:03:05**: The rapid succession of 5 reconnection crashes trips the `feed_restart_storm` breaker, placing the system into `HARD_HALT`.
8. **14:03:09 onwards**: All cycles continue to run but are vetoed with reason `risk_halt`.

---

## Technical Root Cause Analysis

### 1. The Core Issue: Twisted Reactor Lifecycle Mismanagement
The `KiteTicker` library from Kite Connect uses the Twisted framework under the hood. When `kws.connect(threaded=True)` is called, it initializes the Twisted reactor and runs it in a background thread.
When the connection drops or a full restart is requested:
- The system calls `stop_depth_ws()`, which shuts down and stops the old ticker instance (`_KITE_TICKER.close()` / `stop()`).
- In `KiteTicker`, closing/disconnecting stops the global Twisted reactor via `reactor.stop()`.
- Once a Twisted reactor is stopped, it enters a terminated state. Due to Twisted's design, **a stopped reactor cannot be restarted** within the same Python process.
- Subsequent calls to `kws.connect(threaded=True)` try to call `reactor.run(installSignalHandlers=False)` which throws the fatal `ReactorNotRestartable` exception.

### 2. Cascading Failure: Reconnect Storm Breaker
Because `ReactorNotRestartable` is thrown on connection, the startup process immediately fails. The feed stability watchdog/coordinator detects that the feed is down and repeatedly triggers a restart.
This creates a tight loop of failed restarts:
- Reconnect 1 (Thread-5) -> ReactorNotRestartable
- Reconnect 2 (Thread-7) -> ReactorNotRestartable
- Reconnect 3 (Thread-9) -> ReactorNotRestartable
- Reconnect 4 (Thread-11) -> ReactorNotRestartable
- Reconnect 5 (Thread-13) -> ReactorNotRestartable
These 5 rapid restart attempts within a few seconds trip the `feed_restart_storm` breaker check in `restart_depth_ws` (which limits restarts to `FEED_MAX_FULL_RESTARTS_PER_HOUR`), resulting in a `HARD_HALT` risk halt.

### 3. Startup Latency Breach
During the first cycle, the loop critical path took **18.6s**. This triggered a latency breach because:
- The repository detected that `trade_log.jsonl` was missing/empty.
- The `AutoRetrain` / `self.research.run()` initialization routine ran synchronously within the main execution thread instead of running asynchronously or being pre-warmed.
- This blocked the cycle thread, triggering the latency SLO guard.
