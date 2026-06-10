# AntiGravity to Codex Live Soak Handoff - 2026-06-10

## Handoff Context

This document hands over the live soak test results, root cause analysis, and proposed fixes to the next agent (Codex) for implementation.

---

## Soak Summary
* **Branch**: `obs/antigravity-live-soak-20260610`
* **Soak Verdict**: **FAIL**
* **Primary Blocker**: The Kite ticker WebSocket connection dropped uncleanly after 24 seconds, and the reconnect logic raised a fatal `twisted.internet.error.ReactorNotRestartable` exception. This resulted in a restart storm that triggered the `feed_restart_storm` circuit breaker and placed the bot in a permanent `HARD_HALT`.

---

## Action Items for Codex

### 1. Fix the WebSocket reconnect reactor crash
- **Goal**: Allow the system to recover from a WebSocket drop without crashing the global Twisted reactor.
- **Reference Files**:
  - [core/kite_depth_ws.py](file:///Users/madhuram/tradebot/core/kite_depth_ws.py)
  - [core/feed_recovery_coordinator.py](file:///Users/madhuram/tradebot/core/feed_recovery_coordinator.py)
- **Path**: Either transition to utilizing `KiteTicker`'s built-in `auto_reconnect=True` (which manages reconnection without stopping the reactor), or move WebSocket feed handling into a separate worker subprocess.

### 2. Fix the Startup Latency Breach
- **Goal**: Ensure the first loop cycle executes quickly and doesn't trigger latency SLO breaches.
- **Reference Files**:
  - [core/orchestrator.py](file:///Users/madhuram/tradebot/core/orchestrator.py)
  - [core/latency_guard.py](file:///Users/madhuram/tradebot/core/latency_guard.py)
- **Path**: Shift heavy initialization processes (such as retraining and pre-warming indicators) out of the cycle critical loop and run them asynchronously.

### 3. Adjust SENSEX Stale Threshold
- **Goal**: Prevent false positive `LTP_STALE` rejections for SENSEX candidates.
- **Reference Files**:
  - [config/config.py](file:///Users/madhuram/tradebot/config/config.py)
  - [core/kite_depth_ws.py](file:///Users/madhuram/tradebot/core/kite_depth_ws.py)
- **Path**: Calibrate index tick stale boundaries specifically for SENSEX.

---

## Preserved Telemetry Evidence
All logs, incidents, and decisions generated during the soak are copied to:
`file:///Users/madhuram/.gemini/antigravity/brain/a9d80830-a851-4aa0-959f-699d7a8f9d24/soak_telemetry/`
- `incidents.jsonl`
- `decisions.jsonl`
- `reject_reasons.jsonl`
- `task-228.log` (Task log)
