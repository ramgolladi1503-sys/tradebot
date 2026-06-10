# AG Live Feed Stability Experiment Fixes (2026-06-10)

## Codebase Changes Summary

### 1. WebSocket Lifecycle Hardening
- **File**: [core/kite_depth_ws.py](file:///Users/madhuram/tradebot/core/kite_depth_ws.py)
- **Change**: Pre-empts Twisted reactor reconnect loops by checking startup state, marks state as `FEED_LIFECYCLE_FATAL` on terminal errors, and triggers explicit logs (`ws_started`, `ws_connected`, `ws_disconnected`, `ws_reconnect_attempt`, `ws_reconnect_success`, `ws_reconnect_failed`).

### 2. Defensive CPU Spin Protection
- **File**: [core/orchestrator.py](file:///Users/madhuram/tradebot/core/orchestrator.py)
- **Change**: Added defensive `time.sleep(max(2.0, self.poll_interval))` at the top of the monitoring cycle if the feed goes fatal to avoid hot-looping CPU.

### 3. Strict Feed Health Validation
- **File**: [core/feed_health_truth.py](file:///Users/madhuram/tradebot/core/feed_health_truth.py)
- **Change**: Enforced strict requirements: option token count > 0, option/depth age < threshold, and LTP age check.

### 4. Phase2 Firewall Enforcement
- **File**: [core/engine_phase2_adapter.py](file:///Users/madhuram/tradebot/core/engine_phase2_adapter.py)
- **Change**: Direct candidate check which returns `[]` immediately if `feed_ok` is `False`.

### 5. Blocker State Reset & Test Mocking
- **File**: [tests/test_feed_runtime_states.py](file:///Users/madhuram/tradebot/tests/test_feed_runtime_states.py)
- **Change**: Mocks `_latest_depth_epoch_from_store` and `_latest_db_tick_epoch` inside the test scenarios to reflect fresh ticks in simulated environments, preventing tests from triggering false stale-feed overrides.

## Verified Commits & Status
All tests pass cleanly:
```bash
PYTHONPATH=. pytest -q \
  tests/test_feed_recovery_runtime.py \
  tests/test_feed_runtime_states.py \
  tests/test_orchestrator_pilot_feed_ok.py \
  tests/test_orchestrator_latency_accounting.py \
  tests/test_runtime_health.py \
  tests/behavior/test_top_opportunity_edge_behavior.py
```
**Result: 57 passed**
