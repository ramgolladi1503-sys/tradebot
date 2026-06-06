# Live Run With Agent Command Center

This wrapper launches the Agent Command Center as a read-only sidecar while `run_live.sh` remains the primary live process.

## Usage

```bash
bash scripts/run_live_with_agent_command_center.sh
```

## Behavior

- Starts the Agent Command Center watcher in the background.
- Runs the existing live bot via `bash run_live.sh` in the foreground.
- Writes reports under `.runtime/agent_reports/runs/<run_id>/`.
- Copies the latest report artifacts to `.runtime/agent_reports/` when `--copy-latest true` is used.
- Stops only the watcher started by the wrapper on exit or interrupt.
- Runs one final one-shot report before exiting.

## Safety Constraints

- Read-only sidecar only.
- No broker or order calls.
- No live order behavior changes.
- No websocket reconnect changes.
- No strategy, ranking, Phase2, or dashboard changes.
- No runtime mutation, lock deletion, or process-kill behavior outside the watcher launched by the wrapper.

## Report Artifacts

- `.runtime/agent_reports/agent_command_center_latest.json`
- `.runtime/agent_reports/agent_command_center_latest.md`
- `.runtime/agent_reports/runs/<run_id>/agent_command_center_latest.json`
- `.runtime/agent_reports/runs/<run_id>/agent_command_center_latest.md`

## Validation

- `PYTHONPATH=. pytest -q tests/test_agent_command_center_watch.py tests/test_agent_live_sidecar_wrapper_contract.py -vv`
- `PYTHONPATH=. python scripts/run_tradebot_agent_command_center.py --watch --once --run-id smoke --run-dir .runtime/agent_reports/runs/smoke --copy-latest true`

