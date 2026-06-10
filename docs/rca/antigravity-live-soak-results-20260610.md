# AntiGravity Live Soak Results - 2026-06-10

## Soak Run Status & Verdict

**Verdict**: **FAIL**

### Reasons for Verdict
1. **Feed Instability**: The Kite ticker WebSocket connection failed to remain healthy. It was dropped uncleanly within 3 minutes of establishing the connection.
2. **Terminal Recovery Block**: Upon connection drop, the recovery mechanism attempted to restart the WebSocket ticker in-process, which triggered a fatal `twisted.internet.error.ReactorNotRestartable` exception.
3. **Breaker Tripped (HARD_HALT)**: The repeating crash loop of the reconnect handler triggered the `feed_restart_storm` circuit breaker within 5 minutes, placing the system into a permanent `HARD_HALT` state.
4. **Target Window Not Met**: The goal of a 120-minute soak with at least 60 continuous healthy feed minutes was not achieved.

---

## Phase 4 Metrics & Findings

* **Total Runtime Minutes**: ~9 minutes (13:58:44 to 14:07:39 IST)
* **Longest Continuous Healthy Feed Window**: **24 seconds** (The WebSocket client factory started at 14:01:20 IST and connection dropped at 14:01:44 IST; before this, the system was performing startup initialization and awaiting connection).
* **Number of Reconnects**: 5 attempts (All failed with `ReactorNotRestartable` errors on threads 5, 7, 9, 11, and 13).
* **Number of Resubscribe Proofs**: 0
* **DEPTH_STALE Count**: 2 (incidents)
* **LTP_STALE Count**: 2 (incidents) / 2 (reject reasons)
* **OPTION_TICKS_UNVERIFIED Count**: 0 (No option ticks were verified or evaluated because the feed went down immediately).
* **WARMUP_INCOMPLETE Count**: 0 rejects (Warmup warnings were raised at the readiness gate layer, but the feed failed before candidates could be processed and rejected for warmup).
* **Latency Guard Cooldown Count**: 11 rejects (`latency_guard_cooldown`: 3, `latency_guard_degrade_exit_only`: 8)
* **Recovered Fallback Count**: 0
* **Fallback Executable Count**: 0 (Fallback remained non-executable, satisfying safety guarantees).
* **Candidate Pool Count**: 2 unique candidates seen during the brief active window.
* **True Ranking Count**: 4 cycles evaluated candidate decisions before the halt.
* **Persisted Top Opportunity Snapshot Count**: 0 (No top opportunity snapshots were saved).
* **Whether Any Live Order Path Appeared**: **No** (Strictly blocked by safety gates: `LIVE_TRADING_ENABLED=false` and `ALLOW_LIVE_ORDERS=0`).
* **Whether Manual Approval Was Enforced**: **Yes** (`MANUAL_APPROVAL_REQUIRED=1`).
* **Whether Fallback Remained Non-Executable**: **Yes** (`fallback_executable = 0`).

---

## Telemetry Evidence Snapshot Location

All telemetry files containing logs, incidents, and decisions generated during this soak test have been copied to:
`file:///Users/madhuram/.gemini/antigravity/brain/a9d80830-a851-4aa0-959f-699d7a8f9d24/soak_telemetry/`
- `incidents.jsonl`
- `decisions.jsonl`
- `reject_reasons.jsonl`
- `task-228.log` (Under `.system_generated/tasks/` in appDataDir)
