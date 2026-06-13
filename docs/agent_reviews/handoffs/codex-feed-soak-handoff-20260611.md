# Codex Feed Soak Handoff 2026-06-11

This handoff preserves the feed soak evidence and current state after the constructor compatibility fix.

## Proven

- `core/auth.py` now passes reconnect kwargs only when the KiteTicker constructor supports them.
- `tests/test_kite_depth_ws_stability.py` is back in sync with the current WS1006 behavior.
- `tests/test_feed_recovery_runtime.py`, `tests/test_kite_depth_ws_stability.py`, and `tests/test_live_supervisor.py` pass in the focused run.
- `tests/test_feed_runtime_states.py`, `tests/test_runtime_health.py`, `tests/test_orchestrator_pilot_feed_ok.py`, and `tests/test_orchestrator_latency_accounting.py` pass.

## Not Proven

- 90-minute soak stability.
- Single-source-of-truth WS1006 ownership across every branch.
- Candidate starvation root cause is still mixed: feed truth is unhealthy and the latency guard is tripped.

## Evidence Locations

- `/Users/madhuram/tradebot/.runtime/logs/feed_runtime_latest.json`
- `/Users/madhuram/tradebot/.runtime/logs/candidate_flow_trace_latest.json`
- `/Users/madhuram/tradebot/.runtime/logs/desks/DEFAULT/candidates.jsonl`

