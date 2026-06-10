# AG Live Feed Stability Experiment Root Cause Analysis (2026-06-10)

## Incident Background
In previous live runs, a Twisted WS 1006 disconnect triggered attempts to reconnect. The Twisted reactor cannot be restarted once stopped, which repeatedly raised `ReactorNotRestartable` errors. This resulted in an invalid feed recovery state where the feed remained stale or untrusted, triggering latency guard halts, and causing CPU spikes while the main loop spun at high CPU.

## Root Causes Identified & Mitigations

### 1. Twisted Reactor Restart Storms
- **Root Cause**: When a WebSocket disconnected or encountered a terminal error, the shutdown logic stopped the Twisted reactor, but subsequent restart attempts tried to re-call `reactor.connectTCP` or start it again in the same process, which is unsupported by Twisted.
- **Mitigation**: Added a pre-emptive check on the reactor state before calling `kws.connect()` in `core/kite_depth_ws.py`:
  ```python
  from twisted.internet import reactor
  if getattr(reactor, "_started", False) and not getattr(reactor, "running", False):
      raise RuntimeError("ReactorNotRestartable: Twisted reactor was started and stopped")
  ```
  If this state is reached, the lifecycle transitions to `FEED_LIFECYCLE_FATAL` and stops attempting to restart, cleanly failing closed.

### 2. High CPU Spin on Feed Failure
- **Root Cause**: The orchestrator legacy monitoring loop runs at a polling rate of `0.25` seconds. When the feed went fatal or recovery blocked, the orchestrator repeatedly checked the state and processed empty candidate cycles without sleeping, causing a high-CPU hot-loop.
- **Mitigation**: Implemented a defensive sleep (`max(2.0, self.poll_interval)`) inside `_legacy_live_monitoring()` in `core/orchestrator.py` when the feed state is fatal (`FEED_LIFECYCLE_FATAL`, `RECOVERY_BLOCKED`, or `RECONNECT_BLOCKED`), preventing high CPU usage.

### 3. Weak Feed Freshness Gates & Stale Quotes
- **Root Cause**: Lack of strict, explicit option age, depth age, and LTP freshness checks allowed candidates to be processed under stale or untrusted feed data.
- **Mitigation**: Hardened `derive_feed_ok()` in `core/feed_health_truth.py` to require:
  - Fresh option ticks
  - Fresh depth age
  - Non-empty option token count
  - Non-stale underlying tick
  If any criteria fails, `feed_ok` is immediately falsified.

### 4. Phase 2 Candidate Leaks
- **Root Cause**: Even when the feed went invalid, candidates could theoretically leak into Phase 2 evaluation.
- **Mitigation**: Enforced a strict gate inside `core/engine_phase2_adapter.py` that immediately sets candidates to `[]` when `feed_ok` is `False`.
