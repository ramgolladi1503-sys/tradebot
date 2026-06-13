import os
import re

# Update task.md
with open("/Users/madhuram/.gemini/antigravity/brain/a9d80830-a851-4aa0-959f-699d7a8f9d24/task.md", "r") as f:
    task = f.read()

task = task.replace("- `[/]` Fix root cause of `stale` errors after reconnects (likely resubscription not triggering properly or triggering at the wrong lifecycle event).", "- `[x]` Fix root cause of `stale` errors after reconnects (`on_open` vs `on_connect` bug fixed).")
task = task.replace("- `[ ]` Add a test proving instruments are reattached on WS `on_open`.", "- `[x]` Add a test proving instruments are reattached on WS `on_open`.")
task = task.replace("- `[ ]` Add a test proving `os._exit(1)` can only execute inside the child feed process.", "- `[x]` Add a test proving `os._exit(1)` can only execute inside the child feed process.")
task = task.replace("- `[ ]` Verify MOD-4, 7, 8, 9, 10 are safely implemented (or implement them safely if missing).", "- `[x]` Verify MOD-4, 7, 8, 9, 10 are safely implemented (confirmed already applied in codebase).")
task = task.replace("- `[ ]` Verify MOD-5/6 (Option Verification) is safely implemented.", "- `[x]` Verify MOD-5/6 (Option Verification) is safely implemented (confirmed already applied in codebase).")

with open("/Users/madhuram/.gemini/antigravity/brain/a9d80830-a851-4aa0-959f-699d7a8f9d24/task.md", "w") as f:
    f.write(task)

# Update walkthrough.md
with open("/Users/madhuram/.gemini/antigravity/brain/a9d80830-a851-4aa0-959f-699d7a8f9d24/walkthrough.md", "r") as f:
    wt = f.read()

wt += """
## Feed Reconnect Stale Fix (`on_open` vs `on_connect`)
I identified why the feed was getting "stale" ticks even after a successful reconnect: the `autobahn` websocket library triggers `on_connect` during the initial handshake, but you cannot subscribe to channels until `on_open` (when the socket is fully established). I replaced `on_connect` with `on_open` for sending the instrument subscriptions, keeping only logging in `on_connect`. 

## Safety and Regression Tests Added
1. **Instrument Reattachment Test**: Added `test_on_open_resubscribes_instruments` in `tests/test_kite_depth_ws_stability.py` to prove that `_resubscribe_full` is properly triggered on the `on_open` callback, and that reconnect attempts don't subscribe to instruments blindly.
2. **Subprocess `os._exit` Protection Test**: Added `test_restart_depth_ws_calls_os_exit_in_child_process` in `tests/test_kite_ws_subprocess.py` to explicitly assert that `os._exit(1)` is only ever invoked if the current process is the designated child process (`in_child_process = multiprocessing.current_process().name != "MainProcess"`), protecting the main orchestrator.

## Configuration & MOD Verification
I audited the code to ensure all fixes identified in the RCA document (`feed-rca-20260610.md`) were implemented. I verified that MODs 4, 5, 6, 7, 8, 9, 10 are all present in the codebase.
The subprocess mode (`FEED_USE_SUBPROCESS`) remains feature-flagged and disabled by default.

## New Soak Observation
I restarted the live soak observation (`feed_stab_09_canonical_proof_live_probe_...`) so it uses the new `on_open` resubscription bug fix. It is currently running to prove the 90-minute stability requirement.
"""

with open("/Users/madhuram/.gemini/antigravity/brain/a9d80830-a851-4aa0-959f-699d7a8f9d24/walkthrough.md", "w") as f:
    f.write(wt)
