# WS1006 Reactor Restart Suppression

This PR documents and guards the websocket lifecycle contract for WS1006 and related terminal reconnect failures.

## Live RCA Summary

In the live audit-only run on 2026-06-05, TradeBuilder still produced real ranked candidates, but the executable path was blocked by feed/runtime truth. A later WS1006 / unclean-close failure then caused repeated in-process websocket restart attempts and Twisted `ReactorNotRestartable` errors. The safe outcome must be a terminal recovery-blocked state that requires process restart.

## Safety Contract

- WS1006 / unclean close must fail closed.
- ReactorNotRestartable must be treated as terminal.
- In-process websocket restart must be suppressed once terminal recovery is detected.
- Feed/runtime truth must remain degraded or stale until the process is restarted.
- No hidden recovery success is allowed.

## Expected Behavior After WS1006

- `runtime_state=RECOVERY_BLOCKED` or equivalent terminal state
- `process_restart_required=True`
- `restart_suppressed=True`
- `ws_reconnect_allowed=False`
- `ws_reconnect_attempted=False`
- `reconnect_blocked_reason` includes `ws1006_process_restart_required` or `reactor_not_restartable_process_restart_required`
- No follow-up in-process restart thread or timer is scheduled
- Feed remains unhealthy, stale, or degraded

## Expected Evidence Fields

- `runtime_state`
- `process_restart_required`
- `restart_suppressed`
- `reconnect_blocked_reason`
- `restart_blocked_reason`
- `reactor_not_restartable_detected`
- `ws_reconnect_allowed`
- `ws_reconnect_attempted`
- `recovery_action`
- `recovery_blocked`
- `last_error`

## What This PR Does Not Do

- It does not change strategy, ranking, Phase2, broker/order, or dashboard behavior.
- It does not enable live trading.
- It does not make Twisted restartable in-process.
- It does not claim live edge or profitability.

## How To Validate Offline

- Run the focused restart tests.
- Confirm WS1006 and ReactorNotRestartable paths write recovery-blocked snapshots.
- Confirm follow-up restart scheduling is a no-op once terminal blocked.

## Future Live Validation Steps

- Re-run a live audit-only session.
- Confirm WS1006 produces one terminal recovery-blocked transition.
- Confirm no repeated in-process restart storms occur.
- Confirm feed truth stays degraded until process restart.
