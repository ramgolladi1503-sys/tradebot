# Disable KiteTicker Internal Auto-Retry After Terminal WS1006

This document records the offline, read-only rationale for suppressing KiteTicker/Twisted internal retry after terminal WS1006 / unclean websocket close conditions.

The live audit evidence from PR #488 showed that outer restart suppression was not enough on its own: Twisted/KiteTicker could still emit internal retry behavior after a terminal WS1006 path, which risks repeating the same failure mode even when the runtime is already marked `RECOVERY_BLOCKED`.

The required behavior is conservative and fail-closed:

- terminal WS1006 / unclean close transitions into `RECOVERY_BLOCKED`
- `process_restart_required` remains true
- `restart_suppressed` remains true
- internal KiteTicker retry is disabled when supported
- no broker, order, strategy, ranking, or Phase2 behavior changes are introduced

This is an offline safety regression guard only. It does not prove trading edge and it does not change live execution semantics outside the terminal websocket failure path.
