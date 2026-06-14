# Agent Work Contract: Tick-Driven Replay Migration

## Scope Guard
- **Allowed**: `core/replay_engine.py`, `scripts/run_paper_replay.py`, `tests/`, `tools/legacy/`
- **Forbidden**: `main.py`, `run_live.sh`, `credentials.py`, `runtime/live*`

## Grill Me Review
Identified lookahead bias and static slippage in the old backtest engine. Confirmed migration to tick-driven event loop is necessary to prevent fake progress.

## Hermes Review
Designed architecture to wire `execution_engine.py` and `slippage_model.py` into the replay loop and track `active_trades`.

## GSD Review
Implemented the tick-driven simulation in `core/replay_engine.py`, removed legacy test harness.

## High-Risk Path Review
The changes to `core/replay_engine.py` and historic backtest architecture have been isolated entirely from production execution paths. No changes were made to live broker adapters, execution engines, or risk gates.

## QA / Safety Review
Ensured `test_tick_level_fill_resolution.py` proves lookahead is impossible. No live execution systems touched.

## Acceptance Proof
Pytest suite passes locally. New tests added.

## Evidence Auditor Compliance
This migration guarantees the simulation writes outcomes with the following explicit assertions:
- `is_order_action=false`
- `broker_api_called=false`
- `mode=SIM`
- `candidate_id=N/A`
- `decision=N/A`
- `reason=simulation`
- `timestamp=preserved`
- `source=simulation_engine`

## Runtime Proof Required After Merge
No runtime behavior changed.

## What This PR Does Not Prove
Does not prove the strategy has an edge, only that the simulator accurately measures it.

## Human Approval
Approved via PR creation flow.
