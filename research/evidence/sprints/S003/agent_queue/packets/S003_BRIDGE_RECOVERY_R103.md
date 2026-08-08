# MROS S003 — Bridge recovery diagnostic R103

Authority candidate/head for context: `9378d3f6ff9d27b603c406b695367ae8232b5451`

This is an infrastructure-only diagnostic/repair. Do not edit trading/runtime/strategy/broker behavior and do not change `runtime_authority=NONE` or M9 status.

Inspect the persistent MROS launchd services and bridge deployment on this Mac:

1. `launchctl print gui/$(id -u)/com.aixion.mros-bridge-autoupdater`
2. `launchctl print gui/$(id -u)/com.aixion.mros-autonomous-supervisor`
3. `launchctl print gui/$(id -u)/com.aixion.mros-agent-worker`
4. Inspect `/Users/madhuram/.mros-agent-bridge/state`, its ownership/mode/flags/ACL, `bridge-updater.lock`, `bridge_updates.log`, `supervisor_health.json`, and updater/supervisor stderr logs.
5. Inspect local bridge HEAD and remote `origin/research/mros-agent-bridge-v1` HEAD.

If the earlier `Operation not permitted` was only caused by the isolated Codex sandbox, state that clearly and do not modify permissions.

If the persistent launchd updater itself is blocked by an incorrect user-owned filesystem mode/ACL/flag under `/Users/madhuram/.mros-agent-bridge/state`, make only the minimum safe user-level repair needed for the MROS services to write their own state. Do not use broad world-writable permissions. Do not touch unrelated paths. Then kickstart the updater and supervisor and verify that the bridge reaches the remote bridge HEAD or later and supervisor health is `RUNNING` with `last_error=null`.

If macOS privacy/TCC, immutable flags, root ownership, or another condition prevents a safe user-level repair, do not bypass it; report the exact operator-only command/action required.

Return a concise markdown result with: persistent updater status, persistent supervisor status, local bridge HEAD, remote bridge HEAD, authority HEAD, queue HEAD, whether a repair was performed, exact repair if any, final supervisor health, and one verdict: `AMROS_BRIDGE_RECOVERED`, `AMROS_BRIDGE_ALREADY_HEALTHY`, or `AMROS_BRIDGE_OPERATOR_BLOCKED`.