# Legacy Replay Limitations

## Data Fidelity
The replay mechanism is constrained by the shape of the incoming event stream:
- It processes full OHLCV or raw Tick events matching the `RecordedReplayEvent` schema.
- Market depth updates are currently not processed in the legacy loop replay test but can be extended if recorded datasets provide matching L2 snapshot events.

## Missing Features
1. **Background Replay**: `scripts/run_legacy_production_replay.py` is synchronous and block-evaluated. Replaying a continuous stream for thousands of ticks requires external iterator implementations that feed events at a governed pace.
2. **Missing Quotes**: Since most historical data lacks quotes and option chain pricing, evaluating advanced greeks requires mock inputs or skipping those strategy legs.

## Boundary Exclusions
- The `StrategyContext` / `StrategyCandidate` abstraction is entirely omitted, preserving the pristine `ACTIVE_LEGACY_PRODUCTION_PATH`.
