# LIVE-TRUTH-13 — Verified Feed Restart Transaction after WebSocket 1006

## Context
Live evidence proved WebSocket 1006 can leave main.py alive while feed remains stopped/zombie.

## Observed failure
- on_error:1006 -> SUBSCRIBE_FAILED
- on_close:1006 -> SUBSCRIBE_FAILED
- stop_depth_ws:restart:ws_error:1006 -> STOPPED
- main.py stayed alive
- runtime_health stayed FEED_ZOMBIE

## Root Cause
restart_depth_ws called stop_depth_ws and then start_depth_ws, but start_depth_ws did not return a reliable boolean result. Restart success was not tied to verified start handoff.

## What changed
- start_depth_ws now returns True or False.
- restart_depth_ws writes RESTARTING before stopping old feed.
- _STOP_REQUESTED is cleared before replacement start.
- restart_depth_ws writes RESTART_FAILED when start handoff fails.
- FEED_FULL_RESTART_OK is not emitted when replacement start returns False.

## Safety boundaries
- No broker calls.
- No order behavior.
- No candidate/ranking changes.
- No dashboard/UI changes.
- Feed failure remains fail-closed.

## Test command
python -m py_compile core/kite_depth_ws.py
PYTHONPATH=. python -m pytest -q tests/test_kite_depth_restart.py
