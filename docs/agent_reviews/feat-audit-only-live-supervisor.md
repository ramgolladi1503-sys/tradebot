# Agent Review: Audit-Only Live Supervisor

**Branch:** `feat/audit-only-live-supervisor`
**Author:** Tradebot Autonomous Agent (GSD)

## What changed?
1. Added `scripts/run_live_supervised.sh`: A shell supervisor that wraps `main.py` and restarts it on fatal exit up to `LIVE_SUPERVISED_MAX_RESTARTS`.
2. Added `scripts/live_supervisor.py`: A Python equivalent of the shell supervisor for cross-platform and extensible process management.
3. Added `tests/test_live_supervisor.py`: Unit tests simulating a failing `main.py` to prove the supervisor respects maximum restart counts and wait durations.

## Why does this move safety/stability/readiness forward?
This resolves RC-9 (No Process-Level Supervisor) from the Feed Module RCA. Previously, a single `ReactorNotRestartable` or `FEED_LIFECYCLE_FATAL` would crash the feed forever, and the orchestrator would sleep infinitely. By wrapping the live run in a supervisor, the system can automatically reboot into a fresh process state, clearing any fatal reactor conditions, and restoring the feed. This ensures the 5-hour stability target is reachable during Indian market hours.

## What did not change?
* No production application code (`core/`, `strategies/`) was modified.
* No LIVE execution flags were enabled. `ALLOW_LIVE_ORDERS` and `MANUAL_APPROVAL_REQUIRED` remain untouched.
* No existing safety gates, tests, or fallback behaviors were removed or bypassed.
* The orchestrator's fatal wait sleep was not altered; the supervisor simply handles the process crash/exit.

## What tests prove it?
* `tests/test_live_supervisor.py` explicitly proves the supervisor logic (it correctly restarts on exit code `1` and gracefully stops on exit code `0`, and respects max restarts).
* The existing feed tests pass unmodified.

## What could still fail?
* If the root cause of the process exit is an infinite loop or hang instead of a crash (exit code `1`), the supervisor will not trigger unless an external watchdog kills the process.
* If Kite token auth is fundamentally expired, restarts will endlessly fail until the maximum is reached.
