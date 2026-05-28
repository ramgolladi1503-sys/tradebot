# TEST-STAB-04 Agent Review Evidence

Issue: #364
Parent: #361
Blocked roadmap: #319 / EDGE-98

## Scope
WebSocket restart compatibility only.

## Baseline failures

- `tests/test_kite_depth_ws_stability.py::test_fatal_on_error_schedules_async_forced_full_restart`
- `tests/test_kite_depth_ws_stability.py::test_fatal_on_close_schedules_async_forced_full_restart`
- `tests/test_kite_depth_ws_stability.py::test_network_error_restarts_without_auth_required`
- `tests/test_kite_depth_ws_stability.py::test_network_error_forces_full_restart_when_enabled`
- `tests/test_on_connect_forces_subscribe.py::test_on_connect_forces_subscribe`

## Required proof before closing

- focused websocket tests pass
- compileall passes
- full suite status reported in #361

## Safety boundary

- no broker calls
- no live order behavior
- no auth weakening
