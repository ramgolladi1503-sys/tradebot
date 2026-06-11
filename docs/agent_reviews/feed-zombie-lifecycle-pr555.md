# PR #555 Feed Zombie Lifecycle Evidence

## Scope

This PR fixes a live feed lifecycle failure where the main orchestrator could exit while background workers or websocket subprocesses remained alive.

The observed failure mode was:

- main orchestrator exits or crashes
- reconciliation workers remain alive
- websocket subprocess remains alive
- runtime locks remain active
- next live run can enter RECOVERY_BLOCKED

## Files Intentionally Changed

Production lifecycle files:

- main.py
- core/order_reconciliation_daemon.py
- core/broker_truth_reconciler.py
- core/kite_ws_subprocess.py

Test contract files:

- tests/test_kite_auth_consistency.py
- tests/test_kite_depth_restart.py
- tests/test_on_connect_forces_subscribe.py
- tests/test_orchestrator_depth_ws_startup.py

## Fix Summary

1. main.py restores default Unix SIGPIPE behavior so broken stdout or pipe consumers terminate cleanly.
2. Reconciliation daemon and broker truth reconciler are tied to main process lifecycle.
3. Kite websocket subprocess is tied to parent lifecycle so it does not survive orchestrator shutdown.

## Explicit Non-Scope

This PR does not change:

- strategy logic
- ranking logic
- UI behavior
- broker order placement
- risk engine thresholds
- live order enablement
- feed subscription semantics
- KiteTicker auth behavior

Earlier accidental reconnection/subscription changes were removed from this PR.

## Local Validation

Focused feed/auth/startup/subscription suite:

- 60 passed

Lifecycle/recovery/runtime subset:

- 24 passed

## Risk Assessment

Primary risk:

- daemonized workers can terminate abruptly with the main process.

Mitigation:

- This is safer than leaving orphaned workers and stale locks alive.
- This PR is lifecycle-only and does not alter broker execution or trading behavior.
- Live trading remains guarded by existing manual/live-order controls.

## Acceptance Criteria

- No orphaned feed subprocess after main process exit.
- No reconciliation worker keeping process alive after orchestrator exit.
- No stale lock caused by zombie process after clean stop.
- Next startup can reach runtime_state=RUNNING.
- Tests listed above pass.
