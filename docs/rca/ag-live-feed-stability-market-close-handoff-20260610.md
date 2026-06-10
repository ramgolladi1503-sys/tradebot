# AG Live Feed Stability Market Close Handoff (2026-06-10)

## Handoff Context
The live audit-only experiment has concluded successfully at market close. All processes have been cleanly terminated and postrun evidence has been packaged into `runtime/live_observation/ag_postrun_20260610_152858/`.

## Key Technical Achievements
1. **Twisted Reactor Safety**: Re-runs or reconnection attempts on stopped reactors are now blocked programmatically before Twisted raises `ReactorNotRestartable`.
2. **Defensive CPU Protection**: Orchestrator monitoring now sleeps for 2 seconds when feed lifecycle enters a fatal state, stopping high-CPU spin loops.
3. **Strict Feed Validation**: Checks are now in place to prevent candidate evaluation on stale depth and db ticks.
4. **Pass Invariants**: No order placements were attempted or executed.

## Next Steps for Codex / Future Agents
- **Merge stability fixes**: The branch `ag/live-feed-stability-experiment-20260610` is ready for review and merge into main.
- **Extend Reconnection Coverage**: If a disconnect occurs, a separate subprocess could run the Twisted WebSocket reactor, allowing the subprocess to restart independently without affecting the main python process.
- **Verification Command**:
  ```bash
  PYTHONPATH=. pytest -q   tests/test_feed_recovery_runtime.py   tests/test_feed_runtime_states.py   tests/test_orchestrator_pilot_feed_ok.py   tests/test_orchestrator_latency_accounting.py   tests/test_runtime_health.py   tests/behavior/test_top_opportunity_edge_behavior.py
  ```
