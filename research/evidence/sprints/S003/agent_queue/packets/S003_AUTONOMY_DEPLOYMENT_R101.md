# S003 aMROS deployment health verification R101

This is a non-certifying operational health check. Do not modify repository or runtime state.

The disposable job worktree candidate is only an execution anchor. The actual deployment target is the persistent Mac bridge and supervisor.

Verify all of the following directly on the Mac:

1. `git -C /Users/madhuram/.mros-agent-bridge/bridge rev-parse HEAD` is `499f9ef3f45661f8c59ec03c8b7f09e03a90d9ff` or a descendant on `research/mros-agent-bridge-v1`.
2. `/Users/madhuram/.mros-agent-bridge/bridge/scripts/mros/mros_autonomous_cycle_stderr_safe.py` exists.
3. `/Users/madhuram/.mros-agent-bridge/bridge/scripts/mros/mros_autonomous_supervisor.py` routes S003 through the stderr-safe wrapper.
4. `/Users/madhuram/.mros-agent-bridge/state/supervisor_health.json` currently reports `supervisor_status` = `RUNNING` and `last_error` = null.
5. The authority checkout is clean using stdout-only porcelain semantics: capture stdout and stderr separately for `git -C /Users/madhuram/.mros-agent-bridge/authority status --porcelain`; stderr warnings must not count as dirty state.
6. The authority checkout HEAD has fast-forwarded to `origin/research/mros-program-v1`.
7. Report the current active sprint status and whether it changed since `BOARD_AUTONOMOUS_R004_REVIEW_REPAIR_REQUIRED`.

Return concise Markdown with exact command outputs needed to prove each item, plus terminal verdict exactly one of:

`AMROS_DEPLOYMENT_HEALTH_PASS`
`AMROS_DEPLOYMENT_HEALTH_BLOCKED`

If blocked, include the first concrete blocker. Runtime authority must remain NONE and no broker actions are allowed.
