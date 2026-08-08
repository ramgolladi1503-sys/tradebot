# S003 bridge self-update bootstrap R102

Operational-only, non-certifying. Do not review or repair the S003 candidate.

Run the persistent bridge autoupdater directly on the Mac:

`python3 /Users/madhuram/.mros-agent-bridge/bridge/scripts/mros/mros_bridge_autoupdater.py --source-repo /Users/madhuram/tradebot --bridge-worktree /Users/madhuram/.mros-agent-bridge/bridge --state-root /Users/madhuram/.mros-agent-bridge/state`

Then report:

1. updater stdout/stderr and exit code;
2. `git -C /Users/madhuram/.mros-agent-bridge/bridge rev-parse HEAD`;
3. `git -C /Users/madhuram/.mros-agent-bridge/bridge status --porcelain` with stdout/stderr separated;
4. `cat /Users/madhuram/.mros-agent-bridge/state/supervisor_health.json`;
5. exact authority and queue HEADs.

Required bridge target is `dcac192cb0f255c9663ab721a363c9d9153619ad` or a descendant on `research/mros-agent-bridge-v1`.

Do not alter runtime authority, trading code, broker state, strategy state, program acceptance state, or M9. Runtime authority must remain NONE. Broker actions are forbidden.

Terminal verdict exactly one of:

`AMROS_BRIDGE_UPDATE_PASS`
`AMROS_BRIDGE_UPDATE_BLOCKED`
